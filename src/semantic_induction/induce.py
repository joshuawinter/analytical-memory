"""Stage 4 - induce a structural semantic layer from corpus statistics."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from semantic_induction.models import (
    Catalog,
    CorpusStats,
    Dimension,
    Entity,
    Measure,
    Metric,
    Predicate,
    QueryFacts,
    Role,
    SemanticLayer,
    TableProfile,
)


def _table_of(column: str) -> str | None:
    return column.split(".", 1)[0] if "." in column else None


def _table_measure_counts(stats: CorpusStats) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for (_function, column), support in stats.agg_freq.items():
        table = _table_of(column)
        if table is not None:
            counts[table] += support
    return counts


def _table_join_degrees(stats: CorpusStats) -> dict[str, int]:
    degrees: dict[str, int] = defaultdict(int)
    for edge in stats.edge_freq:
        left_table = _table_of(edge.left)
        right_table = _table_of(edge.right)
        if left_table is not None:
            degrees[left_table] += 1
        if right_table is not None:
            degrees[right_table] += 1
    return degrees


def classify_entities(stats: CorpusStats, catalog: Catalog) -> dict[str, Entity]:
    """Classify physical tables using observed measures and join degree."""
    measure_counts = _table_measure_counts(stats)
    join_degrees = _table_join_degrees(stats)
    entities: dict[str, Entity] = {}
    for table in catalog:
        measures = measure_counts.get(table, 0)
        degree = join_degrees.get(table, 0)
        if measures > 0 and degree >= 2:
            kind = "FACT"
        elif measures == 0 and degree >= 2:
            kind = "CONFORMED_DIM"
        elif degree == 1:
            kind = "DIM"
        else:
            kind = "UNKNOWN"
        entities[table] = Entity(table=table, kind=kind)
    return entities


def _candidate_metrics(facts_list: Iterable[QueryFacts]) -> list[Metric]:
    candidates: dict[tuple[tuple[str, str], frozenset[str], frozenset[str]], list[QueryFacts]] = defaultdict(list)
    for facts in facts_list:
        grain = frozenset(facts.group_by)
        tables = frozenset(facts.tables)
        for aggregation in facts.aggregations:
            candidates[((aggregation.func, aggregation.column), grain, tables)].append(facts)

    metrics: list[Metric] = []
    for (measure, grain, _tables), queries in candidates.items():
        predicate_sets = [set(query.predicates) for query in queries]
        invariant_filters = tuple(sorted(set.intersection(*predicate_sets), key=str)) if predicate_sets else ()
        join_path = tuple(sorted({edge for query in queries for edge in query.join_edges}, key=str))
        metrics.append(
            Metric(
                measure=measure,
                grain=grain,
                join_path=join_path,
                default_filters=invariant_filters,
                support=len(queries),
                seen_in=tuple(query.query_id for query in queries),
            )
        )
    return metrics


def induce(
    stats: CorpusStats,
    catalog: Catalog,
    facts_list: Iterable[QueryFacts],
    min_support: int = 1,
    profiles: dict[str, TableProfile] | None = None,
) -> SemanticLayer:
    """Produce entities, measures, dimensions, and supported metric candidates.

    ``profiles`` is optional Stage 1b evidence (see ``profile.py``). When
    supplied, metrics whose join path would silently multiply grain rows
    are excluded -- see ``detect_fanout_risk`` for why a correlated
    ``EXISTS`` flattened into an ``INNER JOIN`` during extraction can look
    like a valid signature but compute a wrong, inflated aggregate.
    """
    if min_support < 1:
        raise ValueError("min_support must be at least 1")

    layer = SemanticLayer(entities=classify_entities(stats, catalog))
    for (aggregation, column), support in stats.agg_freq.items():
        if support >= min_support:
            layer.measures[(aggregation, column)] = Measure(column, aggregation, support)

    for column, roles in stats.role_freq.items():
        if roles and roles.most_common(1)[0][0] == Role.DIMENSION:
            layer.dimensions[column] = Dimension(column, sum(roles.values()))

    metrics = [metric for metric in _candidate_metrics(facts_list) if metric.support >= min_support]
    if profiles is not None:
        metrics = [metric for metric in metrics if not detect_fanout_risk(metric, profiles)]
    layer.metrics = metrics
    return layer


def _is_unique_key(profile: TableProfile, column: str) -> bool | None:
    """True if ``column`` has no duplicate non-null values in this table's profile.

    Returns None when the column was not profiled, so callers can treat
    unknown uniqueness conservatively rather than guessing.
    """
    column_profile = profile.columns.get(column)
    if column_profile is None:
        return None
    non_null = column_profile.row_count - column_profile.null_count
    if non_null <= 0:
        return None
    return column_profile.distinct_count >= non_null


def detect_fanout_risk(metric: Metric, profiles: dict[str, TableProfile]) -> bool:
    """True if this metric's join path can multiply rows without affecting its grain or measure.

    A join only duplicates rows relative to an already-anchored table when
    the *newly joined* table's own join column is not a unique key on that
    table (e.g. ``lineitem.l_orderkey``, where many rows share one order).
    Joining through a column that IS a unique key on its own table (e.g.
    ``supplier.s_suppkey``, ``nation.n_nationkey``) can never duplicate an
    anchored row, no matter how large that table is. Starting from the
    metric's own grain and measure tables as the anchor, this walks
    ``join_path`` to a fixed point; any edge that would introduce
    duplication into a table the metric does not itself group or
    aggregate by is a fan-out risk -- exactly what happens when a
    correlated ``EXISTS`` is flattened into an ``INNER JOIN`` during
    extraction.
    """
    measure_column = metric.measure[1]
    relevant_tables = {_table_of(column) for column in metric.grain}
    if measure_column != "*":
        relevant_tables.add(_table_of(measure_column))
    relevant_tables.discard(None)

    anchor = set(relevant_tables)
    remaining = list(metric.join_path)
    changed = True
    while changed and remaining:
        changed = False
        still_remaining = []
        for edge in remaining:
            left_table, _left_column = edge.left.split(".", 1)
            right_table, _right_column = edge.right.split(".", 1)
            if left_table in anchor and right_table in anchor:
                changed = True
                continue
            if left_table in anchor:
                other_table, other_column = right_table, edge.right.split(".", 1)[1]
            elif right_table in anchor:
                other_table, other_column = left_table, edge.left.split(".", 1)[1]
            else:
                still_remaining.append(edge)
                continue

            profile = profiles.get(other_table)
            unique = _is_unique_key(profile, other_column) if profile else None
            if unique is False and other_table not in relevant_tables:
                return True
            anchor.add(other_table)
            changed = True
        remaining = still_remaining

    # Any edge that never connected to the anchor set could not be
    # verified either way; treat as risky rather than silently trusting it.
    return bool(remaining)