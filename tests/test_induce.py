from pathlib import Path

from semantic_induction.aggregate import aggregate
from semantic_induction.extract import extract_corpus
from semantic_induction.induce import classify_entities, detect_fanout_risk, induce
from semantic_induction.ingest import ingest
from semantic_induction.models import Agg, ColumnProfile, JoinEdge, Metric, QueryFacts, TableProfile


ROOT = Path(__file__).parents[1]


def _corpus():
    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    facts = extract_corpus(queries, catalog)
    return catalog, facts, aggregate(facts)


def test_induces_structural_entities_measures_and_dimensions():
    catalog, facts, stats = _corpus()

    layer = induce(stats, catalog, facts, min_support=2)

    assert layer.entities["lineitem"].kind == "FACT"
    assert layer.entities["nation"].kind in {"DIM", "CONFORMED_DIM"}
    assert ("SUM", "lineitem.l_extendedprice") in layer.measures
    assert "lineitem.l_returnflag" in layer.dimensions
    assert all(metric.support >= 2 for metric in layer.metrics)


def test_induce_canonicalizes_inner_join_edge_direction_across_queries():
    # Two queries express the same equi-join with the sides written in
    # opposite order (`l.l_partkey = p.p_partkey` vs the reverse). For an
    # INNER join that is the identical condition; without canonicalizing
    # direction, a metric compiled from both queries' merged join_path
    # would render the same join twice.
    catalog = {
        "lineitem": {"l_extendedprice": "DECIMAL(15,2)", "l_partkey": "BIGINT"},
        "part": {"p_partkey": "BIGINT"},
    }
    facts = [
        QueryFacts(
            query_id="q_a",
            tables={"lineitem", "part"},
            join_edges=[JoinEdge("lineitem.l_partkey", "part.p_partkey", "INNER")],
            aggregations=[Agg("SUM", "lineitem.l_extendedprice")],
        ),
        QueryFacts(
            query_id="q_b",
            tables={"lineitem", "part"},
            join_edges=[JoinEdge("part.p_partkey", "lineitem.l_partkey", "INNER")],
            aggregations=[Agg("SUM", "lineitem.l_extendedprice")],
        ),
    ]
    stats = aggregate(facts)

    layer = induce(stats, catalog, facts, min_support=2)

    metric = next(m for m in layer.metrics if m.measure == ("SUM", "lineitem.l_extendedprice"))
    assert metric.support == 2
    assert len(metric.join_path) == 1


def test_induce_canonicalization_flips_time_offset_sign_with_direction():
    # A lag join written from either side is the same predicate: `a.d =
    # b.d - interval 1 month` and `b.d = a.d + interval 1 month` describe the
    # same relationship. Canonicalizing direction without also flipping the
    # offset's sign would either fail to merge them or, worse, merge a lag
    # join with a lead join that happens to share column names.
    catalog = {
        "lineitem": {"l_extendedprice": "DECIMAL(15,2)", "l_shipdate": "DATE"},
        "part": {"p_shipdate": "DATE"},
    }
    facts = [
        QueryFacts(
            query_id="q_a",
            tables={"lineitem", "part"},
            join_edges=[JoinEdge("lineitem.l_shipdate", "part.p_shipdate", "INNER", "-1 month")],
            aggregations=[Agg("SUM", "lineitem.l_extendedprice")],
        ),
        QueryFacts(
            query_id="q_b",
            tables={"lineitem", "part"},
            join_edges=[JoinEdge("part.p_shipdate", "lineitem.l_shipdate", "INNER", "+1 month")],
            aggregations=[Agg("SUM", "lineitem.l_extendedprice")],
        ),
    ]
    stats = aggregate(facts)

    layer = induce(stats, catalog, facts, min_support=2)

    metric = next(m for m in layer.metrics if m.measure == ("SUM", "lineitem.l_extendedprice"))
    assert metric.support == 2
    assert len(metric.join_path) == 1
    assert metric.join_path[0].left == "lineitem.l_shipdate"
    assert metric.join_path[0].time_offset == "-1 month"


def test_induce_propagates_component_definition_ids_for_composite_metrics():
    # A composite metric's queries reference another metric's materialized
    # output via FROM/JOIN (QueryFacts.metric_references), not a raw table.
    # induce() should carry that onto the induced Metric as
    # component_definition_ids, so Stage 4b can eventually tell a composite
    # apart from an atomic metric. See ARCHITECTURE.md's "Metric-to-metric
    # lineage" section.
    facts = [
        QueryFacts(
            query_id="composite_q",
            aggregations=[Agg("SUM", "metric_value")],
            metric_references={"component_metric_cube": "def_component_metric"},
        ),
    ]
    stats = aggregate(facts)

    layer = induce(stats, catalog={}, facts_list=facts, min_support=1)

    metric = next(m for m in layer.metrics if m.measure == ("SUM", "metric_value"))
    assert metric.component_definition_ids == ("def_component_metric",)


def test_entity_classification_covers_catalog_tables():
    catalog, _facts, stats = _corpus()

    assert set(classify_entities(stats, catalog)) == set(catalog)


def _profile(table: str, columns: dict[str, tuple[int, int, int]]) -> TableProfile:
    """Build a TableProfile from {column: (row_count, null_count, distinct_count)}."""
    row_count = next(iter(columns.values()))[0] if columns else 0
    return TableProfile(
        table=table,
        row_count=row_count,
        columns={
            name: ColumnProfile(table, name, rows, nulls, distinct)
            for name, (rows, nulls, distinct) in columns.items()
        },
    )


def test_detect_fanout_risk_flags_a_correlated_join_flattened_to_inner_join():
    # Mirrors the real q04-derived bug: COUNT(*) grouped by an orders
    # column, joined to lineitem purely as a flattened EXISTS. orders is
    # the grain table (o_orderkey unique); lineitem repeats l_orderkey
    # many times per order and contributes nothing to grain or measure.
    metric = Metric(
        measure=("COUNT", "*"),
        grain=frozenset({"orders.o_orderpriority"}),
        join_path=(JoinEdge("lineitem.l_orderkey", "orders.o_orderkey", "INNER"),),
        default_filters=(),
        support=1,
        seen_in=("q04",),
    )
    profiles = {
        "orders": _profile("orders", {"o_orderkey": (100, 0, 100), "o_orderpriority": (100, 0, 5)}),
        "lineitem": _profile("lineitem", {"l_orderkey": (400, 0, 100)}),
    }

    assert detect_fanout_risk(metric, profiles) is True


def test_detect_fanout_risk_allows_a_chain_of_proper_foreign_key_lookups():
    # Mirrors the real, verified-correct q11-derived metric: partsupp is
    # the grain/measure table; supplier and nation are joined only through
    # their own unique primary keys, so no partsupp row is ever
    # duplicated regardless of how many suppliers or nations exist.
    metric = Metric(
        measure=("SUM", "partsupp.ps_supplycost"),
        grain=frozenset({"partsupp.ps_partkey"}),
        join_path=(
            JoinEdge("partsupp.ps_suppkey", "supplier.s_suppkey", "INNER"),
            JoinEdge("supplier.s_nationkey", "nation.n_nationkey", "INNER"),
        ),
        default_filters=(),
        support=1,
        seen_in=("q11",),
    )
    profiles = {
        "partsupp": _profile(
            "partsupp", {"ps_partkey": (400, 0, 100), "ps_suppkey": (400, 0, 100)}
        ),
        "supplier": _profile(
            "supplier", {"s_suppkey": (100, 0, 100), "s_nationkey": (100, 0, 25)}
        ),
        "nation": _profile("nation", {"n_nationkey": (25, 0, 25)}),
    }

    assert detect_fanout_risk(metric, profiles) is False


def test_induce_excludes_fanout_risky_metrics_only_when_profiles_are_supplied():
    catalog, facts, stats = _corpus()

    without_profiles = induce(stats, catalog, facts, min_support=1)
    q04_metric = next(
        metric
        for metric in without_profiles.metrics
        if metric.measure == ("COUNT", "*")
        and metric.grain == frozenset({"orders.o_orderpriority"})
    )
    assert q04_metric is not None  # present by default -- profiles are opt-in

    profiles = {
        "orders": _profile("orders", {"o_orderkey": (100, 0, 100), "o_orderpriority": (100, 0, 5)}),
        "lineitem": _profile("lineitem", {"l_orderkey": (400, 0, 100)}),
    }
    with_profiles = induce(stats, catalog, facts, min_support=1, profiles=profiles)

    assert not any(
        metric.measure == ("COUNT", "*") and metric.grain == frozenset({"orders.o_orderpriority"})
        for metric in with_profiles.metrics
    )