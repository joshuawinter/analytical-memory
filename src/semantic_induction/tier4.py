"""Tier 4 - measure whether Stage 4b separates real conflicts from noise.

See ARCHITECTURE.md's Tier 4 section. Detection is a group-by; ranking and
classification are "the actual research problem, and the one that
determines whether anyone keeps using this." A handful of query pairs with
known ground truth -- some encode a genuine definitional disagreement, some
vary only grain, some are a known, accepted gap -- test whether
``detect_conflicts`` gets that classification right before trusting it on a
real, unlabeled corpus.

This is offline and deterministic: no LLM, no API key. It should run in the
main test suite, unlike Tier 3.
"""
from __future__ import annotations

from dataclasses import dataclass

from semantic_induction.models import Conflict


@dataclass(frozen=True)
class Tier4Scenario:
    """One labeled group of query IDs Stage 4b should (or should not) split
    into competing candidates.

    ``expect_conflict=True`` means the queries in ``query_ids`` are known to
    encode a genuine definitional disagreement and should end up as two or
    more separate candidates within a ``DEFINITIONAL`` conflict.
    ``expect_conflict=False`` covers both "these are simply the same
    definition" and "this is a known, accepted precision-over-recall gap" --
    Tier 4 reports which, it does not require every negative to be a clean
    non-issue.
    """

    scenario_id: str
    query_ids: frozenset[str]
    expect_conflict: bool
    description: str = ""


@dataclass(frozen=True)
class Tier4ScenarioResult:
    scenario_id: str
    expected: bool
    found: bool
    matched_kind: str | None
    description: str

    @property
    def correct(self) -> bool:
        return self.expected == self.found


@dataclass(frozen=True)
class Tier4Report:
    results: tuple[Tier4ScenarioResult, ...]

    @property
    def true_positives(self) -> int:
        return sum(1 for r in self.results if r.expected and r.found)

    @property
    def false_negatives(self) -> int:
        return sum(1 for r in self.results if r.expected and not r.found)

    @property
    def false_positives(self) -> int:
        return sum(1 for r in self.results if not r.expected and r.found)

    @property
    def true_negatives(self) -> int:
        return sum(1 for r in self.results if not r.expected and not r.found)

    def precision(self) -> float | None:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else None

    def recall(self) -> float | None:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else None

    def noise_rate(self) -> float | None:
        """Fraction of everything flagged as a real conflict that wasn't one."""
        flagged = self.true_positives + self.false_positives
        return self.false_positives / flagged if flagged else None


def run_tier4(conflicts: list[Conflict], scenarios: list[Tier4Scenario]) -> Tier4Report:
    """Check each labeled scenario against what Stage 4b actually detected.

    A scenario is "found" when some ``DEFINITIONAL`` conflict's candidates
    split the scenario's query IDs across two or more separate candidates --
    i.e. those queries actually ended up as competing signatures, not merged
    into one candidate or absent from ``conflicts`` entirely because the
    only difference detected was grain (see ``conflicts.dimensional_catalog``).
    """
    results = []
    for scenario in scenarios:
        found = False
        matched_kind: str | None = None
        for conflict in conflicts:
            candidate_hits = sum(
                1 for candidate in conflict.candidates if set(candidate.seen_in) & scenario.query_ids
            )
            if candidate_hits >= 2:
                matched_kind = conflict.kind
                if conflict.kind == "DEFINITIONAL":
                    found = True
                    break
        if matched_kind is None:
            for conflict in conflicts:
                seen = {query_id for candidate in conflict.candidates for query_id in candidate.seen_in}
                if seen & scenario.query_ids:
                    matched_kind = conflict.kind
                    break
        results.append(
            Tier4ScenarioResult(scenario.scenario_id, scenario.expect_conflict, found, matched_kind, scenario.description)
        )
    return Tier4Report(tuple(results))
