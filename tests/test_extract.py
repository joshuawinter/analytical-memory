from pathlib import Path

import sqlglot

from semantic_induction.extract import extract_corpus, extract_facts
from semantic_induction.ingest import ingest


ROOT = Path(__file__).parents[1]


def _queries():
    _, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    return {query.id: query for query in queries}


def test_extracts_query_one_facts():
    query = _queries()["q01"]

    facts = extract_facts(query.id, query.ast)

    assert facts.tables == {"lineitem"}
    assert len(facts.aggregations) == 8
    assert facts.group_by == ["lineitem.l_returnflag", "lineitem.l_linestatus"]
    assert len(facts.predicates) == 1
    assert facts.predicates[0].column == "lineitem.l_shipdate"
    assert facts.predicates[0].op == "LTE"


def test_separates_comma_join_edges_from_filters():
    facts = extract_facts("q03", _queries()["q03"].ast)

    assert {edge.left for edge in facts.join_edges} == {
        "customer.c_custkey",
        "lineitem.l_orderkey",
    }
    assert {edge.right for edge in facts.join_edges} == {
        "orders.o_custkey",
        "orders.o_orderkey",
    }
    assert {predicate.column for predicate in facts.predicates} == {
        "customer.c_mktsegment",
        "orders.o_orderdate",
        "lineitem.l_shipdate",
    }


def test_extracts_entire_tpch_corpus():
    facts = extract_corpus(_queries().values())

    assert len(facts) == 22
    assert {fact.query_id for fact in facts} == {f"q{number:02d}" for number in range(1, 23)}


def test_preserves_cte_blocks_and_resolves_lineage():
    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    query = next(query for query in queries if query.id == "q15")

    facts = extract_facts(query.id, query.ast, catalog)

    assert [(block.block_id, block.kind) for block in facts.query_blocks[:2]] == [
        ("revenue", "CTE"),
        ("main", "MAIN"),
    ]
    assert any(block.kind == "SUBQUERY" for block in facts.query_blocks)
    assert facts.query_blocks[0].tables == {"lineitem"}
    assert "revenue" not in facts.tables
    assert facts.column_lineage["revenue.total_revenue"].sources == (
        "lineitem.l_extendedprice",
        "lineitem.l_discount",
    )


def test_records_correlated_exists_scopes():
    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    query = next(query for query in queries if query.id == "q04")

    facts = extract_facts(query.id, query.ast, catalog)

    assert any(
        correlation.inner_column == "lineitem.l_orderkey"
        and correlation.outer_column == "orders.o_orderkey"
        for correlation in facts.correlations
    )
    assert any(block.kind == "SUBQUERY" for block in facts.query_blocks)


def test_records_union_all_as_a_set_operation():
    ast = sqlglot.parse_one(
        "SELECT c_custkey FROM customer UNION ALL SELECT c_custkey FROM customer"
    )

    facts = extract_facts("union", ast)

    assert len(facts.set_operations) == 1
    assert facts.set_operations[0].operator == "UNION_ALL"