from pathlib import Path

from scripts.labeling_app import build_store

ROOT = Path(__file__).parents[1]


def test_tpcds_build_store(tmp_path):
    labels_path = tmp_path / "tpcds_labels.json"
    store, catalog = build_store(database=None, labels=labels_path, domain="tpcds")

    assert len(catalog) == 24
    assert len(store.memory.metric_definitions) > 100
    assert "store_sales.ss_ext_sales_price" in store.memory.concepts
    assert len(store.review_items()) > 100
