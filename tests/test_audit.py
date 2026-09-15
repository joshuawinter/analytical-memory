import json

import pytest

from semantic_induction.audit import AuditIntegrityError, AuditLedger


def test_audit_ledger_chains_events_and_detects_tampering(tmp_path):
    ledger = AuditLedger(tmp_path / "knowledge.audit.jsonl")
    first = ledger.append("KNOWLEDGE_DECISION", "finance-owner", {"decision": "APPROVE"})
    second = ledger.append("VOCABULARY_ENRICHMENT", "data-steward", {"alias": "net revenue"})

    assert second["previous_hash"] == first["event_hash"]
    assert ledger.verify() == second["event_hash"]

    events = ledger.events()
    events[0]["payload"]["decision"] = "REJECT"
    ledger.path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

    with pytest.raises(AuditIntegrityError, match="hash does not match"):
        ledger.verify()