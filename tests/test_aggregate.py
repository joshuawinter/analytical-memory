from pathlib import Path

from semantic_induction.aggregate import aggregate, assign_roles
from semantic_induction.extract import extract_corpus
from semantic_induction.ingest import ingest
from semantic_induction.models import Role


ROOT = Path(__file__).parents[1]


def _facts():
    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    return extract_corpus(queries, catalog)


def test_assign_roles_keeps_multiple_observed_roles():
    facts = next(fact for fact in _facts() if fact.query_id == "q01")

    roles = assign_roles(facts)

    assert Role.MEASURE in roles["lineitem.l_quantity"]
    assert Role.DIMENSION in roles["lineitem.l_returnflag"]
    assert Role.ORDERED in roles["lineitem.l_shipdate"]


def test_aggregate_counts_corpus_support():
    stats = aggregate(_facts())

    assert stats.table_freq["lineitem"] == 17
    assert "revenue" not in stats.table_freq
    # supplier.s_nationkey = nation.n_nationkey, at physical-table-name
    # frequency now that Stage 1 resolves query-local table aliases (e.g.
    # different queries aliasing `supplier` differently no longer fragment
    # the same canonical join edge into separate counts).
    assert stats.edge_freq.most_common(1)[0][1] == 8
    assert stats.agg_freq[("SUM", "lineitem.l_extendedprice")] > 0
    assert stats.grain_freq[frozenset({
        "lineitem.l_returnflag",
        "lineitem.l_linestatus",
    })] == 1
    assert stats.pred_freq[
        ("lineitem.l_shipdate", "LTE", "CAST('1998-09-02' AS DATE)")
    ] == 1