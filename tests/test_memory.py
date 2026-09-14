from semantic_induction.memory import (
    AnalyticalMemory,
    BusinessConcept,
    Evidence,
    MetricDefinition,
    is_publishable_metric,
    metric_definition_from_metric,
    retrieve,
)
from semantic_induction.models import JoinEdge, Metric, Predicate


def _memory() -> AnalyticalMemory:
    memory = AnalyticalMemory(
        concepts={
            "supply_cost": BusinessConcept(
                "supply_cost",
                "Supply Cost",
                aliases=("supplier cost",),
                definition="Cost paid to suppliers for supplied parts.",
            ),
            "part": BusinessConcept("part", "Part", aliases=("item", "SKU")),
        },
        evidence={"query:q11": Evidence("query:q11", "SQL_QUERY", "q11.sql")},
    )
    metric = Metric(
        measure=("SUM", "partsupp.ps_supplycost"),
        grain=frozenset({"partsupp.ps_partkey"}),
        join_path=(JoinEdge("partsupp.ps_suppkey", "supplier.s_suppkey", "INNER"),),
        default_filters=(Predicate("nation.n_name", "EQ", "GERMANY"),),
        support=3,
        seen_in=("q11",),
    )
    definition = metric_definition_from_metric(
        metric, "metric:supply_cost_per_part", "supply_cost", ("query:q11",)
    )
    memory.metric_definitions[definition.definition_id] = definition
    return memory


def test_retrieve_matches_aliases_and_physical_metric_terms():
    hits = retrieve("supplier cost in Germany", _memory())

    assert hits[0].kind == "METRIC_DEFINITION"
    assert hits[0].object_id == "metric:supply_cost_per_part"
    assert "germany" in hits[0].matched_terms

    concept_hits = retrieve("SKU", _memory())
    assert concept_hits[0].kind == "CONCEPT"
    assert concept_hits[0].object_id == "part"


def test_retrieve_is_deterministic_and_respects_limit():
    memory = _memory()

    assert retrieve("part", memory, limit=1) == retrieve("part", memory, limit=1)
    assert len(retrieve("part", memory, limit=1)) == 1
    assert retrieve("", memory) == []


def test_memory_record_preserves_metric_evidence_and_structure():
    definition = _memory().metric_definitions["metric:supply_cost_per_part"]

    assert definition.evidence_ids == ("query:q11",)
    assert definition.grain == ("partsupp.ps_partkey",)
    assert definition.default_filters[0].value == "GERMANY"
    assert "Total supply cost" in definition.inferred_definition
    assert "grouped by part key" in definition.inferred_definition


def test_memory_from_layer_uses_query_evidence_ids():
    from semantic_induction.memory import memory_from_layer
    from semantic_induction.models import SemanticLayer

    memory = memory_from_layer(
        SemanticLayer(
            metrics=[
                Metric(
                    ("SUM", "sales.amount"),
                    frozenset({"sales.customer_id"}),
                    (),
                    (),
                    1,
                    ("q1",),
                )
            ]
        ),
        {"sales.amount": BusinessConcept("sales.amount", "Sales")},
    )

    assert memory.metric_definitions["metric:0:sum"].evidence_ids == ("query:q1",)
    assert memory.evidence["query:q1"].source_ref == "q1"


def test_rejects_query_local_and_nested_predicate_metrics_from_publication():
    cte_metric = MetricDefinition(
        "metric:cte", "derived", ("SUM", "customer_total_return.amount"),
        ("customer_total_return.customer_id",),
    )
    nested_filter_metric = MetricDefinition(
        "metric:nested", "sales", ("SUM", "store_sales.ss_net_profit"),
        ("store.s_state",),
        default_filters=(Predicate("store.s_state", "IN", "(SELECT s_state FROM ranked)"),),
    )

    assert not is_publishable_metric(cte_metric, {"store_sales", "store"})
    assert not is_publishable_metric(nested_filter_metric, {"store_sales", "store"})