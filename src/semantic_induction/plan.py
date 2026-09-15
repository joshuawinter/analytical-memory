"""Validate LLM-proposed metric plans against the induced semantic layer.

This is the boundary described in the architecture doc's Tier 3 design: the
LLM proposes a plan by naming induced objects it was given (a measure,
dimensions, optional narrowing filters). It never supplies join paths or
invariant filters -- those are resolved from the induced ``SemanticLayer``
only. ``resolve_plan`` either returns a ``Metric`` that ``compile_metric`` can
render unchanged, or raises, refusing to invent structure the corpus never
demonstrated.
"""
from __future__ import annotations

from dataclasses import dataclass

from semantic_induction.models import Catalog, Metric, Predicate, SemanticLayer


class PlanValidationError(ValueError):
    """Raised when a plan references structure the induced layer does not support."""


@dataclass(frozen=True)
class MetricPlan:
    """An LLM-proposed composition, referencing only named induced objects."""

    measure: tuple[str, str]  # (aggregation, column); must be an induced Measure
    dimensions: tuple[str, ...] = ()  # grain; validated against induced Metric grains, not Dimension objects
    filters: tuple[Predicate, ...] = ()  # narrowing filters with PLAIN values (e.g. "1998-09-02", not "'1998-09-02'" or a CAST) -- resolve_plan renders them into safe SQL literals


def _table_of(column: str) -> str | None:
    return column.split(".", 1)[0] if "." in column else None


_SCALAR_OPERATORS = {"EQ", "NEQ", "GT", "GTE", "LT", "LTE"}


def _escape_literal(value: object) -> str:
    return str(value).replace("'", "''")


def _render_literal(value: object, column_type: str) -> str:
    """Render a plain scalar value as a safe SQL literal for ``column_type``.

    A plan's filter value is untrusted, plain data (an LLM-proposed string,
    number, or boolean) -- never SQL text. This is the only place that
    literal is turned into SQL, so the composer never needs to (and cannot)
    hand-author quoting or casts itself.
    """
    kind = column_type.upper()
    if "TIMESTAMP" in kind:
        return f"TIMESTAMP '{_escape_literal(value)}'"
    if "DATE" in kind:
        return f"DATE '{_escape_literal(value)}'"
    if any(token in kind for token in ("INT", "DECIMAL", "DOUBLE", "FLOAT", "NUMERIC", "REAL")):
        try:
            float(value)
        except (TypeError, ValueError) as error:
            raise PlanValidationError(
                f"filter value is not numeric for column type {column_type!r}: {value!r}"
            ) from error
        return str(value)
    if "BOOL" in kind:
        lowered = str(value).strip().lower()
        if lowered not in {"true", "false"}:
            raise PlanValidationError(f"filter value is not boolean: {value!r}")
        return lowered
    return f"'{_escape_literal(value)}'"


def _render_plan_filter(predicate: Predicate, column_type: str) -> Predicate:
    if predicate.op not in _SCALAR_OPERATORS:
        raise PlanValidationError(
            f"unsupported filter operator for a plan-supplied value: {predicate.op!r}"
        )
    return Predicate(predicate.column, predicate.op, _render_literal(predicate.value, column_type))


def resolve_plan(plan: MetricPlan, layer: SemanticLayer, catalog: Catalog) -> Metric:
    """Resolve a plan into a compilable ``Metric``, or raise ``PlanValidationError``."""
    if plan.measure not in layer.measures:
        raise PlanValidationError(f"measure not in induced layer: {plan.measure!r}")

    # Dimension membership is not checked against layer.dimensions here: that
    # classification is corpus-wide dominant role and wrongly excludes a
    # column that is dominantly a join KEY but was still part of a real,
    # sufficiently-supported metric's grain (e.g. customer.c_custkey in
    # q18). The exact-grain match below is the authoritative check, since a
    # Metric only exists if that grain was actually observed.
    rendered_filters: list[Predicate] = []
    for predicate in plan.filters:
        table = _table_of(predicate.column)
        columns = catalog.get(table) if table else None
        if columns is None or predicate.column.split(".", 1)[1] not in columns:
            raise PlanValidationError(f"filter column not in catalog: {predicate.column!r}")
        column_type = columns[predicate.column.split(".", 1)[1]]
        rendered_filters.append(_render_plan_filter(predicate, column_type))

    requested_grain = frozenset(plan.dimensions)
    candidates = [metric for metric in layer.metrics if metric.measure == plan.measure]
    if not candidates:
        raise PlanValidationError(f"no induced metric signature for measure: {plan.measure!r}")

    matches = [metric for metric in candidates if metric.grain == requested_grain]
    if not matches:
        known_grains = sorted(tuple(sorted(metric.grain)) for metric in candidates)
        raise PlanValidationError(
            f"no induced signature for {plan.measure!r} at grain {sorted(requested_grain)!r}; "
            f"known grains: {known_grains!r}"
        )

    # Multiple signatures at the same grain would be a Stage 4b conflict;
    # with arbitration disregarded, the highest-support signature wins.
    base = max(matches, key=lambda metric: metric.support)

    # A plan filter on the same (column, op) as an existing invariant is
    # redundant, not narrowing: the corpus-derived invariant already defines
    # the metric on that column and is authoritative (see module docstring).
    # Keeping both would either duplicate an identical clause when the
    # composer's literal rendering happens to differ in surface form from
    # the invariant's (e.g. `DATE '1998-09-02'` vs `CAST('1998-09-02' AS
    # DATE)`, which are equal SQL but unequal strings, so a plain set union
    # would not dedupe them), or silently AND together two different values
    # on the same column with no error at all. Drop the plan-supplied one.
    base_columns_and_ops = {(predicate.column, predicate.op) for predicate in base.default_filters}
    narrowing_filters = tuple(
        predicate for predicate in rendered_filters
        if (predicate.column, predicate.op) not in base_columns_and_ops
    )
    return Metric(
        measure=plan.measure,
        grain=requested_grain,
        join_path=base.join_path,
        default_filters=tuple(sorted(set(base.default_filters) | set(narrowing_filters), key=str)),
        support=base.support,
        seen_in=base.seen_in,
    )
