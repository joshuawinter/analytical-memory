from semantic_induction.conflicts import detect_conflicts, dimensional_catalog
from semantic_induction.models import Agg, Predicate, QueryFacts, SemanticLayer


def test_detects_same_grain_definitional_conflict():
    facts = [
        QueryFacts(
            "sales",
            aggregations=[Agg("SUM", "orders.amount")],
            predicates=[],
        ),
        QueryFacts(
            "completed_sales",
            aggregations=[Agg("SUM", "orders.amount")],
            predicates=[],
        ),
    ]
    facts[1].predicates.append(Predicate("orders.status", "EQ", "'COMPLETE'"))

    conflicts = detect_conflicts(SemanticLayer(), facts)

    assert len(conflicts) == 1
    assert conflicts[0].kind == "DEFINITIONAL"
    assert conflicts[0].measure == ("SUM", "orders.amount")


def test_grain_variation_alone_is_not_a_conflict():
    facts = [
        QueryFacts("daily", aggregations=[Agg("SUM", "orders.amount")], group_by=["date.day"]),
        QueryFacts("monthly", aggregations=[Agg("SUM", "orders.amount")], group_by=["date.month"]),
    ]

    conflicts = detect_conflicts(SemanticLayer(), facts)

    assert conflicts == []


def test_dimensional_catalog_captures_grains_conflict_detection_now_discards():
    facts = [
        QueryFacts("daily", aggregations=[Agg("SUM", "orders.amount")], group_by=["date.day"]),
        QueryFacts("monthly", aggregations=[Agg("SUM", "orders.amount")], group_by=["date.month"]),
    ]

    catalog = dimensional_catalog(facts)

    assert catalog == {
        ("SUM", "orders.amount"): frozenset({frozenset({"date.day"}), frozenset({"date.month"})}),
    }