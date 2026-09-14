from semantic_induction.conflicts import detect_conflicts
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


def test_detects_grain_variation_without_treating_it_as_definitional():
    facts = [
        QueryFacts("daily", aggregations=[Agg("SUM", "orders.amount")], group_by=["date.day"]),
        QueryFacts("monthly", aggregations=[Agg("SUM", "orders.amount")], group_by=["date.month"]),
    ]

    conflicts = detect_conflicts(SemanticLayer(), facts)

    assert len(conflicts) == 1
    assert conflicts[0].kind == "GRAIN_VARIATION"