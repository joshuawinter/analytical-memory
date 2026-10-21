"""Tier 3 - three-arm executable-equivalence experiment (architecture doc, Stage 6).

Compares match rate across arms answering held-out business questions, with
the original SQL withheld from every composer:

  Arm A (RAW_SCHEMA):    catalog only          -> composer returns SQL directly
  Arm B (INDUCED_LAYER): induced SemanticLayer  -> composer returns a MetricPlan,
                         resolved and compiled deterministically via plan.py

The delta between the two match rates is the thesis's entire finding: how
much of a curated layer's benefit was recovered purely from usage. A third,
curated-documentation arm is intentionally not wired to a default runner:
this repository does not bundle hand-authored TPC-H/TPC-DS business
definitions to compare against. ``CURATED_DOCS`` is reserved for a future
run once such text is supplied, using the same ``SqlComposer`` protocol as
the raw-schema arm.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from semantic_induction.compile import CompileError, compile_metric
from semantic_induction.models import Catalog, Predicate, SemanticLayer
from semantic_induction.naming import EnvironmentNamingConfig
from semantic_induction.plan import MetricPlan, PlanValidationError, resolve_plan
from semantic_induction.validate import _cell, _read_answer

RAW_SCHEMA = "RAW_SCHEMA"
INDUCED_LAYER = "INDUCED_LAYER"
CURATED_DOCS = "CURATED_DOCS"


@dataclass(frozen=True)
class BusinessQuestion:
    """A held-out question; the source SQL is never given to any composer."""

    question_id: str
    text: str


@dataclass(frozen=True)
class ArmResult:
    question_id: str
    arm: str
    match: bool
    sql: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class Tier3Report:
    results: tuple[ArmResult, ...]

    def arm(self, arm: str) -> tuple[ArmResult, ...]:
        return tuple(result for result in self.results if result.arm == arm)

    def match_rate(self, arm: str) -> float:
        results = self.arm(arm)
        return sum(result.match for result in results) / len(results) if results else 0.0

    def delta(self, arm_a: str = RAW_SCHEMA, arm_b: str = INDUCED_LAYER) -> float:
        """Positive means the induced layer out-performed the raw-schema control."""
        return self.match_rate(arm_b) - self.match_rate(arm_a)


class SqlComposer(Protocol):
    def compose(self, question: BusinessQuestion, context: str) -> str: ...


class PlanComposer(Protocol):
    def compose(self, question: BusinessQuestion, vocabulary: dict[str, Any]) -> MetricPlan: ...


def render_schema(catalog: Catalog) -> str:
    """Render the raw catalog as text context for the control arm."""
    return "\n".join(
        f"{table}({', '.join(sorted(catalog[table]))})" for table in sorted(catalog)
    )


def _canonical_rows(columns: list[str], rows: list[tuple[object, ...]]) -> list[tuple[object, ...]]:
    """Reorder each row's cells into sorted-column order for name-based comparison."""
    order = sorted(range(len(columns)), key=lambda index: columns[index])
    return [tuple(row[index] for index in order) for row in rows]


def compare_by_named_columns(
    connection: Any,
    sql: str,
    answer_path: Path,
    order_insensitive: bool = True,
) -> tuple[bool, int, int, str | None]:
    """Compare SQL results to a reference CSV by column NAME, not position.

    Tier 3 composers legitimately choose their own column order (and, for
    the raw-schema arm, largely their own aliases). Requiring an exact,
    fixed column order like ``validate.py``'s saved-query harness does
    would fail a run that computed the right answer under a different but
    equally valid column order.
    """
    try:
        result = connection.execute(sql)
        actual_columns = [description[0] for description in result.description]
        actual_rows = [tuple(_cell(value) for value in row) for row in result.fetchall()]
        expected_columns, expected_rows = _read_answer(answer_path)
        if set(actual_columns) != set(expected_columns):
            return (
                False,
                len(actual_rows),
                len(expected_rows),
                f"column names differ: got {sorted(actual_columns)!r}, "
                f"expected {sorted(expected_columns)!r}",
            )
        actual_canonical = _canonical_rows(actual_columns, actual_rows)
        expected_canonical = _canonical_rows(expected_columns, expected_rows)
        if order_insensitive:
            actual_canonical.sort(key=repr)
            expected_canonical.sort(key=repr)
        match = actual_canonical == expected_canonical
        return match, len(actual_rows), len(expected_rows), None
    except Exception as error:
        return False, 0, 0, str(error)


def layer_vocabulary(layer: SemanticLayer) -> dict[str, Any]:
    """Expose only named, induced handles to a plan composer.

    Join paths and invariant filters are deliberately absent: a composer
    selects a measure and demonstrated grain by name, and ``resolve_plan`` is
    the only thing that ever attaches the corpus-demonstrated join path and
    invariant filters to the result.
    """
    return {
        "measures": [
            {"aggregation": aggregation, "column": column, "support": measure.support}
            for (aggregation, column), measure in layer.measures.items()
        ],
        "dimensions": [
            {"column": dimension.column, "support": dimension.support}
            for dimension in layer.dimensions.values()
        ],
        "metric_signatures": [
            {
                "aggregation": aggregation,
                "column": column,
                "dimensions": sorted(metric.grain),
                "support": metric.support,
            }
            for metric in layer.metrics
            for aggregation, column in [metric.measure]
        ],
    }


def run_raw_schema_arm(
    questions: Iterable[BusinessQuestion],
    catalog: Catalog,
    composer: SqlComposer,
    connection: Any,
    answer_dir: Path,
) -> list[ArmResult]:
    schema_text = render_schema(catalog)
    results: list[ArmResult] = []
    for question in questions:
        try:
            sql = composer.compose(question, schema_text)
        except Exception as error:
            results.append(ArmResult(question.question_id, RAW_SCHEMA, False, None, str(error)))
            continue
        match, _actual, _expected, error = compare_by_named_columns(
            connection, sql, answer_dir / f"{question.question_id}.csv"
        )
        results.append(ArmResult(question.question_id, RAW_SCHEMA, match, sql, error))
    return results


def run_induced_layer_arm(
    questions: Iterable[BusinessQuestion],
    layer: SemanticLayer,
    catalog: Catalog,
    composer: PlanComposer,
    connection: Any,
    answer_dir: Path,
) -> list[ArmResult]:
    vocabulary = layer_vocabulary(layer)
    results: list[ArmResult] = []
    for question in questions:
        try:
            plan = composer.compose(question, vocabulary)
            metric = resolve_plan(plan, layer, catalog)
            sql = compile_metric(metric, catalog)
        except (PlanValidationError, CompileError) as error:
            results.append(ArmResult(question.question_id, INDUCED_LAYER, False, None, str(error)))
            continue
        except Exception as error:
            results.append(ArmResult(question.question_id, INDUCED_LAYER, False, None, str(error)))
            continue
        match, _actual, _expected, error = compare_by_named_columns(
            connection, sql, answer_dir / f"{question.question_id}.csv"
        )
        results.append(ArmResult(question.question_id, INDUCED_LAYER, match, sql, error))
    return results


def run_tier3(
    questions: Iterable[BusinessQuestion],
    catalog: Catalog,
    layer: SemanticLayer,
    connection: Any,
    answer_dir: Path,
    raw_schema_composer: SqlComposer,
    induced_layer_composer: PlanComposer,
) -> Tier3Report:
    questions = list(questions)
    results = run_raw_schema_arm(questions, catalog, raw_schema_composer, connection, answer_dir)
    results += run_induced_layer_arm(
        questions, layer, catalog, induced_layer_composer, connection, answer_dir
    )
    return Tier3Report(tuple(results))


@dataclass
class MockSqlComposer:
    """Deterministic lookup. Exercises the harness only; not a demonstration."""

    answers: dict[str, str]

    def compose(self, question: BusinessQuestion, context: str) -> str:
        return self.answers[question.question_id]


@dataclass
class MockPlanComposer:
    """Deterministic lookup. Exercises the harness only; not a demonstration."""

    plans: dict[str, MetricPlan]

    def compose(self, question: BusinessQuestion, vocabulary: dict[str, Any]) -> MetricPlan:
        return self.plans[question.question_id]


def _anthropic_client(config: EnvironmentNamingConfig) -> Any:
    # Routed through the spend ledger and response cache (RUNBOOK section 14),
    # so a rerun of the same questions against the same layer costs nothing.
    from semantic_induction.spend import metered_anthropic_client

    return metered_anthropic_client(config, purpose="tier3", component="Tier 3 Anthropic composers")


def _parse_json_object(text: str) -> dict[str, object]:
    """Parse JSON returned as raw text or inside a Markdown code fence."""
    candidates = [text]
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        candidates.append("\n".join(lines[1:-1]).strip())
    for candidate in candidates:
        try:
            result = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            return result
    raise ValueError("response did not contain a JSON object")


class AnthropicSqlComposer:
    """Claude-backed control-arm composer: raw schema in, SQL text out."""

    def __init__(self, config: EnvironmentNamingConfig | None = None, client: Any | None = None):
        self.config = config or EnvironmentNamingConfig()
        self.client = client or _anthropic_client(self.config)

    def compose(self, question: BusinessQuestion, context: str) -> str:
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=1024,
            system=(
                "Write a single DuckDB SQL query that answers the business "
                "question using only the tables and columns provided. Alias "
                "the primary computed aggregate as metric_value. Keep any "
                "grouping or dimension columns under their original column "
                "names, unaliased. Return JSON only with one field: sql."
            ),
            messages=[
                {
                    "role": "user",
                    "content": json.dumps({"question": question.text, "schema": context}),
                }
            ],
        )
        result = _parse_json_object(response.content[0].text.strip())
        sql = result.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("Anthropic composer response missing non-empty sql field")
        return sql.strip()


class AnthropicPlanComposer:
    """Claude-backed thesis-arm composer: induced vocabulary in, MetricPlan out."""

    def __init__(self, config: EnvironmentNamingConfig | None = None, client: Any | None = None):
        self.config = config or EnvironmentNamingConfig()
        self.client = client or _anthropic_client(self.config)

    def compose(self, question: BusinessQuestion, vocabulary: dict[str, Any]) -> MetricPlan:
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=1024,
            system=(
                "Answer the business question by selecting only from the "
                "given measures and demonstrated metric signatures. The "
                "dimensions in a metric signature are the exact grouping "
                "columns to return; select one complete signature rather "
                "than substituting a similarly named key. Do not invent "
                "columns, joins, or filters not present in the vocabulary. Filter "
                'op must be one of "EQ", "NEQ", "GT", "GTE", "LT", "LTE". '
                "Filter value must be a PLAIN value with no quotes, casts, "
                'or SQL syntax -- e.g. "1998-09-02" for a date, "OPEN" for '
                'a string, "300" for a number. Return JSON only, flat, '
                'with exactly these keys: {"aggregation": str, "column": '
                'str, "dimensions": [str], "filters": [{"column": str, '
                '"op": str, "value": plain value}]}. Example: '
                '{"aggregation": "SUM", "column": "lineitem.l_extendedprice", '
                '"dimensions": ["lineitem.l_returnflag"], "filters": '
                '[{"column": "lineitem.l_shipdate", "op": "LTE", "value": '
                '"1998-09-02"}]}'
            ),
            messages=[
                {
                    "role": "user",
                    "content": json.dumps({"question": question.text, "vocabulary": vocabulary}),
                }
            ],
        )
        result = _parse_json_object(response.content[0].text.strip())
        try:
            measure = _extract_measure(result)
            dimensions = tuple(result.get("dimensions") or ())
            filters = tuple(
                Predicate(item["column"], item["op"], str(item["value"]))
                for item in (result.get("filters") or ())
            )
        except (KeyError, TypeError, IndexError) as error:
            raise ValueError(
                f"Anthropic composer response missing required plan fields: {result!r}"
            ) from error
        return MetricPlan(measure=measure, dimensions=dimensions, filters=filters)


def _extract_measure(result: dict[str, object]) -> tuple[str, str]:
    """Accept the requested flat shape plus common model deviations."""
    if "aggregation" in result and "column" in result:
        return str(result["aggregation"]), str(result["column"])
    measure = result.get("measure")
    if isinstance(measure, dict) and "aggregation" in measure and "column" in measure:
        return str(measure["aggregation"]), str(measure["column"])
    if isinstance(measure, (list, tuple)) and len(measure) == 2:
        return str(measure[0]), str(measure[1])
    raise KeyError("aggregation/column")

