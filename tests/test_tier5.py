"""Tier 5 (rulings outrank frequency) and the mechanics it forced into existence."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import duckdb

from semantic_induction.investigate import investigate
from semantic_induction.labeling import LabelingStore
from semantic_induction.memory import (
    AnalyticalMemory,
    BusinessConcept,
    Evidence,
    MetricDefinition,
    memory_from_layer,
)
from semantic_induction.models import Conflict, Metric, Predicate, SemanticLayer
from semantic_induction.tier5 import QUESTION, build_world, run_tier5


def test_tier5_all_scenarios_pass_and_counters_are_zero(tmp_path):
    report = run_tier5(labels_path=tmp_path / "labels.json")

    failures = [(r.scenario_id, r.detail) for r in report.results if not r.passed]
    assert not failures, failures
    assert report.answered_from_frequency == 0
    assert report.answered_while_contested == 0
    assert report.majority_support == 10 and report.minority_support == 3
    assert report.passed


def test_tier5_world_has_a_fork_and_no_merged_definition(tmp_path):
    world = build_world(labels_path=tmp_path / "labels.json")

    definitions = world.store.memory.metric_definitions
    majority, minority = definitions[world.majority_id], definitions[world.minority_id]
    assert majority.conflict_id == minority.conflict_id is not None
    assert majority.status == minority.status == "CONTESTED"
    assert majority.default_filters == ()
    assert [p.column for p in minority.default_filters] == ["store_sales.ss_quantity"]
    # Frequency alone would have produced exactly the majority's definition.
    merged = [d for d in definitions.values() if d.measure == majority.measure and d.conflict_id is None]
    assert merged == []


def _fabricated_conflict():
    majority = Metric(("SUM", "sales.amount"), frozenset({"sales.year"}), (), (), 5, ("q1", "q2", "q3", "q4", "q5"))
    minority = Metric(
        ("SUM", "sales.amount"), frozenset({"sales.year"}), (),
        (Predicate("sales.voided", "EQ", "false"),), 2, ("q6", "q7"),
    )
    merged = Metric(("SUM", "sales.amount"), frozenset({"sales.year"}), (), (), 7, tuple(f"q{i}" for i in range(1, 8)))
    conflict = Conflict(("SUM", "sales.amount"), frozenset({"sales.year"}), (minority, majority), "DEFINITIONAL", 7.0, {})
    return merged, conflict


def test_memory_from_layer_replaces_merged_definition_with_contested_candidates():
    merged, conflict = _fabricated_conflict()
    concepts = {"sales.amount": BusinessConcept("sales.amount", "Sales")}

    without = memory_from_layer(SemanticLayer(metrics=[merged]), concepts)
    with_fork = memory_from_layer(SemanticLayer(metrics=[merged]), concepts, conflicts=[conflict])

    assert list(without.metric_definitions) == ["metric:0:sum"]
    assert without.metric_definitions["metric:0:sum"].default_filters == ()
    ids = sorted(with_fork.metric_definitions)
    assert ids == [
        "conflict:sum:sales.amount:sales.year:candidate:0",
        "conflict:sum:sales.amount:sales.year:candidate:1",
    ]
    first, second = (with_fork.metric_definitions[i] for i in ids)
    assert first.evidence_ids == ("query:q1", "query:q2", "query:q3", "query:q4", "query:q5")  # higher support first
    assert second.default_filters[0].column == "sales.voided"
    assert {d.conflict_id for d in (first, second)} == {"conflict:sum:sales.amount:sales.year"}
    assert "query:q7" in with_fork.evidence


def _contested_store(path=None) -> LabelingStore:
    memory = AnalyticalMemory(
        concepts={"sales.amount": BusinessConcept("sales.amount", "Sales", aliases=("revenue",))},
        evidence={"query:q1": Evidence("query:q1", "SQL_QUERY", "q1.sql")},
        metric_definitions={
            "c:0": MetricDefinition("c:0", "sales.amount", ("SUM", "sales.amount"), (), evidence_ids=("query:q1",), conflict_id="c"),
            "c:1": MetricDefinition(
                "c:1", "sales.amount", ("SUM", "sales.amount"), (),
                default_filters=(Predicate("sales.voided", "EQ", "false"),), evidence_ids=("query:q1",), conflict_id="c",
            ),
        },
    )
    return LabelingStore(memory, path)


def _connection():
    connection = duckdb.connect()
    connection.execute("CREATE TABLE sales(amount INTEGER, voided BOOLEAN)")
    connection.execute("INSERT INTO sales VALUES (10, false), (20, false), (5, true)")
    return connection


def test_investigate_exposes_fork_when_contested_and_unruled():
    result = investigate("What is revenue?", _contested_store(), {"sales": {"amount": "INTEGER", "voided": "BOOLEAN"}}, _connection())

    assert result.status == "NEEDS_REVIEW"
    assert set(result.candidates) == {"c:0", "c:1"}
    assert "frequency" in (result.message or "")


def test_investigate_answers_from_ruling_as_of_and_reverts_before_it():
    store = _contested_store()
    catalog = {"sales": {"amount": "INTEGER", "voided": "BOOLEAN"}}
    connection = _connection()
    effective = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.label("c:1", "APPROVE", "Exclude voided sales.", "finance", valid_from=effective)

    ruled = investigate("What is revenue?", store, catalog, connection, as_of=effective + timedelta(days=1))
    before = investigate("What is revenue?", store, catalog, connection, as_of=effective - timedelta(days=1))

    assert ruled.status == "ANSWERED" and ruled.definition_id == "c:1" and ruled.rows == ((30,),)
    assert before.status == "NEEDS_REVIEW" and set(before.candidates) == {"c:0", "c:1"}


def test_resolution_as_of_picks_latest_effective_ruling_and_keeps_history():
    store = _contested_store()
    january = datetime(2026, 1, 1, tzinfo=timezone.utc)
    april = datetime(2026, 4, 1, tzinfo=timezone.utc)
    first = store.label("c:1", "APPROVE", "first", "finance", valid_from=january)
    second = store.label("c:1", "REJECT", "reversed", "finance", valid_from=april)

    assert store.resolution_as_of("c:1", january - timedelta(days=1)) is None
    assert store.resolution_as_of("c:1", january + timedelta(days=1)) == first
    assert store.resolution_as_of("c:1", april + timedelta(days=1)) == second
    assert [r.resolution_id for r in store.history["c:1"]] == ["resolution:c:1:1", "resolution:c:1:2"]
    # A future-dated ruling does not displace the head until its time comes.
    store.label("c:1", "APPROVE", "next year", "finance", valid_from=datetime(2099, 1, 1, tzinfo=timezone.utc))
    assert store.memory.resolutions["c:1"] == second


def test_labels_file_round_trips_history_and_reads_the_old_flat_layout(tmp_path):
    path = tmp_path / "labels.json"
    store = _contested_store(path)
    january = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store.label("c:1", "APPROVE", "first", "finance", valid_from=january)
    store.label("c:1", "REJECT", "reversed", "finance", valid_from=datetime(2026, 4, 1, tzinfo=timezone.utc))

    reloaded = _contested_store(path)
    reloaded.load()
    assert [r.decision for r in reloaded.history["c:1"]] == ["APPROVE", "REJECT"]
    assert reloaded.resolution_as_of("c:1", january + timedelta(days=1)).decision == "APPROVE"
    assert reloaded.memory.resolutions["c:1"].decision == "REJECT"

    # Pre-history files: one flat resolution per definition, no format marker.
    old = tmp_path / "old_labels.json"
    old.write_text(json.dumps({
        "c:0": {
            "resolution_id": "resolution:c:0:1", "target_id": "c:0", "decision": "APPROVE",
            "rationale": "legacy", "decided_by": "analyst", "decided_at": "2025-06-01T00:00:00+00:00",
            "valid_from": None, "valid_to": None,
        }
    }), encoding="utf-8")
    legacy = _contested_store(old)
    legacy.load()
    assert legacy.memory.resolutions["c:0"].rationale == "legacy"
    assert legacy.resolution_as_of("c:0").decision == "APPROVE"
    assert legacy.resolution_as_of("c:0", datetime(2025, 1, 1, tzinfo=timezone.utc)) is None
