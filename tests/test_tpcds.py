from pathlib import Path

from semantic_induction.extract import extract_corpus
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