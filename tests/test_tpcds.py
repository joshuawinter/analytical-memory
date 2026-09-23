from pathlib import Path

from semantic_induction.extract import extract_corpus, extract_facts
from semantic_induction.ingest import ingest


ROOT = Path(__file__).parents[1]


def test_tpcds_corpus_is_extractable():
    catalog, queries = ingest(ROOT / "data/tpcds/ddl.sql", ROOT / "data/tpcds/queries")
    facts = extract_corpus(queries, catalog)

    assert len(catalog) == 24
    assert len(queries) == 99
    assert len(facts) == 99
    assert sum(len(fact.set_operations) for fact in facts) > 0
    assert sum(len(fact.correlations) for fact in facts) > 0


def test_period_over_period_self_join_keeps_its_offset():
    """q47's v1/v1_lag/v1_lead self-join is the whole point of the query --

    `v1.rn = v1_lag.rn + 1` / `v1.rn = v1_lead.rn - 1` is what turns an
    ordinary dimensional self-join into a month-over-month comparison. Before
    JoinEdge carried a time_offset, `_is_column_pair` rejected both
    predicates outright (one side is `column + 1`, not a bare column) and
    extraction silently dropped them, keeping only the surrounding
    category/brand/store_name/company_name edges. See ARCHITECTURE.md's
    "Metric-to-metric lineage" section.
    """
    catalog, queries = ingest(ROOT / "data/tpcds/ddl.sql", ROOT / "data/tpcds/queries")
    q47 = next(query for query in queries if query.id == "q47")

    facts = extract_facts(q47.id, q47.ast, catalog)

    rank_edges = {
        (edge.left, edge.right): edge.time_offset
        for edge in facts.join_edges
        if edge.left.endswith(".rn") and edge.right.endswith(".rn")
    }
    assert rank_edges == {
        ("v1.rn", "v1_lag.rn"): "+1",
        ("v1.rn", "v1_lead.rn"): "-1",
    }