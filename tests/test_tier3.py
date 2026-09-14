from pathlib import Path

import duckdb

from semantic_induction.aggregate import aggregate
from semantic_induction.extract import extract_corpus
from semantic_induction.induce import induce
from semantic_induction.ingest import ingest
from semantic_induction.models import Dimension, Measure, Metric, Predicate, SemanticLayer
from semantic_induction.plan import MetricPlan
from semantic_induction.tier3 import (
    ArmResult,
    AnthropicPlanComposer,
    BusinessQuestion,
    INDUCED_LAYER,
    MockPlanComposer,
    MockSqlComposer,
    RAW_SCHEMA,
    Tier3Report,
    layer_vocabulary,
    run_induced_layer_arm,
    run_raw_schema_arm,
    run_tier3,
)


ROOT = Path(__file__).parents[1]


def _fabricated_layer_and_catalog():
    catalog = {"orders": {"amount": "DECIMAL", "status": "VARCHAR", "voided": "BOOLEAN"}}
    layer = SemanticLayer(
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
    return catalog, layer


def _write_answer(path: Path, header: str, rows: list[str]) -> None:
    path.write_text(header + "\n" + "\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


def test_report_match_rate_and_delta():
    report = Tier3Report(
        (
            ArmResult("q1", RAW_SCHEMA, True),
            ArmResult("q2", RAW_SCHEMA, False),
            ArmResult("q1", INDUCED_LAYER, True),
            ArmResult("q2", INDUCED_LAYER, True),
        )
    )

    assert report.match_rate(RAW_SCHEMA) == 0.5
    assert report.match_rate(INDUCED_LAYER) == 1.0
    assert report.delta() == 0.5


def test_layer_vocabulary_exposes_only_measures_and_dimensions():
    _catalog, layer = _fabricated_layer_and_catalog()

    vocabulary = layer_vocabulary(layer)

    assert set(vocabulary) == {"measures", "dimensions", "metric_signatures"}
    assert vocabulary["measures"] == [{"aggregation": "SUM", "column": "orders.amount", "support": 3}]
    assert vocabulary["dimensions"] == [{"column": "orders.status", "support": 3}]
    assert vocabulary["metric_signatures"] == [
        {
            "aggregation": "SUM",
            "column": "orders.amount",
            "dimensions": ["orders.status"],
            "support": 3,
        }
    ]


def test_raw_schema_arm_matches_and_reports_mismatch(tmp_path):
    connection = duckdb.connect()
    connection.execute("CREATE TABLE orders(amount DECIMAL(10, 2))")
    connection.execute("INSERT INTO orders VALUES (10), (20)")
    _write_answer(tmp_path / "correct.csv", "total", ["30.00"])
    _write_answer(tmp_path / "wrong.csv", "total", ["999.00"])

    composer = MockSqlComposer(
        {
            "correct": "SELECT SUM(amount) AS total FROM orders",
            "wrong": "SELECT SUM(amount) AS total FROM orders",
        }
    )
    questions = [BusinessQuestion("correct", "irrelevant"), BusinessQuestion("wrong", "irrelevant")]

    results = run_raw_schema_arm(questions, {"orders": {"amount": "DECIMAL"}}, composer, connection, tmp_path)

    by_id = {result.question_id: result for result in results}
    assert by_id["correct"].match is True
    assert by_id["wrong"].match is False


def test_raw_schema_arm_matches_when_only_column_order_differs(tmp_path):
    connection = duckdb.connect()
    connection.execute("CREATE TABLE orders(amount DECIMAL(10, 2), status VARCHAR)")
    connection.execute("INSERT INTO orders VALUES (10, 'OPEN'), (20, 'OPEN')")
    # Reference lists status first; the composer's SQL lists it last. Same
    # column names, different order -- this must still match.
    _write_answer(tmp_path / "q.csv", "status,metric_value", ["OPEN,30.00"])

    composer = MockSqlComposer(
        {"q": "SELECT SUM(amount) AS metric_value, status FROM orders GROUP BY status"}
    )
    question = BusinessQuestion("q", "irrelevant")

    results = run_raw_schema_arm(
        [question], {"orders": {"amount": "DECIMAL", "status": "VARCHAR"}}, composer, connection, tmp_path
    )

    assert results[0].match is True


def test_raw_schema_arm_rejects_genuinely_different_column_names(tmp_path):
    connection = duckdb.connect()
    connection.execute("CREATE TABLE orders(amount DECIMAL(10, 2))")
    connection.execute("INSERT INTO orders VALUES (10), (20)")
    _write_answer(tmp_path / "q.csv", "metric_value", ["30.00"])

    # The composer aliased the aggregate differently from what the
    # reference expects -- a real naming mismatch, not just reordering.
    composer = MockSqlComposer({"q": "SELECT SUM(amount) AS total_quantity FROM orders"})
    question = BusinessQuestion("q", "irrelevant")

    results = run_raw_schema_arm([question], {"orders": {"amount": "DECIMAL"}}, composer, connection, tmp_path)

    assert results[0].match is False
    assert "column names differ" in results[0].error


def test_induced_layer_arm_resolves_plan_and_executes(tmp_path):
    catalog, layer = _fabricated_layer_and_catalog()
    connection = duckdb.connect()
    connection.execute("CREATE TABLE orders(amount DECIMAL(10, 2), status VARCHAR, voided BOOLEAN)")
    connection.execute("INSERT INTO orders VALUES (10, 'OPEN', false), (20, 'OPEN', false), (5, 'OPEN', true)")
    _write_answer(tmp_path / "revenue_by_status.csv", "metric_value,status", ["30.00,OPEN"])

    question = BusinessQuestion("revenue_by_status", "What is revenue by order status?")
    composer = MockPlanComposer(
        {"revenue_by_status": MetricPlan(measure=("SUM", "orders.amount"), dimensions=("orders.status",))}
    )

    results = run_induced_layer_arm([question], layer, catalog, composer, connection, tmp_path)

    assert len(results) == 1
    assert results[0].match is True
    assert "orders.voided" not in (results[0].error or "")


def test_induced_layer_arm_reports_invalid_plan_as_mismatch_not_a_crash(tmp_path):
    catalog, layer = _fabricated_layer_and_catalog()
    connection = duckdb.connect()
    connection.execute("CREATE TABLE orders(amount DECIMAL(10, 2))")
    _write_answer(tmp_path / "bad.csv", "metric_value", ["0.00"])

    # AVG was never induced, and no grouping-free grain was ever observed --
    # this plan cannot be resolved without inventing structure.
    composer = MockPlanComposer({"bad": MetricPlan(measure=("AVG", "orders.amount"))})
    question = BusinessQuestion("bad", "irrelevant")

    results = run_induced_layer_arm([question], layer, catalog, composer, connection, tmp_path)

    assert results[0].match is False
    assert "not in induced layer" in results[0].error


def test_induced_layer_arm_matches_when_reference_columns_are_reordered(tmp_path):
    catalog, layer = _fabricated_layer_and_catalog()
    connection = duckdb.connect()
    connection.execute("CREATE TABLE orders(amount DECIMAL(10, 2), status VARCHAR, voided BOOLEAN)")
    connection.execute("INSERT INTO orders VALUES (10, 'OPEN', false), (20, 'OPEN', false)")
    # compile_metric always emits metric_value first, then grain columns.
    # The reference here lists status first -- same columns, different
    # order -- and must still match.
    _write_answer(tmp_path / "q.csv", "status,metric_value", ["OPEN,30.00"])

    question = BusinessQuestion("q", "irrelevant")
    composer = MockPlanComposer(
        {"q": MetricPlan(measure=("SUM", "orders.amount"), dimensions=("orders.status",))}
    )

    results = run_induced_layer_arm([question], layer, catalog, composer, connection, tmp_path)

    assert results[0].match is True


def test_run_tier3_combines_both_arms(tmp_path):
    catalog, layer = _fabricated_layer_and_catalog()
    connection = duckdb.connect()
    connection.execute("CREATE TABLE orders(amount DECIMAL(10, 2), status VARCHAR, voided BOOLEAN)")
    connection.execute("INSERT INTO orders VALUES (10, 'OPEN', false)")
    _write_answer(tmp_path / "q.csv", "metric_value,status", ["10.00,OPEN"])

    question = BusinessQuestion("q", "irrelevant")
    raw_composer = MockSqlComposer({"q": "SELECT SUM(amount) AS metric_value, status FROM orders GROUP BY status"})
    plan_composer = MockPlanComposer(
        {"q": MetricPlan(measure=("SUM", "orders.amount"), dimensions=("orders.status",))}
    )

    report = run_tier3([question], catalog, layer, connection, tmp_path, raw_composer, plan_composer)

    assert len(report.results) == 2
    assert report.match_rate(RAW_SCHEMA) == 1.0
    assert report.match_rate(INDUCED_LAYER) == 1.0


def test_end_to_end_against_real_induced_tpch_layer(tmp_path):
    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    facts = extract_corpus(queries, catalog)
    layer = induce(aggregate(facts), catalog, facts, min_support=1)

    # q1 is a single-table grouped aggregate with no join path -- the
    # cleanest real signature to execute against a small hand-built table.
    target = next(
        metric
        for metric in layer.metrics
        if metric.measure == ("SUM", "lineitem.l_quantity")
        and metric.grain == frozenset({"lineitem.l_returnflag", "lineitem.l_linestatus"})
    )

    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE lineitem(l_quantity DECIMAL(15, 2), l_returnflag VARCHAR, "
        "l_linestatus VARCHAR, l_shipdate DATE)"
    )
    connection.execute(
        "INSERT INTO lineitem VALUES (10, 'A', 'F', DATE '1998-01-01'), "
        "(5, 'A', 'F', DATE '1998-01-02'), (100, 'N', 'O', DATE '1999-01-01')"
    )
    _write_answer(tmp_path / "q1.csv", "metric_value,l_linestatus,l_returnflag", ["15.00,F,A"])

    question = BusinessQuestion("q1", "Summarize quantity shipped by return flag and line status.")
    composer = MockPlanComposer({"q1": MetricPlan(measure=target.measure, dimensions=tuple(target.grain))})

    results = run_induced_layer_arm([question], layer, catalog, composer, connection, tmp_path)

    assert results[0].match is True


def test_end_to_end_multi_join_signature_with_hidden_invariant_filter(tmp_path):
    """The q11-derived supply-cost-by-part-in-Germany signature: a real
    3-table join (partsupp -> supplier -> nation) plus a filter that is
    not implied by the schema. This is the discriminating question for
    the actual thesis, unlike the single-table q1 sanity check above --
    the induced-layer arm gets the join path and filter attached
    automatically from corpus-demonstrated structure; a raw-schema
    composer would have to derive both independently.
    """
    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    facts = extract_corpus(queries, catalog)
    layer = induce(aggregate(facts), catalog, facts, min_support=1)

    target = next(
        metric
        for metric in layer.metrics
        if metric.measure == ("SUM", "partsupp.ps_supplycost")
        and metric.grain == frozenset({"partsupp.ps_partkey"})
    )
    assert len(target.join_path) == 2  # partsupp->supplier, supplier->nation
    assert any(p.column == "nation.n_name" and p.value == "'GERMANY'" for p in target.default_filters)

    connection = duckdb.connect()
    connection.execute("CREATE TABLE nation(n_nationkey INTEGER, n_name VARCHAR)")
    connection.execute("CREATE TABLE supplier(s_suppkey INTEGER, s_nationkey INTEGER)")
    connection.execute(
        "CREATE TABLE partsupp(ps_partkey INTEGER, ps_suppkey INTEGER, ps_supplycost DECIMAL(15, 2))"
    )
    connection.execute("INSERT INTO nation VALUES (1, 'GERMANY'), (2, 'FRANCE')")
    connection.execute("INSERT INTO supplier VALUES (100, 1), (200, 2)")
    connection.execute(
        "INSERT INTO partsupp VALUES (10, 100, 5.00), (10, 200, 999.00), (20, 100, 3.00)"
    )
    _write_answer(tmp_path / "q.csv", "ps_partkey,metric_value", ["10,5.00", "20,3.00"])

    question = BusinessQuestion("q", "irrelevant")
    composer = MockPlanComposer({"q": MetricPlan(measure=target.measure, dimensions=tuple(target.grain))})

    results = run_induced_layer_arm([question], layer, catalog, composer, connection, tmp_path)

    assert results[0].match is True


def _fake_client(response_text: str):
    class Messages:
        def create(self, **request):
            return type("Response", (), {"content": [type("Block", (), {"text": response_text})()]})()

    class Client:
        messages = Messages()

    return Client()


def test_anthropic_plan_composer_accepts_flat_shape():
    composer = AnthropicPlanComposer(client=_fake_client(
        '{"aggregation":"SUM","column":"lineitem.l_extendedprice","dimensions":["lineitem.l_returnflag"],"filters":[]}'
    ))

    plan = composer.compose(BusinessQuestion("q", "irrelevant"), {"measures": [], "dimensions": []})

    assert plan.measure == ("SUM", "lineitem.l_extendedprice")
    assert plan.dimensions == ("lineitem.l_returnflag",)


def test_anthropic_plan_composer_accepts_nested_measure_object():
    composer = AnthropicPlanComposer(client=_fake_client(
        '{"measure":{"aggregation":"SUM","column":"lineitem.l_extendedprice"},"dimensions":[],"filters":[]}'
    ))

    plan = composer.compose(BusinessQuestion("q", "irrelevant"), {"measures": [], "dimensions": []})

    assert plan.measure == ("SUM", "lineitem.l_extendedprice")


def test_anthropic_plan_composer_accepts_measure_as_a_pair():
    composer = AnthropicPlanComposer(client=_fake_client(
        '{"measure":["SUM","lineitem.l_extendedprice"],"dimensions":[],"filters":[]}'
    ))

    plan = composer.compose(BusinessQuestion("q", "irrelevant"), {"measures": [], "dimensions": []})

    assert plan.measure == ("SUM", "lineitem.l_extendedprice")


def test_anthropic_plan_composer_error_includes_the_raw_response_for_debugging():
    composer = AnthropicPlanComposer(client=_fake_client('{"unexpected_key": "value"}'))

    try:
        composer.compose(BusinessQuestion("q", "irrelevant"), {"measures": [], "dimensions": []})
        assert False, "expected ValueError"
    except ValueError as error:
        assert "unexpected_key" in str(error)

