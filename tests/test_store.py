import json
from pathlib import Path

import pytest

from semantic_induction.audit import AuditIntegrityError, AuditLedger
from semantic_induction.labeling import LabelingStore
from semantic_induction.memory import AnalyticalMemory, BusinessConcept, Evidence, MetricDefinition
from semantic_induction.store import (
    MemoryConflictError,
    MemoryStore,
    MemoryStoreError,
    content_sha256,
    parse_front_matter,
    render_entry,
    safe_segment,
)


def test_write_creates_immutable_versions_chained_into_the_ledger(tmp_path):
    store = MemoryStore(tmp_path / "memory")

    first = store.write("concepts/on-time", "# On time\n\nPromise date basis.\n", actor="finance-owner")
    second = store.write("concepts/on-time", "# On time\n\nRequest date basis.\n", actor="ops-owner")

    assert first.operation == "created" and second.operation == "modified"
    assert store.read("concepts/on-time") == "# On time\n\nRequest date basis.\n"
    assert store.read_version(first.version_id) == "# On time\n\nPromise date basis.\n"
    assert [version.actor for version in store.history("concepts/on-time")] == ["finance-owner", "ops-owner"]
    # the first object still exists untouched: nothing is updated in place
    assert (tmp_path / "memory" / "objects" / f"{first.content_sha256}.md").exists()
    assert store.verify() == 2
    assert store.ledger.events()[-1]["payload"]["previous_sha256"] == first.content_sha256


def test_optimistic_concurrency_rejects_stale_writers(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    head = store.write("concepts/revenue", "gross\n", actor="a")

    with pytest.raises(MemoryConflictError):
        store.write("concepts/revenue", "net\n", actor="b", expected_sha256="0" * 64)
    store.write("concepts/revenue", "net\n", actor="b", expected_sha256=head.content_sha256)
    assert store.read("concepts/revenue") == "net\n"


def test_editing_the_head_projection_outside_the_ledger_is_detected(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    store.write("concepts/revenue", "gross\n", actor="a")

    (tmp_path / "memory" / "entries" / "concepts" / "revenue.md").write_text("net\n", encoding="utf-8")

    with pytest.raises(AuditIntegrityError, match="edited outside the ledger"):
        store.verify()
    assert store.rebuild_projection() == 1
    assert store.verify() == 1


def test_tampering_with_an_object_is_detected(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    version = store.write("concepts/revenue", "gross\n", actor="a")

    (tmp_path / "memory" / "objects" / f"{version.content_sha256}.md").write_text("net\n", encoding="utf-8")

    with pytest.raises(AuditIntegrityError, match="does not match its hash"):
        store.verify()


def test_redaction_scrubs_content_but_keeps_who_and_when(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    leaked = store.write("notes/oops", "password: hunter2\n", actor="analyst")

    store.redact(leaked.version_id, actor="security", reason="credential leaked")

    assert store.read("notes/oops") is None
    assert store.read_version(leaked.version_id) is None
    history = store.history("notes/oops")
    assert history[0].redacted is True and history[0].actor == "analyst"
    assert "hunter2" not in (tmp_path / "memory" / "objects" / f"{leaked.content_sha256}.md").read_text()
    assert store.verify() == 1
    with pytest.raises(MemoryStoreError):
        store.redact(leaked.version_id, actor="security", reason="")


def test_delete_is_a_version_not_an_erasure(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    created = store.write("concepts/old", "retired metric\n", actor="a")
    store.delete("concepts/old", actor="steward")

    assert store.read("concepts/old") is None
    assert store.paths() == []
    assert store.read_version(created.version_id) == "retired metric\n"
    assert [version.operation for version in store.history("concepts/old")] == ["created", "deleted"]
    assert store.verify() == 2


def test_paths_are_normalized_and_cannot_escape_the_store(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    store.write("concepts//revenue", "x\n", actor="a")
    assert store.paths() == ["concepts/revenue.md"]
    with pytest.raises(MemoryStoreError):
        store.write("../outside", "x\n", actor="a")
    assert safe_segment("metric:3:sum") == "metric_3_sum"


def test_front_matter_round_trips_flat_metadata():
    content = render_entry(
        {"kind": "resolution", "decision": "APPROVE", "grain": ["orders.customer_id", "d.year"], "note": "has: colon", "empty": None},
        "# Body\n\ntext",
    )
    parsed = parse_front_matter(content)
    assert parsed == {"kind": "resolution", "decision": "APPROVE", "grain": ["orders.customer_id", "d.year"], "note": "has: colon"}
    assert content.endswith("# Body\n\ntext\n")


def _labeling_store(path: Path) -> LabelingStore:
    memory = AnalyticalMemory(
        concepts={"sales": BusinessConcept("sales", "Sales")},
        evidence={"query:q1": Evidence("query:q1", "SQL_QUERY", "q1.sql")},
        metric_definitions={
            "metric:sales": MetricDefinition(
                "metric:sales", "sales", ("SUM", "orders.amount"), ("orders.customer_id",), evidence_ids=("query:q1",)
            )
        },
    )
    return LabelingStore(memory, path)


def test_rulings_become_immutable_memory_entries_in_the_same_ledger(tmp_path):
    store = _labeling_store(tmp_path / "labels.json")

    first = store.label("metric:sales", "clarify", "Which amount column?", "analyst")
    store.label("metric:sales", "approve", "Finance confirmed gross amount.", "finance-owner")
    store.enrich("metric:sales", "Gross sales amount per customer.", "gross sales, GS")

    memory = store.memory_store
    assert memory is not None and memory.root == tmp_path / "labels.memory"
    entry = memory.read("resolutions/metric_sales")
    front = parse_front_matter(entry)
    assert front["decision"] == "APPROVE"
    assert front["decided_by"] == "finance-owner"
    assert front["supersedes"] == first.resolution_id
    assert "Gross sales amount per customer." in entry
    assert memory.read("vocabulary/metric_sales") is not None

    # three resolution versions (clarify, approve, re-render after enrichment) plus one vocabulary entry
    assert len(memory.history("resolutions/metric_sales")) == 3
    assert memory.verify() == 4

    # one chain: decisions and memory versions interleave in the same ledger
    events = [event["event_type"] for event in AuditLedger(tmp_path / "labels.audit.jsonl").events()]
    assert events == [
        "KNOWLEDGE_DECISION", "MEMORY_VERSION",
        "KNOWLEDGE_DECISION", "MEMORY_VERSION",
        "VOCABULARY_ENRICHMENT", "MEMORY_VERSION", "MEMORY_VERSION",
    ]
    # the clarify ruling is still readable from history even though it was superseded
    clarify = memory.history("resolutions/metric_sales")[0]
    assert "Which amount column?" in memory.read_version(clarify.version_id)


def test_ledger_tamper_is_caught_by_memory_verify(tmp_path):
    store = _labeling_store(tmp_path / "labels.json")
    store.label("metric:sales", "approve", "ok", "finance-owner")
    ledger_path = tmp_path / "labels.audit.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    events[0]["payload"]["decision"] = "REJECT"
    ledger_path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

    with pytest.raises(AuditIntegrityError):
        store.memory_store.verify()


def test_content_sha256_is_stable():
    assert content_sha256("a\n") == "87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7"
