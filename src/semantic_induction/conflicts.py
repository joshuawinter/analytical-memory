"""Stage 4b - detect and rank competing induced metric signatures."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from semantic_induction.models import Conflict, Metric, QueryFacts, SemanticLayer


def _metric_id(metric: Metric) -> str:
    return f"{metric.measure[0]}:{metric.measure[1]}:{','.join(sorted(metric.grain))}"


def _metrics_from_facts(facts_list: Iterable[QueryFacts]) -> list[Metric]:
    signatures: dict[tuple[tuple[str, str], frozenset[str], frozenset[str], frozenset], list[QueryFacts]] = defaultdict(list)
    for facts in facts_list:
        grain = frozenset(facts.group_by)
        tables = frozenset(facts.tables)
        filters = frozenset(facts.predicates)
        joins = frozenset(facts.join_edges)
        for aggregation in facts.aggregations:
            signatures[((aggregation.func, aggregation.column), grain, tables, filters | joins)].append(facts)

    metrics: list[Metric] = []
    for (measure, grain, _tables, _signature), queries in signatures.items():
        joins = tuple(sorted({edge for query in queries for edge in query.join_edges}, key=str))
        filters = tuple(sorted({predicate for query in queries for predicate in query.predicates}, key=str))
        metrics.append(
            Metric(
                measure=measure,
                grain=grain,
                join_path=joins,
                default_filters=filters,
                support=len(queries),
                seen_in=tuple(query.query_id for query in queries),
            )
        )
    return metrics


def detect_conflicts(
    layer: SemanticLayer,
    facts_list: Iterable[QueryFacts],
    min_support: int = 1,
) -> list[Conflict]:
    """Return ranked competing metric signatures.

    Materiality is currently a deterministic support/divergence proxy. An
    execution-backed scorer can replace it once metric compilation exists.
    """
    if min_support < 1:
        raise ValueError("min_support must be at least 1")

    metrics = [metric for metric in _metrics_from_facts(facts_list) if metric.support >= min_support]
    by_measure: dict[tuple[str, str], list[Metric]] = defaultdict(list)
    for metric in metrics:
        by_measure[metric.measure].append(metric)

    conflicts: list[Conflict] = []
    for measure, candidates in by_measure.items():
        grains = {candidate.grain for candidate in candidates}
        if len(grains) > 1:
            for grain in grains:
                grain_candidates = tuple(candidate for candidate in candidates if candidate.grain == grain)
                if len(grain_candidates) > 1:
                    conflicts.append(_conflict(measure, grain, grain_candidates, "DEFINITIONAL"))
            conflicts.append(
                _conflict(measure, frozenset(), tuple(candidates), "GRAIN_VARIATION")
            )
            continue
        if len(candidates) > 1:
            grain = next(iter(grains), frozenset())
            conflicts.append(_conflict(measure, grain, tuple(candidates), "DEFINITIONAL"))
    return sorted(conflicts, key=lambda conflict: conflict.materiality, reverse=True)


def _conflict(
    measure: tuple[str, str],
    grain: frozenset[str],
    candidates: tuple[Metric, ...],
    kind: str,
) -> Conflict:
    support = {_metric_id(candidate): candidate.support for candidate in candidates}
    materiality = sum(support.values()) * max(1, len(candidates) - 1)
    return Conflict(measure, grain, candidates, kind, float(materiality), support)