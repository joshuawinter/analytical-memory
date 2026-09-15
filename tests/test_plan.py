from pathlib import Path

from semantic_induction.aggregate import aggregate
from semantic_induction.compile import compile_metric
from semantic_induction.extract import extract_corpus
from semantic_induction.induce import induce
from semantic_induction.ingest import ingest
from semantic_induction.models import Dimension, Measure, Metric, Predicate, SemanticLayer
from semantic_induction.plan import MetricPlan, PlanValidationError, resolve_plan


ROOT = Path(__file__).parents[1]


def _layer():
    return SemanticLayer(
        measures={("SUM", "orders.amount"): Measure("orders.amount", "SUM", 3)},
        dimensions={"orders.status": Dimension("orders.status", 3)},
        metrics=[
            Metric(
                measure=("SUM", "orders.amount"),
                grain=frozenset({"orders.status"}),
                join_path=(),
                default_filters=(Predicate("orders.voided", "EQ", "false"),),
                support=3,
                seen_in=("q1", "q2", "q3"),
            )
        ],
    )


def test_resolves_plan_at_a_known_grain_and_keeps_invariant_filters():
    catalog = {"orders": {"amount": "DECIMAL", "status": "VARCHAR", "voided": "BOOLEAN"}}
    plan = MetricPlan(measure=("SUM", "orders.amount"), dimensions=("orders.status",))

    metric = resolve_plan(plan, _layer(), catalog)

    assert metric.grain == frozenset({"orders.status"})
    assert Predicate("orders.voided", "EQ", "false") in metric.default_filters


def test_plan_filters_narrow_but_do_not_replace_invariant_filters():
    catalog = {"orders": {"amount": "DECIMAL", "status": "VARCHAR", "voided": "BOOLEAN"}}
    plan = MetricPlan(
        measure=("SUM", "orders.amount"),
        dimensions=("orders.status",),
        filters=(Predicate("orders.status", "EQ", "OPEN"),),
    )

    metric = resolve_plan(plan, _layer(), catalog)

    assert Predicate("orders.voided", "EQ", "false") in metric.default_filters
    assert Predicate("orders.status", "EQ", "'OPEN'") in metric.default_filters


def test_plan_filter_on_a_date_column_is_rendered_as_a_safe_literal():
    catalog = {"orders": {"amount": "DECIMAL", "status": "VARCHAR", "shipdate": "DATE"}}
    plan = MetricPlan(
        measure=("SUM", "orders.amount"),
        dimensions=("orders.status",),
        filters=(Predicate("orders.shipdate", "LTE", "1998-09-02"),),
    )

    metric = resolve_plan(plan, _layer(), catalog)

    assert Predicate("orders.shipdate", "LTE", "DATE '1998-09-02'") in metric.default_filters


def test_plan_filter_on_the_same_column_and_op_as_an_invariant_is_dropped_not_duplicated():
    catalog = {"orders": {"amount": "DECIMAL", "status": "VARCHAR", "voided": "BOOLEAN"}}
    # The composer echoes back the invariant it was already given, rendered
    # through the plan's own literal formatting. This must not produce two
    # ANDed conditions on `orders.voided` in the compiled metric.
    plan = MetricPlan(
        measure=("SUM", "orders.amount"),
        dimensions=("orders.status",),
        filters=(Predicate("orders.voided", "EQ", "false"),),
    )

    metric = resolve_plan(plan, _layer(), catalog)

    voided_filters = [p for p in metric.default_filters if p.column == "orders.voided"]
    assert voided_filters == [Predicate("orders.voided", "EQ", "false")]


def test_plan_filter_with_non_numeric_value_on_a_numeric_column_is_rejected():
    catalog = {"orders": {"amount": "DECIMAL", "status": "VARCHAR"}}
    plan = MetricPlan(
        measure=("SUM", "orders.amount"),
        dimensions=("orders.status",),
        filters=(Predicate("orders.amount", "GT", "not-a-number"),),
    )

    try:
        resolve_plan(plan, _layer(), catalog)
        assert False, "expected PlanValidationError"
    except PlanValidationError as error:
        assert "not numeric" in str(error)


def test_plan_filter_with_unsupported_operator_is_rejected():
    catalog = {"orders": {"amount": "DECIMAL", "status": "VARCHAR"}}
    plan = MetricPlan(
        measure=("SUM", "orders.amount"),
        dimensions=("orders.status",),
        filters=(Predicate("orders.status", "IN", "OPEN"),),
    )

    try:
        resolve_plan(plan, _layer(), catalog)
        assert False, "expected PlanValidationError"
    except PlanValidationError as error:
        assert "unsupported filter operator" in str(error)


def test_rejects_measure_not_present_in_induced_layer():
    catalog = {"orders": {"amount": "DECIMAL"}}
    plan = MetricPlan(measure=("AVG", "orders.amount"))

    try:
        resolve_plan(plan, _layer(), catalog)
        assert False, "expected PlanValidationError"
    except PlanValidationError:
        pass


def test_rejects_grain_the_corpus_never_demonstrated():
    catalog = {"orders": {"amount": "DECIMAL", "status": "VARCHAR"}}
    plan = MetricPlan(measure=("SUM", "orders.amount"), dimensions=())

    try:
        resolve_plan(plan, _layer(), catalog)
        assert False, "expected PlanValidationError"
    except PlanValidationError as error:
        assert "known grains" in str(error)


def test_rejects_dimension_that_was_never_part_of_any_induced_grain():
    catalog = {"orders": {"amount": "DECIMAL", "status": "VARCHAR", "region": "VARCHAR"}}
    plan = MetricPlan(measure=("SUM", "orders.amount"), dimensions=("orders.region",))

    try:
        resolve_plan(plan, _layer(), catalog)
        assert False, "expected PlanValidationError"
    except PlanValidationError as error:
        assert "known grains" in str(error)


def test_end_to_end_plan_resolves_and_executes_against_induced_tpch_layer():
    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    facts = extract_corpus(queries, catalog)
    layer = induce(aggregate(facts), catalog, facts, min_support=2)

    target = next(metric for metric in layer.metrics if metric.grain)
    plan = MetricPlan(measure=target.measure, dimensions=tuple(target.grain))
    metric = resolve_plan(plan, layer, catalog)
    sql = compile_metric(metric, catalog)

    function, column = target.measure
    assert f'{function}("{column.split(".")[0]}"."{column.split(".")[1]}")' in sql
    assert metric.grain == frozenset(target.grain)


def test_resolves_grain_containing_key_dominant_columns():
    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    facts = extract_corpus(queries, catalog)
    layer = induce(aggregate(facts), catalog, facts, min_support=2)

    # q18's grain includes columns (e.g. customer.c_custkey) whose
    # corpus-wide dominant role is KEY, not DIMENSION. They must still be
    # proposable: the exact grain was demonstrated by a real, supported
    # metric signature, which is the only authority that matters here.
    target = next(
        metric
        for metric in layer.metrics
        if metric.grain and not all(column in layer.dimensions for column in metric.grain)
    )
    plan = MetricPlan(measure=target.measure, dimensions=tuple(target.grain))

    metric = resolve_plan(plan, layer, catalog)

    assert metric.grain == frozenset(target.grain)
