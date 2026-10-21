"""Tier 5 - do human rulings outrank frequency?

ARCHITECTURE.md's Stage 4c says a resolved ruling "is durable and overrides
frequency". Until this harness that was asserted by construction, never
tested. Tier 5 builds a world where the majority of analyst queries encode
the wrong definition of a measure, the minority encode the right one, and a
hidden truth says so. It then checks four things against the real
investigation path, offline, with no model call:

1. With no ruling, the question is refused with the fork exposed. A silent
   answer from the majority signature is the failure that matters most; it
   is what frequency-ranked platform induction does.
2. Once a human approves the minority and rejects the majority, the answer
   is the minority's and matches the hidden truth by result equality.
3. Asked "as of" a moment before the ruling, the answer reverts to refusal.
4. A later, dated ruling that reverses the first wins after its own
   valid_from, the earlier answer stays reproducible before it, and the
   memory store's chain verifies with both versions readable.

Two counters are reported alongside pass/fail: how often the system answered
from frequency while a ruling for the other side was in force, and how often
it answered at all while contested with no ruling. Both must be zero.

Building this surfaced three gaps, all fixed in the same change: ``induce()``
merged rival signatures by predicate intersection so no fork ever reached
memory; ``investigate()`` ignored ``Resolution.valid_from``/``valid_to``; and
``LabelingStore`` kept only the head ruling, so supersession had no history
to read. See ``memory_from_layer(conflicts=...)``, ``LabelingStore.
resolution_as_of``, and ``investigate(as_of=...)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from semantic_induction.aggregate import aggregate
from semantic_induction.conflicts import detect_conflicts
from semantic_induction.extract import extract_corpus
from semantic_induction.induce import induce
from semantic_induction.ingest import ingest
from semantic_induction.investigate import investigate
from semantic_induction.labeling import LabelingStore
from semantic_induction.memory import BusinessConcept, memory_from_layer
from semantic_induction.models import Catalog
from semantic_induction.profile import profile_database
from semantic_induction.store import safe_segment
from semantic_induction.validate import compare_sql_to_answer

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_ROOT = ROOT / "data" / "tpcds" / "tier5"
DEFAULT_DDL = ROOT / "data" / "tpcds" / "ddl.sql"

QUESTION = "What is net paid revenue by year?"
MEASURE = ("SUM", "store_sales.ss_net_paid")
GRAIN = ("date_dim.d_year",)

# Fixed moments so the harness is deterministic. The first ruling takes
# effect in January; the reversal in April; probes sit before, between, after.
FIRST_RULING = datetime(2026, 1, 1, tzinfo=timezone.utc)
SECOND_RULING = datetime(2026, 4, 1, tzinfo=timezone.utc)
BEFORE_ANY = datetime(2025, 12, 1, tzinfo=timezone.utc)
BETWEEN = datetime(2026, 2, 1, tzinfo=timezone.utc)
AFTER_BOTH = datetime(2026, 5, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Tier5ScenarioResult:
    scenario_id: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Tier5Report:
    results: tuple[Tier5ScenarioResult, ...]
    answered_from_frequency: int
    answered_while_contested: int
    majority_definition_id: str
    minority_definition_id: str
    majority_support: int
    minority_support: int

    @property
    def passed(self) -> bool:
        return (
            all(result.passed for result in self.results)
            and self.answered_from_frequency == 0
            and self.answered_while_contested == 0
        )


@dataclass
class Tier5World:
    store: LabelingStore
    catalog: Catalog
    connection: Any
    truth_path: Path
    majority_id: str
    minority_id: str
    majority_support: int
    minority_support: int


def _run_sql_file(connection: Any, path: Path) -> None:
    # Drop `--` comment lines before splitting on `;` so prose in a comment
    # cannot be mistaken for a statement boundary.
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--")]
    for statement in "\n".join(lines).split(";"):
        if statement.strip():
            connection.execute(statement)


def build_world(
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    labels_path: Path | None = None,
    ddl_path: Path = DEFAULT_DDL,
) -> Tier5World:
    """Induce the fixture corpus into memory with the fork intact.

    ``labels_path`` is where rulings, the audit ledger, and the memory store
    land; scenario 4 reads the store's history, so it must be a real path.
    """
    if labels_path is None:
        raise ValueError("labels_path is required so the memory store and ledger are on disk")
    catalog, queries = ingest(ddl_path, fixture_root / "queries")
    facts = extract_corpus(queries, catalog)

    connection = duckdb.connect()
    _run_sql_file(connection, ddl_path)
    _run_sql_file(connection, fixture_root / "seed.sql")
    profiles = profile_database(connection, catalog, sample_size=5, top_values=5)

    layer = induce(aggregate(facts), catalog, facts, min_support=1, profiles=profiles)
    conflicts = detect_conflicts(layer, facts, min_support=1, profiles=profiles)
    concepts = {
        MEASURE[1]: BusinessConcept(
            MEASURE[1], "Revenue", ("net paid", "revenue"), "Net amount paid on store sales."
        )
    }
    memory = memory_from_layer(layer, concepts, profiles=profiles, conflicts=conflicts)
    store = LabelingStore(memory, labels_path)

    rivals = [
        definition
        for definition in memory.metric_definitions.values()
        if definition.measure == MEASURE and tuple(definition.grain) == GRAIN
    ]
    contested = [definition for definition in rivals if definition.conflict_id is not None]
    merged = [definition for definition in rivals if definition.conflict_id is None]
    if len(contested) != 2 or merged:
        raise RuntimeError(
            f"expected exactly two contested definitions and no merged one for {MEASURE}; "
            f"got contested={[d.definition_id for d in contested]} merged={[d.definition_id for d in merged]}"
        )
    contested.sort(key=lambda definition: -len(definition.evidence_ids))
    majority, minority = contested
    if not any(predicate.column.endswith("ss_quantity") for predicate in minority.default_filters):
        raise RuntimeError("the lower-support candidate should be the one carrying the ss_quantity predicate")

    return Tier5World(
        store=store,
        catalog=catalog,
        connection=connection,
        truth_path=fixture_root / "truth" / "revenue_by_year.csv",
        majority_id=majority.definition_id,
        minority_id=minority.definition_id,
        majority_support=len(majority.evidence_ids),
        minority_support=len(minority.evidence_ids),
    )


def run_tier5(fixture_root: Path = DEFAULT_FIXTURE_ROOT, labels_path: Path | None = None) -> Tier5Report:
    world = build_world(fixture_root, labels_path)
    store, catalog, connection = world.store, world.catalog, world.connection
    results: list[Tier5ScenarioResult] = []
    answered_from_frequency = 0
    answered_while_contested = 0
    both = {world.majority_id, world.minority_id}

    def ask(as_of: datetime | None = None):
        return investigate(QUESTION, store, catalog, connection, as_of=as_of)

    # 1. No ruling: refuse, expose the fork, never answer from the majority.
    result = ask()
    if result.status == "ANSWERED":
        answered_while_contested += 1
    passed = result.status == "NEEDS_REVIEW" and set(result.candidates) == both
    results.append(
        Tier5ScenarioResult(
            "no_ruling_refuses_with_fork_exposed",
            passed,
            f"status={result.status} candidates={sorted(result.candidates)}",
        )
    )

    # 2. Rule for the minority: the answer is the minority's and matches truth.
    store.label(
        world.minority_id, "APPROVE",
        "Finance recognizes revenue only on lines that sold. Voided and giveaway tickets "
        "carry a net_paid amount but no quantity and are excluded.",
        "finance-controller", valid_from=FIRST_RULING,
    )
    store.label(
        world.majority_id, "REJECT",
        "Sums voided and giveaway tickets. Widespread in saved queries because the "
        "original dashboard query omitted the quantity filter and was copied.",
        "finance-controller", valid_from=FIRST_RULING,
    )
    result = ask(BETWEEN)
    if result.status == "ANSWERED" and result.definition_id == world.majority_id:
        answered_from_frequency += 1
    match, actual_rows, expected_rows, error = (False, 0, 0, "no sql")
    if result.sql:
        match, actual_rows, expected_rows, error = compare_sql_to_answer(connection, result.sql, world.truth_path)
    passed = result.status == "ANSWERED" and result.definition_id == world.minority_id and match
    results.append(
        Tier5ScenarioResult(
            "ruling_for_minority_answers_and_matches_truth",
            passed,
            f"status={result.status} definition={result.definition_id} truth_match={match} "
            f"rows={actual_rows}/{expected_rows}" + (f" error={error}" if error else ""),
        )
    )

    # 3. Point in time: before the ruling, back to refusal with the fork.
    result = ask(BEFORE_ANY)
    if result.status == "ANSWERED":
        answered_while_contested += 1
    passed = result.status == "NEEDS_REVIEW" and set(result.candidates) == both
    results.append(
        Tier5ScenarioResult(
            "as_of_before_ruling_reverts_to_review",
            passed,
            f"status={result.status} candidates={sorted(result.candidates)}",
        )
    )

    # 4. Supersede: reverse the ruling from April. April onward answers the
    #    majority; February still answers the minority; the chain verifies.
    store.label(
        world.majority_id, "APPROVE",
        "Policy change effective Q2: gross ticket value is the reported revenue figure; "
        "voids are handled in a separate adjustment line.",
        "finance-controller", valid_from=SECOND_RULING,
    )
    store.label(
        world.minority_id, "REJECT",
        "Superseded by the Q2 policy; retained for pre-Q2 reporting.",
        "finance-controller", valid_from=SECOND_RULING,
    )
    after = ask(AFTER_BOTH)
    between = ask(BETWEEN)
    now = ask()
    if between.status == "ANSWERED" and between.definition_id == world.majority_id:
        answered_from_frequency += 1
    memory_store = store.memory_store
    verified = memory_store.verify() if memory_store is not None else 0
    minority_history = memory_store.history(f"resolutions/{safe_segment(world.minority_id)}") if memory_store else []
    versions_readable = all(
        memory_store.read_version(version.version_id) is not None for version in minority_history
    ) if memory_store else False
    decisions_in_history = [
        "APPROVE" if "decision: APPROVE" in (memory_store.read_version(v.version_id) or "") else "REJECT"
        for v in minority_history
    ] if memory_store else []
    passed = (
        after.status == "ANSWERED" and after.definition_id == world.majority_id
        and now.status == "ANSWERED" and now.definition_id == world.majority_id
        and between.status == "ANSWERED" and between.definition_id == world.minority_id
        and verified > 0
        and decisions_in_history == ["APPROVE", "REJECT"]
        and versions_readable
    )
    results.append(
        Tier5ScenarioResult(
            "superseding_ruling_wins_forward_and_history_stays_readable",
            passed,
            f"after={after.definition_id} between={between.definition_id} now={now.definition_id} "
            f"verified_versions={verified} minority_history={decisions_in_history}",
        )
    )

    return Tier5Report(
        results=tuple(results),
        answered_from_frequency=answered_from_frequency,
        answered_while_contested=answered_while_contested,
        majority_definition_id=world.majority_id,
        minority_definition_id=world.minority_id,
        majority_support=world.majority_support,
        minority_support=world.minority_support,
    )
