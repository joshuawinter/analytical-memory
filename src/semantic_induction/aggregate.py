"""Stage 3 - aggregate per-query facts into corpus-level statistics."""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from semantic_induction.models import CorpusStats, QueryFacts, Role


def assign_roles(facts: QueryFacts) -> dict[str, set[Role]]:
    """Assign observed semantic roles to columns in one query."""
    roles: dict[str, set[Role]] = defaultdict(set)

    for edge in facts.join_edges:
        roles[edge.left].add(Role.KEY)
        roles[edge.right].add(Role.KEY)

    for aggregation in facts.aggregations:
        if aggregation.func in {"SUM", "AVG", "MIN", "MAX", "COUNT", "STDDEV"}:
            if aggregation.column != "*":
                roles[aggregation.column].add(Role.MEASURE)

    for column in facts.group_by:
        roles[column].add(Role.DIMENSION)

    for predicate in facts.predicates:
        if predicate.op in {"EQ", "IN"}:
            roles[predicate.column].add(Role.DIMENSION)
        if predicate.op in {"GT", "GTE", "LT", "LTE", "BETWEEN"}:
            roles[predicate.column].add(Role.ORDERED)

    return dict(roles)


def aggregate(facts_list: Iterable[QueryFacts]) -> CorpusStats:
    """Roll per-query facts into frequency-weighted corpus statistics."""
    edge_freq: Counter = Counter()
    role_freq: dict[str, Counter[Role]] = defaultdict(Counter)
    agg_freq: Counter[tuple[str, str]] = Counter()
    grain_freq: Counter[frozenset[str]] = Counter()
    pred_freq: Counter[tuple[str, str, str]] = Counter()
    table_freq: Counter[str] = Counter()

    for facts in facts_list:
        edge_freq.update(facts.join_edges)
        table_freq.update(facts.tables)
        grain = frozenset(facts.group_by)
        if grain:
            grain_freq[grain] += 1

        for column, roles in assign_roles(facts).items():
            role_freq[column].update(roles)
        agg_freq.update((item.func, item.column) for item in facts.aggregations)
        pred_freq.update(
            (item.column, item.op, item.value) for item in facts.predicates
        )

    return CorpusStats(
        edge_freq=edge_freq,
        role_freq=dict(role_freq),
        agg_freq=agg_freq,
        grain_freq=grain_freq,
        pred_freq=pred_freq,
        table_freq=table_freq,
    )