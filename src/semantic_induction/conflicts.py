"""Stage 4b - detect and rank competing induced metric signatures."""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from semantic_induction.models import Conflict, Metric, Predicate, QueryFacts, SemanticLayer, TableProfile

# A predicate on a column with this few distinct observed values or fewer is
# treated as potentially categorical/status-like (e.g. a return flag or an
# order status) even when it appears in only one query, because a status
# column is the kind of thing a business definition actually turns on.
_LOW_CARDINALITY_LIMIT = 12


def _metric_id(metric: Metric) -> str:
    return f"{metric.measure[0]}:{metric.measure[1]}:{','.join(sorted(metric.grain))}"


def _is_low_cardinality(predicate: Predicate, profiles: dict[str, TableProfile]) -> bool:
    if "." not in predicate.column:
        return True  # unqualified/derived column: no cardinality evidence, stay conservative
    table, column = predicate.column.split(".", 1)
    column_profile = profiles.get(table, TableProfile(table, 0)).columns.get(column)
    if column_profile is None:
        return True  # not profiled: no evidence to suppress it, stay conservative
    return column_profile.distinct_count <= _LOW_CARDINALITY_LIMIT


def _candidate_defining_predicates(
    population: list[QueryFacts],
    predicate_min_support: int,
    profiles: dict[str, TableProfile] | None,
) -> set[Predicate]:
    """Choose which observed predicates are worth treating as rival definitions.

    A literal filter that appears in only one query out of a population that
    otherwise agrees is ambiguous with a single observation: it might be a
    genuine definitional split (``status = 'COMPLETE'``), or it might be an
    incidental scoping choice for that one question (``d_year = 2000``,
    ``i_manufact_id = 128``). Recurrence across queries is one signal a split
    is real; a low-cardinality column (a flag, a status, a category -- the
    kind of thing a business definition actually turns on) is another, even
    at a single observation. A predicate on a high-cardinality column
    (dates, IDs) that neither recurs nor shows low cardinality is treated as
    a narrowing choice, not a competing definition -- see conflicts.py's
    module docstring and ARCHITECTURE.md's Stage 4b section on why flooding
    the queue with scoping differences is worse than missing one.
    """
    counts = Counter(predicate for facts in population for predicate in set(facts.predicates))
    kept: set[Predicate] = set()
    for predicate, count in counts.items():
        if count >= predicate_min_support:
            kept.add(predicate)
        elif profiles is None or _is_low_cardinality(predicate, profiles):
            kept.add(predicate)
    return kept


def _metrics_from_facts(
    facts_list: Iterable[QueryFacts],
    predicate_min_support: int = 2,
    profiles: dict[str, TableProfile] | None = None,
) -> list[Metric]:
    populations: dict[tuple[tuple[str, str], frozenset[str], frozenset[str]], list[QueryFacts]] = defaultdict(list)
    for facts in facts_list:
        grain = frozenset(facts.group_by)
        tables = frozenset(facts.tables)
        for aggregation in facts.aggregations:
            populations[((aggregation.func, aggregation.column), grain, tables)].append(facts)

    metrics: list[Metric] = []
    for (measure, grain, _tables), population in populations.items():
        candidate_defining = _candidate_defining_predicates(population, predicate_min_support, profiles)
        signatures: dict[frozenset[Predicate], list[QueryFacts]] = defaultdict(list)
        for facts in population:
            kept = frozenset(predicate for predicate in facts.predicates if predicate in candidate_defining)
            signatures[kept].append(facts)

        for kept_filters, queries in signatures.items():
            joins = tuple(sorted({edge for query in queries for edge in query.join_edges}, key=str))
            metrics.append(
                Metric(
                    measure=measure,
                    grain=grain,
                    join_path=joins,
                    default_filters=tuple(sorted(kept_filters, key=str)),
                    support=len(queries),
                    seen_in=tuple(query.query_id for query in queries),
                )
            )
    return metrics


def detect_conflicts(
    layer: SemanticLayer,
    facts_list: Iterable[QueryFacts],
    min_support: int = 1,
    predicate_min_support: int = 2,
    profiles: dict[str, TableProfile] | None = None,
) -> list[Conflict]:
    """Return ranked competing metric signatures.

    ``profiles`` is optional Stage 1b evidence (see ``profile.py``). When
    supplied, a one-off literal filter on a high-cardinality column (a date,
    an ID) is treated as a narrowing choice rather than a rival definition
    unless it recurs -- see ``_candidate_defining_predicates``. Without
    profiles, every observed filter difference is conservatively treated as
    candidate-defining, matching the prior behavior.

    Materiality is currently a deterministic support/divergence proxy. An
    execution-backed scorer can replace it once metric compilation exists.
    """
    if min_support < 1:
        raise ValueError("min_support must be at least 1")

    metrics = [
        metric
        for metric in _metrics_from_facts(facts_list, predicate_min_support, profiles)
        if metric.support >= min_support
    ]
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