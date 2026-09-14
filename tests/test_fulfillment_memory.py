from pathlib import Path

from scripts.build_fulfillment_demo import build
from scripts.labeling_app import build_fulfillment_store


def test_fulfillment_store_exposes_otif_definition(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.build_fulfillment_demo.OUT", tmp_path)
    monkeypatch.setattr("scripts.build_fulfillment_demo.DB", tmp_path / "fulfillment.duckdb")
    monkeypatch.setattr("scripts.build_fulfillment_demo.REPORT", tmp_path / "report.html")
    build()

    store, _catalog = build_fulfillment_store(tmp_path / "fulfillment.duckdb", tmp_path / "labels.json")
    definition = store.memory.metric_definitions["metric:fulfillment:otif"]

    assert "On-time-in-full" in definition.inferred_definition
    assert definition.query_sql is not None
    assert definition.profile_notes
