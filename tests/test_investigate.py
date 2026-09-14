import duckdb

from semantic_induction.investigate import investigate
from semantic_induction.labeling import LabelingStore
from semantic_induction.memory import BusinessConcept, Evidence, MetricDefinition, AnalyticalMemory
from semantic_induction.models import Catalog


def _store(approved: bool) -> LabelingStore:
    memory = AnalyticalMemory(
        concepts={"sales.amount": BusinessConcept("sales.amount", "Sales", aliases=("revenue",))},
        evidence={"query:q1": Evidence("query:q1", "SQL_QUERY", "q1.sql")},
        metric_definitions={
            "metric:sales": MetricDefinition(
                "metric:sales", "sales.amount", ("SUM", "sales.amount"), (), evidence_ids=("query:q1",),
                inferred_definition="Total sales.",
            )
        },
    )
    store = LabelingStore(memory)
    if approved:
        store.label("metric:sales", "APPROVE", "Confirmed by finance.")
    return store


def test_investigate_requires_human_approval():
    connection = duckdb.connect()
    connection.execute("CREATE TABLE sales(amount INTEGER)")
    connection.execute("INSERT INTO sales VALUES (10), (20)")

    result = investigate("What is revenue?", _store(False), {"sales": {"amount": "INTEGER"}}, connection)

    assert result.status == "NEEDS_REVIEW"
    assert result.sql is None


def test_investigate_executes_only_the_approved_definition():
    connection = duckdb.connect()
    connection.execute("CREATE TABLE sales(amount INTEGER)")
    connection.execute("INSERT INTO sales VALUES (10), (20)")

    result = investigate("What is revenue?", _store(True), {"sales": {"amount": "INTEGER"}}, connection)

    assert result.status == "ANSWERED"
    assert result.rows == ((30,),)
    assert result.evidence[0].source_ref == "q1.sql"