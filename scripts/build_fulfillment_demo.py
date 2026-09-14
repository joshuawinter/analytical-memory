"""Build a deterministic order-to-cash fulfillment demonstration.

Usage:
    .venv/Scripts/python.exe scripts/build_fulfillment_demo.py

Writes data/fulfillment_demo/fulfillment.duckdb, truth.json, and report.html.
"""
from __future__ import annotations

import html
import json
import random
from datetime import date, timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fulfillment_demo"
DB = OUT / "fulfillment.duckdb"
REPORT = OUT / "report.html"


SCHEMA = """
CREATE TABLE customer(customer_id INTEGER, segment VARCHAR, region VARCHAR);
CREATE TABLE product(product_id INTEGER, category VARCHAR, unit_price DECIMAL(10,2));
CREATE TABLE warehouse(warehouse_id VARCHAR, region VARCHAR, capacity INTEGER);
CREATE TABLE sales_order(order_id INTEGER, customer_id INTEGER, order_date DATE, promised_date DATE, warehouse_id VARCHAR, status VARCHAR);
CREATE TABLE sales_order_line(order_id INTEGER, line_number INTEGER, product_id INTEGER, ordered_quantity INTEGER, unit_price DECIMAL(10,2));
CREATE TABLE order_event(event_id INTEGER, order_id INTEGER, line_number INTEGER, event_type VARCHAR, event_time DATE, quantity INTEGER, reason_code VARCHAR);
CREATE TABLE inventory_snapshot(snapshot_date DATE, warehouse_id VARCHAR, product_id INTEGER, available_quantity INTEGER, reserved_quantity INTEGER);
"""


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    rng = random.Random(42)
    connection = duckdb.connect(str(DB))
    connection.execute(SCHEMA)

    customers = [(i, "Enterprise" if i % 3 == 0 else "SMB", "West" if i % 2 else "East") for i in range(1, 31)]
    products = [(1, "Core", 100.0), (2, "Core", 120.0), (3, "Premium", 250.0), (4, "Premium", 275.0), (5, "Accessory", 35.0)]
    warehouses = [("W01", "East", 1000), ("W02", "West", 1000), ("W03", "West", 1000)]
    connection.executemany("INSERT INTO customer VALUES (?, ?, ?)", customers)
    connection.executemany("INSERT INTO product VALUES (?, ?, ?)", products)
    connection.executemany("INSERT INTO warehouse VALUES (?, ?, ?)", warehouses)

    orders = []
    lines = []
    events = []
    snapshots = []
    event_id = 1
    for order_id in range(1, 81):
        month_start = date(2026, 1, 5) if order_id <= 40 else date(2026, 2, 5)
        order_date = month_start + timedelta(days=(order_id * 3) % 20)
        warehouse_id = ("W03" if order_id > 40 and order_id % 2 == 0 else ("W01" if order_id % 3 else "W02"))
        promised_date = order_date + timedelta(days=3)
        customer_id = (order_id % 30) + 1
        product_id = (order_id % 5) + 1
        quantity = 10 + (order_id % 7)
        late = order_id > 40 and warehouse_id == "W03"
        delivery_date = promised_date + timedelta(days=3 if late else 0)
        orders.append((order_id, customer_id, order_date, promised_date, warehouse_id, "DELIVERED"))
        lines.append((order_id, 1, product_id, quantity, float(products[product_id - 1][2])))
        events.extend([
            (event_id, order_id, 1, "ORDER_CREATED", order_date, quantity, None),
            (event_id + 1, order_id, 1, "SHIPPED", order_date + timedelta(days=2 if not late else 5), quantity if not late else quantity // 2, "STOCKOUT" if late else None),
            (event_id + 2, order_id, 1, "DELIVERED", delivery_date, quantity if not late else quantity // 2, None),
        ])
        event_id += 3

    for warehouse_id, _region, _capacity in warehouses:
        for product_id, _category, _price in products:
            snapshots.append((date(2026, 1, 31), warehouse_id, product_id, 100, 10))
            snapshots.append((date(2026, 2, 28), warehouse_id, product_id, 5 if warehouse_id == "W03" else 100, 90 if warehouse_id == "W03" else 10))

    connection.executemany("INSERT INTO sales_order VALUES (?, ?, ?, ?, ?, ?)", orders)
    connection.executemany("INSERT INTO sales_order_line VALUES (?, ?, ?, ?, ?)", lines)
    connection.executemany("INSERT INTO order_event VALUES (?, ?, ?, ?, ?, ?, ?)", events)
    connection.executemany("INSERT INTO inventory_snapshot VALUES (?, ?, ?, ?, ?)", snapshots)

    metrics = connection.execute("""
        SELECT DATE_TRUNC('month', o.order_date) AS month,
               COUNT(*) AS orders,
               SUM(CASE WHEN delivered.event_time <= o.promised_date
                         AND delivered.quantity >= l.ordered_quantity THEN 1 ELSE 0 END) AS on_time_in_full,
               SUM(CASE WHEN delivered.event_time > o.promised_date THEN 1 ELSE 0 END) AS late_orders
        FROM sales_order o
        JOIN sales_order_line l ON l.order_id = o.order_id
        JOIN order_event delivered ON delivered.order_id = o.order_id
             AND delivered.event_type = 'DELIVERED'
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    drivers = connection.execute("""
        SELECT o.warehouse_id,
               SUM(CASE WHEN delivered.event_time > o.promised_date THEN 1 ELSE 0 END) AS late_orders,
               SUM(CASE WHEN shipped.reason_code = 'STOCKOUT' THEN 1 ELSE 0 END) AS stockout_orders
        FROM sales_order o
        JOIN order_event shipped ON shipped.order_id = o.order_id AND shipped.event_type = 'SHIPPED'
        JOIN order_event delivered ON delivered.order_id = o.order_id AND delivered.event_type = 'DELIVERED'
        GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()
    truth = {
        "domain": "order_to_cash_fulfillment",
        "question": "Why did on-time-in-full fulfillment decline in February 2026?",
        "known_cause": "W03 stockouts caused the decline",
        "expected_driver": "W03",
        "metrics": ["order volume", "on-time-in-full rate", "late shipments", "stockout orders"],
    }
    (OUT / "truth.json").write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render_report(metrics, drivers, truth), encoding="utf-8")
    connection.close()
    print(f"database: {DB}")
    print(f"visual report: {REPORT}")
    print(f"known cause: {truth['known_cause']}")


def render_report(metrics: list[tuple], drivers: list[tuple], truth: dict[str, object]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(str(month)[:10])}</td><td>{orders}</td><td>{otif}</td><td>{late}</td></tr>"
        for month, orders, otif, late in metrics
    )
    driver_rows = "".join(
        f"<tr><td>{warehouse}</td><td>{late}</td><td>{stockouts}</td></tr>"
        for warehouse, late, stockouts in drivers
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Fulfillment Demo</title><style>
body{{font:15px Segoe UI,system-ui,sans-serif;margin:0;background:#f1f4f1;color:#193238}}header{{background:#173b3f;color:#fff;padding:32px 8%}}main{{max-width:1000px;margin:25px auto;padding:0 20px}}.hero,.panel{{background:#fff;border:1px solid #d7e0db;border-radius:8px;padding:22px;margin:16px 0;box-shadow:0 2px 8px #1932380d}}h1{{margin:0 0 8px}}h2{{margin-top:0}}.truth{{border-left:5px solid #4d9a72;background:#e6f1e9;padding:14px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #e1e8e3}}th{{color:#657670;font-size:12px;text-transform:uppercase}}.bar{{height:12px;background:#dbe7df;border-radius:8px;overflow:hidden}}.bar span{{display:block;height:100%;background:#d76b3f}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Order-to-Cash Fulfillment Demo</h1><p>A deterministic enterprise-like world with hidden evaluation truth.</p></header><main><section class='hero'><h2>Investigation question</h2><p>{html.escape(str(truth['question']))}</p><div class='truth'><b>Known evaluation truth:</b> {html.escape(str(truth['known_cause']))}</div></section><section class='grid'><article class='panel'><h2>Monthly fulfillment</h2><table><tr><th>Month</th><th>Orders</th><th>On-time-in-full</th><th>Late</th></tr>{rows}</table></article><article class='panel'><h2>Warehouse drivers</h2><table><tr><th>Warehouse</th><th>Late orders</th><th>Stockout orders</th></tr>{driver_rows}</table></article></section><section class='panel'><h2>What this demonstrates</h2><p>The data is generated from order, shipment, inventory, and event rules. The agent's future task is to recover the metric definition, obtain expert approval, investigate the change, and identify the known driver without being given the truth directly.</p></section></main></body></html>"""


if __name__ == "__main__":
    build()
