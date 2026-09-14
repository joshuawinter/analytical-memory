import duckdb

import scripts.build_fulfillment_demo as builder
import scripts.investigate_fulfillment_demo as investigator


def test_fulfillment_demo_reproduces_known_operational_change(tmp_path, monkeypatch):
    # Keep the deterministic demo's real output contract while isolating the
    # test from any previously generated local artifacts.
    monkeypatch.setattr(builder, "OUT", tmp_path)
    monkeypatch.setattr(builder, "DB", tmp_path / "fulfillment.duckdb")
    monkeypatch.setattr(builder, "REPORT", tmp_path / "report.html")
    monkeypatch.setattr(investigator, "DB", tmp_path / "fulfillment.duckdb")
    monkeypatch.setattr(investigator, "OUT", tmp_path / "investigation.html")
    monkeypatch.setattr(investigator, "RECORD", tmp_path / "investigation.json")

    builder.build()
    investigator.run()

    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "truth.json").exists()
    assert (tmp_path / "investigation.html").exists()
    assert (tmp_path / "investigation.json").exists()
    with duckdb.connect(str(tmp_path / "fulfillment.duckdb"), read_only=True) as connection:
        rows = connection.execute(
            "SELECT o.warehouse_id, COUNT(*) "
            "FROM order_event e JOIN sales_order o ON o.order_id = e.order_id "
            "WHERE e.event_type = 'SHIPPED' AND e.reason_code = 'STOCKOUT' "
            "GROUP BY o.warehouse_id"
        ).fetchall()
    assert rows == [("W03", 20)]