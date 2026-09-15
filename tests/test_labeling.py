from pathlib import Path

import pytest

from semantic_induction.labeling import LabelingError, LabelingStore
from semantic_induction.memory import BusinessConcept, Evidence, MetricDefinition, AnalyticalMemory
from semantic_induction.models import TableProfile


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


def test_review_items_surfaces_unstructured_candidates_flagged_not_dropped():
    # A grain column referencing a CTE alias ("tmp1") can't be safely
    # flattened into a governed measure/grain/filter definition -- it must
    # still reach the reviewer, flagged, rather than silently vanish the
    # way it did before this was fixed.
    memory = AnalyticalMemory(
        concepts={
            "sales": BusinessConcept("sales", "Sales"),
            "reviewed": BusinessConcept("reviewed", "Reviewed"),
        },
        evidence={"query:q1": Evidence("query:q1", "SQL_QUERY", "q1.sql")},
        # is_publishable_metric checks a grain/measure column's table against
        # the *profiled* table set, not the compile-time catalog -- "orders"
        # profiled but "tmp1" not is what makes the CTE reference detectable.
        profiles={"orders": TableProfile("orders", 10)},
        metric_definitions={
            "metric:unstructured": MetricDefinition(
                "metric:unstructured",
                "sales",
                ("SUM", "orders.amount"),
                ("tmp1.customer_id",),
                evidence_ids=("query:q1",),
            ),
            "metric:structured": MetricDefinition(
                "metric:structured",
                "reviewed",
                ("SUM", "orders.amount"),
                ("orders.customer_id",),
                evidence_ids=("query:q1",),
            ),
        },
    )
    store = LabelingStore(memory)

    items = {item["definition_id"]: item for item in store.review_items(catalog={"orders": {"amount": "DECIMAL"}})}

    assert items["metric:unstructured"]["structured"] is False
    assert items["metric:structured"]["structured"] is True