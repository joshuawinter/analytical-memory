"""Evidence-backed analytical memory and deterministic retrieval.

This module is intentionally small and dependency-free. It wraps the existing
induced semantic layer with business concepts, evidence, and investigation
records without changing the validated SQL-induction contracts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from semantic_induction.models import JoinEdge, Metric, Predicate, SemanticLayer, TableProfile


@dataclass(frozen=True)
class BusinessConcept:
    concept_id: str
    preferred_label: str
    aliases: tuple[str, ...] = ()
    definition: str = ""
    broader_concept_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_type: str
    source_ref: str
    excerpt: str = ""
    confidence: float = 1.0
    observed_at: datetime | None = None


@dataclass(frozen=True)
class MetricDefinition:
    definition_id: str
    concept_id: str
    measure: tuple[str, str]
    grain: tuple[str, ...]
    join_path: tuple[JoinEdge, ...] = ()
    default_filters: tuple[Predicate, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    status: str = "OBSERVED"
    confidence: float = 0.0
    inferred_definition: str = ""
    profile_notes: tuple[str, ...] = ()
    query_sql: str | None = None
    profile_tables: tuple[str, ...] = ()


@dataclass(frozen=True)
class Investigation:
    investigation_id: str
    question: str
    concept_ids: tuple[str, ...] = ()
    metric_definition_id: str | None = None
    assumptions: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    generated_sql: str | None = None
    finding: str | None = None
    validation_status: str | None = None


@dataclass(frozen=True)
class Resolution:
    resolution_id: str
    target_id: str
    decision: str
    rationale: str
    decided_by: str
    decided_at: datetime
    valid_from: datetime | None = None
    valid_to: datetime | None = None


@dataclass
class AnalyticalMemory:
    concepts: dict[str, BusinessConcept] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    profiles: dict[str, TableProfile] = field(default_factory=dict)
    metric_definitions: dict[str, MetricDefinition] = field(default_factory=dict)
    investigations: dict[str, Investigation] = field(default_factory=dict)
    resolutions: dict[str, Resolution] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalHit:
    kind: str
    object_id: str
    score: float
    matched_terms: tuple[str, ...]


def is_publishable_metric(
    definition: MetricDefinition, known_tables: set[str] | None = None
) -> bool:
    """Keep query-local implementation details out of the business catalog.

    The corpus extractor intentionally records CTEs and CASE expressions for
    lineage. A derived CTE alias or mutually-exclusive branch predicates cannot
    be represented faithfully by the simple metric contract, so it must not be
    presented as a business definition until a richer expression model exists.
    """
    measure_column = definition.measure[1]
    # A hand-authored, executable definition is already a governed expression;
    # unqualified columns without SQL are unresolved query-local aliases.
    if measure_column != "*" and "." not in measure_column and not definition.query_sql:
        return False
    source_columns = [measure_column, *definition.grain]
    if known_tables and any(
        "." in column and column.split(".", 1)[0] not in known_tables
        for column in source_columns
    ):
        return False
    for predicate in definition.default_filters:
        # A nested query or a query-local ranking requires an expression model,
        # not the simple measure/grain/filter contract used by this catalog.
        if "SELECT" in predicate.value.upper() or "." not in predicate.column:
            return False
    values_by_column: dict[str, set[str]] = {}
    for predicate in definition.default_filters:
        values_by_column.setdefault(predicate.column, set()).add(predicate.value)
    return not any(len(values) > 1 for values in values_by_column.values())


def metric_definition_from_metric(
    metric: Metric,
    definition_id: str,
    concept_id: str,
    evidence_ids: tuple[str, ...] = (),
    status: str = "OBSERVED",
    profiles: dict[str, TableProfile] | None = None,
) -> MetricDefinition:
    """Promote an induced metric into an evidence-backed memory record."""
    return MetricDefinition(
        definition_id=definition_id,
        concept_id=concept_id,
        measure=metric.measure,
        grain=tuple(sorted(metric.grain)),
        join_path=metric.join_path,
        default_filters=metric.default_filters,
        evidence_ids=evidence_ids or metric.seen_in,
        status=status,
        confidence=min(1.0, metric.support / 3),
        inferred_definition=infer_metric_definition(metric),
        profile_notes=profile_notes(metric, profiles),
    )


def _human_table(table: str) -> str:
    return {
        "lineitem": "line items",
        "partsupp": "part-supplier records",
        "store_sales": "store sales transactions",
        "catalog_sales": "catalog sales transactions",
        "web_sales": "web sales transactions",
        "customer_address": "customer addresses",
        "date_dim": "calendar dates",
        "item": "items",
    }.get(
        table, table.replace("_", " ")
    )


def _human_column(column: str) -> str:
    name = column.rsplit(".", 1)[-1]
    known_names = {
        "ca_state": "customer state",
        "d_year": "calendar year",
        "d_moy": "calendar month",
        "d_month_seq": "calendar month sequence",
        "i_current_price": "current item price",
        "ss_ext_sales_price": "gross store sales",
        "ss_net_paid": "net store payment",
        "ss_net_profit": "store net profit",
        "sr_return_amt": "store return amount",
    }
    if name in known_names:
        return known_names[name]
    if "_" in name:
        name = name.split("_", 1)[1]
    name = name.replace("_", " ")
    for compact, spaced in {
        "returnflag": "return flag",
        "linestatus": "line status",
        "supplycost": "supply cost",
        "partkey": "part key",
        "shipdate": "ship date",
        "extendedprice": "extended price",
    }.items():
        name = name.replace(compact, spaced)
    return name


def _table_from_column(column: str) -> str | None:
    return column.split(".", 1)[0] if "." in column else None


def _clean_value(value: str) -> str:
    match = re.search(r"'([^']+)'", value)
    return match.group(1) if match else value


def _filter_phrase(predicate: Predicate) -> str:
    operators = {
        "EQ": "is",
        "NEQ": "is not",
        "LTE": "is on or before",
        "LT": "is before",
        "GTE": "is on or after",
        "GT": "is after",
    }
    value = _clean_value(predicate.value)
    if predicate.column.endswith(".d_moy") and predicate.op == "EQ":
        month = re.fullmatch(r"\s*(\d{1,2})\s*", value)
        if month and 1 <= int(month.group(1)) <= 12:
            month_name = (
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December",
            )[int(month.group(1)) - 1]
            return f"calendar month is {month_name}"
    if predicate.column.endswith(".d_month_seq") and "d_year" in value and "d_moy" in value:
        year = re.search(r"d_year[^0-9]*(\d{4})", value)
        month = re.search(r"d_moy[^0-9]*(\d{1,2})", value)
        if year and month:
            month_name = (
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December",
            )[int(month.group(1)) - 1]
            return f"during {month_name} {year.group(1)}"
    if predicate.column.endswith(".i_current_price") and "AVG" in value and "i_category" in value:
        multiplier = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*\*", value)
        if multiplier:
            percent = round((float(multiplier.group(1)) - 1) * 100)
            return f"current item price is more than {percent}% above its category average"
    return f"{_human_column(predicate.column)} {operators.get(predicate.op, predicate.op.lower())} {value}"


def infer_metric_definition(metric: Metric) -> str:
    """Render observed structure as a cautious business-readable definition."""
    aggregation, column = metric.measure
    if column != "*" and "." not in column:
        return "Derived query expression. Requires review before it can become a business metric."
    measure_table = _table_from_column(column) if column != "*" else None
    anchor_table = measure_table or (
        _table_from_column(next(iter(metric.grain), "")) if metric.grain else None
    )
    subject = _human_table(anchor_table) if anchor_table else "records"
    if aggregation == "COUNT" and column == "*":
        # A count with only customer geography in its grain commonly represents
        # sales activity, not a count of geography rows.
        if any(item.endswith(".ca_state") for item in metric.grain):
            measure_text = "Number of store sales transactions"
        else:
            measure_text = f"Number of {subject}"
    elif aggregation == "SUM":
        measure_text = f"Total {_human_column(column)} for {subject}"
    else:
        measure_text = f"{aggregation.title()} of {_human_column(column)} for {subject}"
    clauses = [measure_text]
    if metric.grain:
        dimensions = " and ".join(_human_column(item) for item in sorted(metric.grain))
        clauses.append(f"grouped by {dimensions}")
    if metric.default_filters:
        filter_phrases = [_filter_phrase(item) for item in metric.default_filters]
        has_calendar_month = any(phrase.startswith("during ") for phrase in filter_phrases)
        if has_calendar_month:
            filter_phrases = [
                phrase for phrase in filter_phrases
                if not (phrase.startswith("calendar month is ") or phrase.startswith("calendar year is "))
            ]
        clauses.append("where " + " and ".join(filter_phrases))
    return ", ".join(clauses) + "."


def profile_notes(metric: Metric, profiles: dict[str, TableProfile] | None = None) -> tuple[str, ...]:
    """Summarize data evidence without treating it as a business definition."""
    if not profiles:
        return ()
    tables: set[str] = set()
    if metric.measure[1] != "*":
        table = _table_from_column(metric.measure[1])
        if table:
            tables.add(table)
    tables.update(table for table in (_table_from_column(item) for item in metric.grain) if table)
    notes: list[str] = []
    for table in sorted(tables):
        profile = profiles.get(table)
        if profile:
            notes.append(f"{_human_table(table)}: {profile.row_count:,} observed rows")
    for column in sorted(metric.grain):
        table = _table_from_column(column)
        if table and table in profiles:
            name = column.split(".", 1)[1]
            column_profile = profiles[table].columns.get(name)
            if column_profile:
                notes.append(f"{_human_column(column)}: {column_profile.distinct_count:,} distinct values")
    return tuple(notes)


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1}


def _metric_text(definition: MetricDefinition, concept: BusinessConcept | None) -> str:
    parts = [definition.measure[0], definition.measure[1], *definition.grain]
    parts.extend(f"{predicate.column} {predicate.op} {predicate.value}" for predicate in definition.default_filters)
    if concept is not None:
        parts.extend((concept.preferred_label, *concept.aliases, concept.definition))
    return " ".join(parts)


def retrieve(
    query: str,
    memory: AnalyticalMemory,
    limit: int = 10,
) -> list[RetrievalHit]:
    """Return deterministic concept and metric matches ranked by token overlap."""
    if limit <= 0:
        return []
    query_terms = _tokens(query)
    if not query_terms:
        return []

    hits: list[RetrievalHit] = []
    for concept in memory.concepts.values():
        terms = _tokens(" ".join((concept.preferred_label, *concept.aliases, concept.definition)))
        matched = query_terms & terms
        if matched:
            hits.append(RetrievalHit("CONCEPT", concept.concept_id, len(matched) / len(query_terms), tuple(sorted(matched))))

    for definition in memory.metric_definitions.values():
        if not is_publishable_metric(definition, set(memory.profiles)):
            continue
        concept = memory.concepts.get(definition.concept_id)
        terms = _tokens(_metric_text(definition, concept))
        matched = query_terms & terms
        if matched:
            hits.append(RetrievalHit("METRIC_DEFINITION", definition.definition_id, len(matched) / len(query_terms), tuple(sorted(matched))))

    hits.sort(key=lambda hit: (-hit.score, hit.kind, hit.object_id))
    return hits[:limit]


def memory_from_layer(
    layer: SemanticLayer,
    concepts: dict[str, BusinessConcept],
    evidence: dict[str, Evidence] | None = None,
    profiles: dict[str, TableProfile] | None = None,
) -> AnalyticalMemory:
    """Create memory records from the current layer without losing provenance."""
    memory = AnalyticalMemory(
        concepts=dict(concepts), evidence=dict(evidence or {}), profiles=dict(profiles or {})
    )
    for index, metric in enumerate(layer.metrics):
        concept_id = metric.measure[1]
        if concept_id not in memory.concepts:
            continue
        definition_id = f"metric:{index}:{metric.measure[0].lower()}"
        evidence_ids = tuple(f"query:{source_ref}" for source_ref in metric.seen_in)
        definition = metric_definition_from_metric(
            metric, definition_id, concept_id, evidence_ids, profiles=profiles
        )
        memory.metric_definitions[definition_id] = definition
        for source_ref in metric.seen_in:
            evidence_id = f"query:{source_ref}"
            memory.evidence.setdefault(
                evidence_id,
                Evidence(evidence_id, "SQL_QUERY", source_ref),
            )
    return memory