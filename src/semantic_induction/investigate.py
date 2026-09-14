"""Execute evidence-backed analytical investigations without inventing structure."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from semantic_induction.compile import CompileError, compile_metric
from semantic_induction.labeling import LabelingStore
from semantic_induction.memory import Evidence, MetricDefinition, retrieve
from semantic_induction.models import Catalog, Metric


@dataclass(frozen=True)
class InvestigationResult:
    question: str
    status: str
    definition_id: str | None = None
    inferred_definition: str | None = None
    evidence: tuple[Evidence, ...] = ()
    sql: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    message: str | None = None


def _metric_from_definition(definition: MetricDefinition) -> Metric:
    return Metric(
        measure=definition.measure,
        grain=frozenset(definition.grain),
        join_path=definition.join_path,
        default_filters=definition.default_filters,
        support=0,
        seen_in=definition.evidence_ids,
    )


def investigate(
    question: str,
    store: LabelingStore,
    catalog: Catalog,
    connection: Any,
) -> InvestigationResult:
    """Answer only from an approved definition, otherwise request review."""
    hits = [hit for hit in retrieve(question, store.memory) if hit.kind == "METRIC_DEFINITION"]
    approved = [
        hit for hit in hits
        if store.memory.resolutions.get(hit.object_id)
        and store.memory.resolutions[hit.object_id].decision == "APPROVE"
    ]
    if len(approved) != 1:
        status = "NEEDS_REVIEW" if not approved else "AMBIGUOUS"
        return InvestigationResult(
            question=question,
            status=status,
            message=(
                "No approved metric definition matched the question."
                if not approved
                else "Multiple approved metric definitions matched the question."
            ),
        )

    definition = store.memory.metric_definitions[approved[0].object_id]
    evidence = tuple(
        store.memory.evidence[item]
        for item in definition.evidence_ids
        if item in store.memory.evidence
    )
    try:
        sql = definition.query_sql or compile_metric(_metric_from_definition(definition), catalog)
        result = connection.execute(sql)
        columns = tuple(item[0] for item in result.description)
        rows = tuple(result.fetchall())
    except CompileError as error:
        return InvestigationResult(
            question, "UNSUPPORTED", definition.definition_id,
            definition.inferred_definition, evidence, message=str(error)
        )
    except Exception as error:
        return InvestigationResult(
            question, "EXECUTION_FAILED", definition.definition_id,
            definition.inferred_definition, evidence, sql=sql if "sql" in locals() else None,
            message=str(error)
        )
    return InvestigationResult(
        question=question,
        status="ANSWERED",
        definition_id=definition.definition_id,
        inferred_definition=definition.inferred_definition,
        evidence=evidence,
        sql=sql,
        columns=columns,
        rows=rows,
    )