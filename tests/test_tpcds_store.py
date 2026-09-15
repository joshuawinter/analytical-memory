from pathlib import Path

import pytest

from scripts.labeling_app import build_store

ROOT = Path(__file__).parents[1]


def test_tpcds_build_store(tmp_path):
    labels_path = tmp_path / "tpcds_labels.json"
    store, catalog = build_store(database=None, labels=labels_path, domain="tpcds")

    assert len(catalog) == 24
    assert len(store.memory.metric_definitions) > 100
    assert "store_sales.ss_ext_sales_price" in store.memory.concepts
    assert len(store.review_items()) > 100


def test_build_store_with_anthropic_naming_fails_loudly_without_credentials(tmp_path, monkeypatch):
    # The opt-in LLM naming pass must fail with a clear error rather than
    # silently falling back to the default heuristic path when requested
    # without credentials -- a silent fallback would be indistinguishable
    # from a real rename having happened.
    monkeypatch.delenv("SEMANTIC_INDUCTION_API_KEY", raising=False)
    labels_path = tmp_path / "tpch_labels.json"

    with pytest.raises(RuntimeError, match="missing API key environment variable"):
        build_store(database=None, labels=labels_path, domain="tpch", naming_provider="anthropic")
