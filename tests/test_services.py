import duckdb

from semantic_induction.memory import AnalyticalMemory, BusinessConcept, MetricDefinition
from semantic_induction.labeling import LabelingStore
from semantic_induction.services import InvestigationService, investigation_payload


def test_service_serializes_approval_gate():
    store = LabelingStore(
        AnalyticalMemory(
            concepts={"sales.amount": BusinessConcept("sales.amount", "Sales", ("revenue",))},
            metric_definitions={
                "metric:sales": MetricDefinition(
                    "metric:sales", "sales.amount", ("SUM", "sales.amount"), (),
                    inferred_definition="Total sales.",
                )
            },
        )
    )
    connection = duckdb.connect()
    result = InvestigationService(store, {"sales": {"amount": "INTEGER"}}, connection).investigate("What is revenue?")
    payload = investigation_payload(result)

    assert payload["status"] == "NEEDS_REVIEW"
    assert payload["sql"] is None
