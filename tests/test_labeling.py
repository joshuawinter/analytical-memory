from pathlib import Path

import pytest

from semantic_induction.labeling import LabelingError, LabelingStore
from semantic_induction.memory import BusinessConcept, Evidence, MetricDefinition, AnalyticalMemory


def _store(path: Path | None = None) -> LabelingStore:
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


def test_label_persists_resolution_and_keeps_evidence(tmp_path):
    path = tmp_path / "labels.json"
    store = _store(path)

    resolution = store.label("metric:sales", "approve", "Matches the finance definition.", "analyst")

    assert resolution.decision == "APPROVE"
    assert store.memory.evidence["query:q1"].source_ref == "q1.sql"
    assert path.exists()

    reloaded = _store(path)
    reloaded.load()
    assert reloaded.memory.resolutions["metric:sales"].rationale == "Matches the finance definition."


def test_label_requires_valid_decision_and_rationale():
    store = _store()

    with pytest.raises(LabelingError):
        store.label("metric:sales", "maybe", "unclear")
    with pytest.raises(LabelingError):
        store.label("metric:sales", "APPROVE", "")