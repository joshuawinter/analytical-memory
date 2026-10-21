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

import json
from dataclasses import dataclass
from pathlib import Path

from semantic_induction.models import Conflict, TableProfile


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

    ``known_gap`` marks a scenario whose label is set against what the
    current classifier is expected to do. It still counts in precision and
    recall (the label is the truth, not the classifier); it only lets the
    test suite distinguish "the classifier regressed" from "the classifier
    is exactly as imprecise as documented".
    """

    scenario_id: str
    query_ids: frozenset[str]
    expect_conflict: bool
    description: str = ""
    known_gap: bool = False


@dataclass(frozen=True)
class Tier4ScenarioResult:
    scenario_id: str
    expected: bool
    found: bool
    matched_kind: str | None
    description: str
    known_gap: bool = False

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

    @property
    def unexpected_failures(self) -> tuple[Tier4ScenarioResult, ...]:
        """Misclassifications not covered by a documented known gap: regressions."""
        return tuple(r for r in self.results if not r.correct and not r.known_gap)

    @property
    def surprising_passes(self) -> tuple[Tier4ScenarioResult, ...]:
        """Known gaps the classifier got right anyway: the documentation is stale."""
        return tuple(r for r in self.results if r.correct and r.known_gap)

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
            Tier4ScenarioResult(
                scenario.scenario_id, scenario.expect_conflict, found, matched_kind, scenario.description, scenario.known_gap
            )
        )
    return Tier4Report(tuple(results))


# ---------------------------------------------------------------------------
# Generated corpus: one isolated scenario per directory, labelled semantically.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratedScenario:
    scenario_id: str
    family: str
    directory: Path
    expect_conflict: bool
    expect_conflict_without_profiles: bool
    known_gap: bool
    known_gap_without_profiles: bool
    rationale: str
    query_ids: tuple[str, ...]


def load_generated_scenarios(root: Path) -> list[GeneratedScenario]:
    """Read ``manifest.json`` written by ``scripts/build_tier4_corpus.py``."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return [
        GeneratedScenario(
            scenario_id=item["scenario_id"],
            family=item["family"],
            directory=root / item["scenario_id"],
            expect_conflict=bool(item["expect_conflict"]),
            expect_conflict_without_profiles=bool(item["expect_conflict_without_profiles"]),
            known_gap=bool(item["known_gap"]),
            known_gap_without_profiles=bool(item.get("known_gap_without_profiles", item["known_gap"])),
            rationale=item["rationale"],
            query_ids=tuple(item["query_ids"]),
        )
        for item in manifest["scenarios"]
    ]


def run_generated_tier4(
    root: Path,
    ddl_path: Path,
    profiles: dict[str, TableProfile] | None,
) -> Tier4Report:
    """Run Stage 4b over each generated scenario as its own corpus.

    Isolation matters: predicate recurrence is counted within a population,
    so a filter that recurs across two scenarios must not make either look
    contested. ``profiles`` (Stage 1b evidence for the whole TPC-DS catalog)
    is shared; the label used is ``expect_conflict`` when profiles are
    supplied and ``expect_conflict_without_profiles`` otherwise, because the
    classifier's documented behaviour differs between the two modes.
    """
    from semantic_induction.conflicts import detect_conflicts
    from semantic_induction.extract import extract_corpus
    from semantic_induction.ingest import ingest

    results: list[Tier4ScenarioResult] = []
    for scenario in load_generated_scenarios(root):
        catalog, queries = ingest(ddl_path, scenario.directory)
        facts = extract_corpus(queries, catalog)
        conflicts = detect_conflicts(None, facts, min_support=1, profiles=profiles)
        expected = scenario.expect_conflict if profiles is not None else scenario.expect_conflict_without_profiles
        known_gap = scenario.known_gap if profiles is not None else scenario.known_gap_without_profiles
        labelled = Tier4Scenario(
            scenario.scenario_id,
            frozenset(query.id for query in queries),
            expected,
            f"[{scenario.family}] {scenario.rationale}",
            known_gap,
        )
        results.extend(run_tier4(conflicts, [labelled]).results)
    return Tier4Report(tuple(results))
