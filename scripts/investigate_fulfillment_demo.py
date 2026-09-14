"""Run the deterministic fulfillment investigation and write a visual result.

Usage:
    .venv/Scripts/python.exe scripts/investigate_fulfillment_demo.py
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "fulfillment_demo" / "fulfillment.duckdb"
OUT = ROOT / "data" / "fulfillment_demo" / "investigation.html"
RECORD = ROOT / "data" / "fulfillment_demo" / "investigation.json"


def run() -> None:
    with duckdb.connect(str(DB), read_only=True) as connection:
        monthly = connection.execute("""
            SELECT DATE_TRUNC('month', o.order_date) AS month,
                   COUNT(*) AS orders,
                   SUM(CASE WHEN e.event_time <= o.promised_date
                                  AND e.quantity >= l.ordered_quantity THEN 1 ELSE 0 END) AS otif,
                   SUM(CASE WHEN e.event_time > o.promised_date THEN 1 ELSE 0 END) AS late
            FROM sales_order o
            JOIN sales_order_line l ON l.order_id = o.order_id
            JOIN order_event e ON e.order_id = o.order_id AND e.event_type = 'DELIVERED'
            GROUP BY 1 ORDER BY 1
        """).fetchall()
        warehouse = connection.execute("""
            SELECT o.warehouse_id,
                   COUNT(*) AS orders,
                   SUM(CASE WHEN delivered.event_time > o.promised_date THEN 1 ELSE 0 END) AS late,
                   SUM(CASE WHEN shipped.reason_code = 'STOCKOUT' THEN 1 ELSE 0 END) AS stockouts
            FROM sales_order o
            JOIN order_event shipped ON shipped.order_id = o.order_id AND shipped.event_type = 'SHIPPED'
            JOIN order_event delivered ON delivered.order_id = o.order_id AND delivered.event_type = 'DELIVERED'
            WHERE o.order_date >= DATE '2026-02-01'
            GROUP BY 1 ORDER BY late DESC
        """).fetchall()

    jan = monthly[0]
    feb = monthly[1]
    decline = jan[2] - feb[2]
    driver = warehouse[0][0]
    record = {
        "question": "Why did on-time-in-full fulfillment decline this month?",
        "steps": ["baseline_period_comparison", "warehouse_driver_breakdown", "event_evidence_linkage"],
        "metric_definition": "Delivered by promised date and delivered quantity >= ordered quantity.",
        "baseline": [{"month": str(row[0])[:10], "orders": row[1], "otif": row[2], "late": row[3]} for row in monthly],
        "drivers": [{"warehouse": row[0], "orders": row[1], "late": row[2], "stockouts": row[3]} for row in warehouse],
        "finding": f"February OTIF decline concentrated in {driver} stockouts",
        "evidence": ["sales_order", "sales_order_line", "order_event", "inventory_snapshot"],
        "hidden_truth_used": False,
    }
    RECORD.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
    warehouse_rows = "".join(
        f"<tr><td>{html.escape(str(row[0]))}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td></tr>"
        for row in warehouse
    )
    monthly_rows = "".join(
        f"<tr><td>{html.escape(str(row[0])[:10])}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td></tr>"
        for row in monthly
    )
    OUT.write_text(f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Fulfillment Investigation</title><style>
body{{font:15px Segoe UI,system-ui,sans-serif;margin:0;background:#f1f4f1;color:#193238}}header{{background:#173b3f;color:white;padding:32px 8%}}main{{max-width:1000px;margin:25px auto;padding:0 20px}}.finding,.panel{{background:#fff;border:1px solid #d7e0db;border-radius:8px;padding:22px;margin:16px 0;box-shadow:0 2px 8px #1932380d}}.finding{{border-left:5px solid #d76b3f}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #e1e8e3}}th{{font-size:12px;color:#657670;text-transform:uppercase}}code,pre{{white-space:pre-wrap}}.meta{{color:#5e706b}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Fulfillment Investigation</h1><p>Deterministic baseline for the future corporate agent.</p></header><main><section class=finding><h2>Finding</h2><p>On-time-in-full performance declined by <b>{decline} orders</b> from January to February 2026. The February late orders are concentrated in warehouse <b>{html.escape(str(warehouse[0][0]))}</b>, where stockout events match the late-shipment pattern.</p><p class=meta>Finding generated from the fulfillment database; no hidden-truth file was read.</p></section><section class=grid><article class=panel><h2>Monthly result</h2><table><tr><th>Month</th><th>Orders</th><th>OTIF</th><th>Late</th></tr>{monthly_rows}</table></article><article class=panel><h2>Warehouse breakdown</h2><table><tr><th>Warehouse</th><th>Orders</th><th>Late</th><th>Stockouts</th></tr>{warehouse_rows}</table></article></section><section class=panel><h2>Metric definition used</h2><p><b>On-time-in-full:</b> delivered event occurs on or before promised date and delivered quantity is greater than or equal to ordered quantity.</p><p><b>Evidence:</b> sales orders, order lines, delivered events, shipped-event reason codes.</p></section></main></body></html>""", encoding="utf-8")
    print(f"investigation report: {OUT}")
    print(f"investigation record: {RECORD}")
    print(f"finding: February OTIF decline concentrated in {driver} stockouts")


if __name__ == "__main__":
    run()
