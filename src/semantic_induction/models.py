"""Shared data model for the pipeline.

Mirrors the dataclasses sketched in ARCHITECTURE.md stages 1-3. Kept
dependency-free (stdlib dataclasses, not pydantic) because these objects are
produced in tight loops over every query in the corpus; pydantic is reserved
for the stage-4+ SemanticLayer, which is small and validated once.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class Role(Enum):
    KEY = auto()
    MEASURE = auto()
    DIMENSION = auto()
    ORDERED = auto()


@dataclass(frozen=True)
class JoinEdge:
    left: str  # qualified "table.column"
    right: str
    join_type: str  # INNER, LEFT, ...


@dataclass(frozen=True)
class Agg:
    func: str  # SUM, AVG, COUNT, ...
    column: str  # qualified "table.column"; "*" for COUNT(*)
    alias: str | None = None


@dataclass(frozen=True)
class Predicate:
    column: str  # qualified "table.column"
    op: str  # EQ, IN, GT, LT, BETWEEN, ...
    value: str  # literal repr, or "?"/param name for bind parameters


@dataclass
class Window:
    func: str
    partition_by: tuple[str, ...] = ()
    order_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class ColumnLineage:
    """Base columns contributing to one query-block output column."""

    sources: tuple[str, ...] = ()
    status: str = "SUPPORTED"  # SUPPORTED, PARTIAL, UNRESOLVED


@dataclass
class QueryBlock:
    """A local SELECT scope, such as the main query or a CTE."""

    block_id: str
    kind: str
    parent_id: str | None = None
    tables: set[str] = field(default_factory=set)
    output_lineage: dict[str, ColumnLineage] = field(default_factory=dict)


@dataclass(frozen=True)
class Correlation:
    """A predicate reference crossing from an inner scope to an outer scope."""

    scope_id: str
    inner_column: str
    outer_column: str
    operator: str


@dataclass(frozen=True)
class SetOperation:
    """A set operation connecting two query scopes."""

    operator: str  # UNION, UNION_ALL, INTERSECT, EXCEPT
    left_scope: str
    right_scope: str


@dataclass
class QueryFacts:
    query_id: str
    tables: set[str] = field(default_factory=set)
    join_edges: list[JoinEdge] = field(default_factory=list)
    aggregations: list[Agg] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    predicates: list[Predicate] = field(default_factory=list)
    projections: list[str] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    window_fns: list[Window] = field(default_factory=list)
    query_blocks: list[QueryBlock] = field(default_factory=list)
    column_lineage: dict[str, ColumnLineage] = field(default_factory=dict)
    correlations: list[Correlation] = field(default_factory=list)
    set_operations: list[SetOperation] = field(default_factory=list)


@dataclass
class Query:
    id: str
    ast: Any  # sqlglot.exp.Expression, qualified
    sql: str


# Table -> {column: type}
Catalog = dict[str, dict[str, str]]


@dataclass(frozen=True)
class ColumnProfile:
    """Bounded statistical evidence for one physical column."""

    table: str
    column: str
    row_count: int
    null_count: int
    distinct_count: int
    min_value: str | None = None
    max_value: str | None = None
    top_values: tuple[tuple[str, int], ...] = ()


@dataclass
class TableProfile:
    """Column statistics plus a bounded, queryable sample of table rows."""

    table: str
    row_count: int
    columns: dict[str, ColumnProfile] = field(default_factory=dict)
    sample_columns: tuple[str, ...] = ()
    sample_rows: tuple[tuple[Any, ...], ...] = ()


@dataclass(frozen=True)
class Provenance:
    """Origin and validity metadata shared by analytical and ETL artifacts."""

    artifact_id: str
    artifact_type: str
    source_system: str | None = None
    producer: str | None = None
    run_id: str | None = None
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


@dataclass(frozen=True)
class MappingRule:
    """A source-to-target transformation candidate from an integration workflow."""

    rule_id: str
    source_attributes: tuple[str, ...]
    target_attribute: str
    expression: Any
    operation: str = "MAP"
    provenance: Provenance | None = None


@dataclass(frozen=True)
class BusinessKeyMapping:
    source_key: tuple[str, ...]
    target_entity: str
    target_surrogate_key: str
    lookup_policy: str
    provenance: Provenance | None = None


@dataclass(frozen=True)
class TemporalPolicy:
    target_entity: str
    business_key: tuple[str, ...]
    effective_start: str
    effective_end: str
    current_flag: str | None = None
    history_type: str = "SCD2"


@dataclass(frozen=True)
class LoadBatch:
    batch_id: str
    source_system: str
    status: str
    source_watermark: str | None = None
    parent_batch_id: str | None = None
    provenance: Provenance | None = None


@dataclass(frozen=True)
class DataQualityOutcome:
    rule_id: str
    record_id: str
    disposition: str
    reason: str | None = None
    batch_id: str | None = None


@dataclass(frozen=True)
class TargetRowVersion:
    target_entity: str
    target_key: str
    business_key: tuple[str, ...]
    effective_start: str
    effective_end: str | None
    current: bool
    batch_id: str


@dataclass(frozen=True)
class Entity:
    table: str
    kind: str  # FACT, CONFORMED_DIM, DIM, UNKNOWN
    grain: tuple[str, ...] = ()


@dataclass(frozen=True)
class Measure:
    column: str
    aggregation: str
    support: int


@dataclass(frozen=True)
class Dimension:
    column: str
    support: int


@dataclass(frozen=True)
class Metric:
    measure: tuple[str, str]
    grain: frozenset[str]
    join_path: tuple[JoinEdge, ...]
    default_filters: tuple[Predicate, ...]
    support: int
    seen_in: tuple[str, ...]


@dataclass(frozen=True)
class Conflict:
    measure: tuple[str, str]
    grain: frozenset[str]
    candidates: tuple[Metric, ...]
    kind: str  # GRAIN_VARIATION, DEFINITIONAL, NORMATIVE
    materiality: float
    support: dict[str, int]


@dataclass(frozen=True)
class Ruling:
    conflict_id: str
    chosen: str | None
    rationale: str
    generalizes: bool
    ruled_by: str
    ruled_at: datetime
    valid_from: datetime
    supersedes: str | None = None


@dataclass(frozen=True)
class NamedDefinition:
    object_id: str
    name: str
    description: str
    source: str


@dataclass(frozen=True)
class CompilationAttempt:
    metric_id: str
    status: str  # COMPILED, UNSUPPORTED, FAILED
    features: tuple[str, ...] = ()
    rejection_reason: str | None = None
    generated_sql: str | None = None
    execution_ms: float | None = None
    result_match: bool | None = None


@dataclass(frozen=True)
class CompilationCoverage:
    attempts: tuple[CompilationAttempt, ...]

    @property
    def total(self) -> int:
        return len(self.attempts)

    @property
    def compiled(self) -> int:
        return sum(attempt.status == "COMPILED" for attempt in self.attempts)

    @property
    def unsupported(self) -> int:
        return sum(attempt.status == "UNSUPPORTED" for attempt in self.attempts)

    @property
    def failed(self) -> int:
        return sum(attempt.status == "FAILED" for attempt in self.attempts)


@dataclass
class SemanticLayer:
    """Structural Stage 4 output; naming and adjudication happen later."""

    entities: dict[str, Entity] = field(default_factory=dict)
    measures: dict[tuple[str, str], Measure] = field(default_factory=dict)
    dimensions: dict[str, Dimension] = field(default_factory=dict)
    metrics: list[Metric] = field(default_factory=list)
    names: dict[str, NamedDefinition] = field(default_factory=dict)


@dataclass
class CorpusStats:
    """Frequency-weighted statistics aggregated across query facts."""

    edge_freq: Counter[JoinEdge] = field(default_factory=Counter)
    role_freq: dict[str, Counter[Role]] = field(default_factory=dict)
    agg_freq: Counter[tuple[str, str]] = field(default_factory=Counter)
    grain_freq: Counter[frozenset[str]] = field(default_factory=Counter)
    pred_freq: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    table_freq: Counter[str] = field(default_factory=Counter)
