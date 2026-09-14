"""Local analytical-memory review, investigation, and MCP inspection interface."""
from __future__ import annotations

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from semantic_induction.aggregate import aggregate
from semantic_induction.extract import extract_corpus
from semantic_induction.induce import induce
from semantic_induction.ingest import ingest
from semantic_induction.investigate import investigate
from semantic_induction.labeling import LabelingError, LabelingStore
from semantic_induction.mcp_server import handle_rpc_message
from semantic_induction.memory import (
    AnalyticalMemory,
    BusinessConcept,
    Evidence,
    MetricDefinition,
    memory_from_layer,
)
from semantic_induction.profile import profile_database
from semantic_induction.services import InvestigationService, investigation_payload


def _label(column: str) -> str:
    return re.sub(r"^[a-z]+_", "", column.rsplit(".", 1)[-1]).replace("_", " ").title()


def build_store(database: Path | None, labels: Path, domain: str = "tpch") -> tuple[LabelingStore, dict[str, dict[str, str]]]:
    data_dir = ROOT / "data" / domain
    catalog, queries = ingest(data_dir / "ddl.sql", data_dir / "queries")
    facts = extract_corpus(queries, catalog)
    profiles = None
    if database and database.exists():
        with duckdb.connect(str(database), read_only=True) as c:
            profiles = profile_database(c, catalog, sample_size=5, top_values=5)
    layer = induce(aggregate(facts), catalog, facts, min_support=1, profiles=profiles)
    aliases_by_column: dict[str, set[str]] = {}
    for fact in facts:
      for aggregation in fact.aggregations:
        if aggregation.alias and aggregation.column != "*":
          aliases_by_column.setdefault(aggregation.column, set()).add(aggregation.alias)
    concepts = {
        column: BusinessConcept(
            column,
            _label(column),
        tuple(sorted({column.rsplit(".", 1)[-1], *aliases_by_column.get(column, set())})),
            f"Observed {aggregation} measure over {column}.",
        )
        for aggregation, column in layer.measures
    }
    store = LabelingStore(memory_from_layer(layer, concepts, profiles=profiles), labels)
    store.load()
    return store, catalog


def build_fulfillment_store(database: Path | None, labels: Path) -> tuple[LabelingStore, dict[str, dict[str, str]]]:
    tables = ("sales_order", "sales_order_line", "order_event", "inventory_snapshot")
    catalog = {
        "sales_order": {"order_id": "VARCHAR", "customer_id": "VARCHAR", "order_date": "DATE", "promised_date": "DATE", "status": "VARCHAR", "priority": "VARCHAR"},
        "sales_order_line": {"order_id": "VARCHAR", "line_id": "INTEGER", "product_id": "VARCHAR", "ordered_quantity": "INTEGER", "unit_price": "DECIMAL(10,2)"},
        "order_event": {"event_id": "VARCHAR", "order_id": "VARCHAR", "event_type": "VARCHAR", "event_time": "TIMESTAMP", "warehouse_id": "VARCHAR", "carrier_id": "VARCHAR", "quantity": "INTEGER"},
        "inventory_snapshot": {"snapshot_date": "DATE", "warehouse_id": "VARCHAR", "product_id": "VARCHAR", "on_hand_quantity": "INTEGER", "reserved_quantity": "INTEGER", "available_quantity": "INTEGER"},
    }
    profiles = None
    if database and database.exists():
        with duckdb.connect(str(database), read_only=True) as c:
            catalog = {
                table: {row[0]: row[1] for row in c.execute(f'DESCRIBE "{table}"').fetchall()}
                for table in tables
            }
            profiles = profile_database(c, catalog, sample_size=5, top_values=5)
    memory = AnalyticalMemory(
        concepts={
            "fulfillment.otif": BusinessConcept(
                "fulfillment.otif",
                "On-Time-In-Full Fulfillment",
                ("OTIF", "on time in full"),
                "Delivered by promise date with ordered quantity fulfilled.",
            )
        },
        evidence={
            "demo:events": Evidence(
                "demo:events", "GENERATED_DATA", "order_event and inventory_snapshot"
            )
        },
        profiles=profiles,
        metric_definitions={
            "metric:fulfillment:otif": MetricDefinition(
                "metric:fulfillment:otif",
                "fulfillment.otif",
                ("OTIF", "fulfillment"),
                (),
                evidence_ids=("demo:events",),
                inferred_definition="On-time-in-full: delivered by promised date and delivered quantity is at least ordered quantity.",
            profile_notes=((
                    f"sales orders: {profiles['sales_order'].row_count:,} observed rows",
                    f"order events: {profiles['order_event'].row_count:,} observed rows",
            ) if profiles else ()),
                profile_tables=tables,
                query_sql="""SELECT DATE_TRUNC('month',o.order_date) AS month,COUNT(*) AS orders,
SUM(CASE WHEN d.event_time<=o.promised_date AND d.quantity>=l.ordered_quantity THEN 1 ELSE 0 END) AS otif_orders,
SUM(CASE WHEN d.event_time>o.promised_date THEN 1 ELSE 0 END) AS late_orders
FROM sales_order o JOIN sales_order_line l ON l.order_id=o.order_id
JOIN order_event d ON d.order_id=o.order_id AND d.event_type='DELIVERED'
GROUP BY 1 ORDER BY 1""",
            )
        },
    )
    store = LabelingStore(memory, labels)
    store.load()
    return store, catalog


class MultiDomainRegistry:
    def __init__(self) -> None:
        self.domains: dict[str, dict] = {}

    def register(self, domain_id: str, label: str, store: LabelingStore, catalog: dict[str, dict[str, str]], database_path: Path | None) -> None:
        self.domains[domain_id] = {
            "id": domain_id,
            "label": label,
            "store": store,
            "catalog": catalog,
            "database_path": database_path,
        }

    def get(self, domain_id: str) -> dict:
        return self.domains.get(domain_id) or self.domains["tpch"]

    def list_domains(self) -> list[dict[str, str]]:
        return [{"id": d["id"], "label": d["label"]} for d in self.domains.values()]


def init_multi_domain_registry() -> MultiDomainRegistry:
    registry = MultiDomainRegistry()
    
    # 1. TPC-H
    tpch_db = ROOT / "data/tpch/tpch.duckdb"
    tpch_store, tpch_cat = build_store(tpch_db if tpch_db.exists() else None, ROOT / "data/tpch/labels.json", domain="tpch")
    registry.register("tpch", "TPC-H Benchmark (8 tables, 22 queries)", tpch_store, tpch_cat, tpch_db)

    # 2. TPC-DS
    tpcds_db = ROOT / "data/tpcds/tpcds.duckdb"
    tpcds_store, tpcds_cat = build_store(tpcds_db if tpcds_db.exists() else None, ROOT / "data/tpcds/labels.json", domain="tpcds")
    registry.register("tpcds", "TPC-DS Benchmark (24 tables, 99 queries)", tpcds_store, tpcds_cat, tpcds_db)

    # 3. Order-to-Cash Fulfillment
    ful_db = ROOT / "data/fulfillment_demo/fulfillment.duckdb"
    ful_store, ful_cat = build_fulfillment_store(ful_db if ful_db.exists() else None, ROOT / "data/fulfillment_demo/labels.json")
    registry.register("fulfillment", "Order-to-Cash Fulfillment (4 tables, Event Log)", ful_store, ful_cat, ful_db)

    return registry


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Analytical Memory &amp; MCP Inspector</title>
<style>
body{font:15px Segoe UI,system-ui,sans-serif;margin:0;background:#eef2f0;color:#193238}
.top{background:#173b3f;color:#fff;padding:20px 7%;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:15px}
.top h1{margin:0 0 5px;font-size:26px}
.top p{margin:0;color:#c8d8d2}
.domain-picker{display:flex;align-items:center;gap:10px;background:#244c52;padding:8px 14px;border-radius:8px}
.domain-picker label{color:#e0ece7;font-size:12px;font-weight:bold;text-transform:uppercase}
.domain-picker select{background:#fff;font-weight:600;padding:6px 12px;border-radius:5px}
main{max-width:1050px;margin:20px auto;padding:0 18px}
.tab-bar{display:flex;gap:8px;margin-bottom:16px;border-bottom:2px solid #cbdad2;padding-bottom:8px}
.tab-btn{background:#dbe7df;color:#193238;border:0;padding:8px 18px;border-radius:6px;font-weight:600;cursor:pointer}
.tab-btn.active{background:#173b3f;color:#fff}
.panel-section{background:#fff;border:1px solid #d4dfda;border-radius:8px;padding:18px;margin:14px 0;box-shadow:0 2px 8px #1932380d}
.ask{background:#dfeae5}
.ask h2, .panel-section h2{margin:0 0 5px;font-size:18px}
.ask p{margin:0 0 12px;color:#506663}
.askbar,.bar{display:flex;gap:9px;margin-bottom:14px}
input,select,textarea,button{font:inherit;border:1px solid #c7d3ce;border-radius:6px;padding:9px;background:#fff}
input{flex:1}
button{background:#d76b3f;color:#fff;border:0;font-weight:650;cursor:pointer}
button.sec{background:#2e5a61}
.answer{background:#f7faf8;border:1px solid #cbdad2;border-radius:6px;padding:14px}
.answer-head{display:flex;gap:12px;margin-bottom:10px}
.answer-status{font-size:12px;font-weight:700;padding:4px 8px;border-radius:12px}
.ok{background:#d7efdf;color:#25633e}
.review{background:#f7e6bb;color:#76550d}
.answer-message,.answer-empty{color:#61736e}
.answer-field{margin:10px 0}
.answer-field label,.field label{display:block;color:#71807b;font-size:11px;text-transform:uppercase;margin-bottom:4px}
.sql code{display:block;white-space:pre-wrap;background:#edf3ef;padding:10px;margin-top:8px;border-radius:5px;overflow:auto}
.result-wrap{overflow:auto;border:1px solid #d8e2dc;border-radius:5px}
.result-wrap table{width:100%;border-collapse:collapse;min-width:420px}
.result-wrap th,.result-wrap td{text-align:left;padding:9px;border-bottom:1px solid #e3eae5;white-space:nowrap}
.result-wrap th{font-size:11px;text-transform:uppercase;color:#687873;background:#f2f6f3}
.card{background:#fff;border:1px solid #d4dfda;border-left:5px solid #9eb7ad;border-radius:8px;padding:18px;margin:14px 0}
.card.approve{border-left-color:#4d9a72}
.card.reject{border-left-color:#bd5548}
.card.clarify{border-left-color:#d1a23d}
.head{display:flex;justify-content:space-between;gap:12px}
.head h2{margin:0;font-size:18px}
.status{color:#687873;font-size:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:15px 0}
.field code{white-space:pre-wrap}
.evidence{color:#456060;margin-bottom:14px}
.actions{display:grid;grid-template-columns:140px 1fr 110px;gap:9px}
.sample-table{margin-top:10px}
.sample-table b{display:block;margin-bottom:5px}
.sample-wrap{overflow:auto;border:1px solid #d8e2dc;border-radius:5px}
.sample-wrap table{width:100%;border-collapse:collapse;min-width:520px}
.sample-wrap th,.sample-wrap td{text-align:left;padding:7px;border-bottom:1px solid #e3eae5;white-space:nowrap}
.sample-wrap th{font-size:10px;text-transform:uppercase;color:#687873;background:#f2f6f3}
.mcp-pill{display:inline-block;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:700;background:#d7efdf;color:#25633e;margin-bottom:12px}
.mcp-btns{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.rpc-box{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.rpc-box pre{background:#202a2d;color:#e8f0ec;padding:12px;border-radius:6px;overflow:auto;max-height:360px;font-size:13px}
@media(max-width:700px){.grid,.actions,.rpc-box{grid-template-columns:1fr}.head{display:block}.askbar{display:grid}}
</style>
</head>
<body>
<header class="top">
  <div>
    <h1>Analytical Memory &amp; MCP Inspector</h1>
    <p>Live corporate intelligence substrate with Model Context Protocol interface.</p>
  </div>
  <div class="domain-picker">
    <label for="domain-select">Active Domain:</label>
    <select id="domain-select" onchange="switchDomain(this.value)">
      __DOMAIN_OPTIONS__
    </select>
  </div>
</header>
<main>
  <nav class="tab-bar">
    <button id="tab1-btn" class="tab-btn active" onclick="showTab('tab-review')">Review &amp; Investigation</button>
    <button id="tab2-btn" class="tab-btn" onclick="showTab('tab-mcp')">Live MCP Protocol Inspector</button>
  </nav>

  <!-- TAB 1: REVIEW & INVESTIGATION -->
  <div id="tab-review">
    <section class="panel-section ask">
      <h2>Ask an investigation question</h2>
      <p>Approved definitions only. Unapproved or ambiguous questions remain in review.</p>
      <div class="askbar">
        <input id="question" placeholder="Why did on-time-in-full fulfillment decline this month?">
        <button onclick="ask()">Investigate</button>
      </div>
      <div id="answer" class="answer"><div class="answer-empty">Enter a question to begin.</div></div>
    </section>

    <div class="bar">
      <input id="q" placeholder="Search candidates...">
      <select id="f">
        <option>ALL</option>
        <option>PENDING</option>
        <option>APPROVE</option>
        <option>REJECT</option>
        <option>CLARIFY</option>
      </select>
      <span id="count"></span>
    </div>
    <section id="cards"></section>
  </div>

  <!-- TAB 2: LIVE MCP INSPECTOR -->
  <div id="tab-mcp" style="display:none;">
    <section class="panel-section">
      <div class="mcp-pill">● MCP Protocol 2024-11-05 Active (semantic-induction-mcp v0.1.0)</div>
      <h2>Interactive MCP Tool &amp; Resource Inspector</h2>
      <p>Trigger live JSON-RPC 2.0 protocol calls directly against the MCP service and inspect wire payloads.</p>

      <div class="mcp-btns">
        <button class="sec" onclick="mcpCall('initialize', {protocolVersion:'2024-11-05'})">1. Initialize Handshake</button>
        <button class="sec" onclick="mcpCall('ping')">2. Ping</button>
        <button class="sec" onclick="mcpCall('tools/list')">3. List Tools</button>
        <button class="sec" onclick="mcpCall('resources/list')">4. List Resources</button>
        <button class="sec" onclick="mcpCall('resources/read', {uri:'memory://concepts'})">Resource: Concepts</button>
        <button class="sec" onclick="mcpCall('resources/read', {uri:'memory://metric_definitions'})">Resource: Metrics</button>
        <button class="sec" onclick="mcpCall('tools/call', {name:'search_business_memory', arguments:{question:'fulfillment'}})">Tool: Search Memory</button>
        <button onclick="mcpCall('tools/call', {name:'run_approved_investigation', arguments:{question:'Why did on-time-in-full fulfillment decline this month?'}})">Tool: Run Investigation</button>
      </div>

      <div class="rpc-box">
        <div>
          <label><strong>JSON-RPC Request (Wire Sent)</strong></label>
          <pre id="rpc-req">Click an action button above to inspect JSON-RPC traffic.</pre>
        </div>
        <div>
          <label><strong>JSON-RPC Response (Wire Received)</strong></label>
          <pre id="rpc-res">// Response will appear here.</pre>
        </div>
      </div>
    </section>
  </div>
</main>

<script>
let data = __ITEMS__;
let currentDomain = "__CURRENT_DOMAIN__";
const esc = x => String(x ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

async function switchDomain(domainId) {
  currentDomain = domainId;
  const res = await fetch('/api/items?domain=' + encodeURIComponent(domainId));
  if (res.ok) {
    data = await res.json();
    render();
    document.getElementById('rpc-req').textContent = 'Domain switched to: ' + domainId;
    document.getElementById('rpc-res').textContent = '// Ready for MCP requests against ' + domainId;
    document.getElementById('answer').innerHTML = '<div class="answer-empty">Switched domain to ' + domainId + '. Enter a question to investigate.</div>';
  }
}

function showTab(id) {
  document.getElementById('tab-review').style.display = id === 'tab-review' ? 'block' : 'none';
  document.getElementById('tab-mcp').style.display = id === 'tab-mcp' ? 'block' : 'none';
  document.getElementById('tab1-btn').className = 'tab-btn ' + (id === 'tab-review' ? 'active' : '');
  document.getElementById('tab2-btn').className = 'tab-btn ' + (id === 'tab-mcp' ? 'active' : '');
}

function sampleHtml(samples) {
  if (!samples || !samples.length) return 'none';
  return samples.map(s => `
    <div class="sample-table">
      <b>${esc(s.table)}</b>
      <div class="sample-wrap">
        <table>
          <thead><tr>${s.columns.map(c => '<th>' + esc(c) + '</th>').join('')}</tr></thead>
          <tbody>${s.rows.map(row => '<tr>' + row.map(v => '<td>' + esc(v) + '</td>').join('') + '</tr>').join('')}</tbody>
        </table>
      </div>
    </div>
  `).join('');
}

async function ask() {
  const q = document.querySelector('#question').value.trim();
  const box = document.querySelector('#answer');
  if (!q) { box.innerHTML = '<div class="answer-empty">Enter a question.</div>'; return; }
  box.innerHTML = '<div class="answer-empty">Investigating...</div>';
  const r = await fetch('/investigate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question: q, domain: currentDomain})
  });
  const o = await r.json();
  let m = '<div class="answer-head"><span class="answer-status ' + (o.status==='ANSWERED'?'ok':'review') + '">' + esc(o.status) + '</span>' + (o.message ? '<span class="answer-message">' + esc(o.message) + '</span>' : '') + '</div>';
  if (o.definition) m += '<div class="answer-field"><label>Definition</label><p>' + esc(o.definition) + '</p></div>';
  if (o.evidence?.length) m += '<div class="answer-field"><label>Evidence</label><p>' + esc(o.evidence.join(', ')) + '</p></div>';
  if (o.sql) m += '<details class="sql"><summary>Generated SQL</summary><code>' + esc(o.sql) + '</code></details>';
  if (o.columns?.length) {
    m += '<div class="answer-field"><label>Result</label><div class="result-wrap"><table><thead><tr>' + o.columns.map(c => '<th>' + esc(c) + '</th>').join('') + '</tr></thead><tbody>' + o.rows.map(row => '<tr>' + row.map(v => '<td>' + esc(v) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div></div>';
  }
  box.innerHTML = m;
}

function render() {
  const q = document.querySelector('#q').value.toLowerCase();
  const f = document.querySelector('#f').value;
  const xs = data.filter(x => (!q || JSON.stringify(x).toLowerCase().includes(q)) && (f === 'ALL' || (x.decision || 'PENDING') === f));
  document.querySelector('#count').textContent = xs.length + ' candidates';
  document.querySelector('#cards').innerHTML = xs.length ? xs.map(x => `
    <article class="card ${(x.decision || '').toLowerCase()}">
      <div class="head">
        <h2>${esc(x.label)}</h2>
        <span class="status">${esc(x.decision || 'PENDING')}</span>
      </div>
      <div class="field"><label>Inferred definition</label><p>${esc(x.inferred_definition)}</p></div>
      <div class="grid">
        <div class="field"><label>Measure</label><code>${esc(x.measure)}</code></div>
        <div class="field"><label>Grain</label><code>${esc(x.grain.join(', ') || 'not specified')}</code></div>
      </div>
      <div class="grid">
        <div class="field"><label>Corrected business definition</label><textarea class="corrected-definition" placeholder="Optional canonical definition">${esc(x.corrected_definition)}</textarea></div>
        <div class="field"><label>Business aliases (comma-separated)</label><textarea class="aliases" placeholder="Example: revenue, net sales">${esc((x.aliases || []).join(', '))}</textarea></div>
      </div>
      <div class="evidence">
        <b>Evidence:</b> ${esc(x.evidence.join(', ') || 'none')}<br>
        <b>Profile:</b> ${esc(x.profile_notes.join('; ') || 'none')}
        <details><summary>Sample data</summary>${sampleHtml(x.samples)}</details>
      </div>
      <div class="actions">
        <select class="decision">
          <option ${x.decision==='APPROVE'?'selected':''}>APPROVE</option>
          <option ${x.decision==='REJECT'?'selected':''}>REJECT</option>
          <option ${x.decision==='CLARIFY'?'selected':''}>CLARIFY</option>
        </select>
        <textarea class="rationale" placeholder="Rationale required">${esc(x.rationale)}</textarea>
        <button onclick="save(this,'${esc(x.definition_id)}')">Save</button>
      </div>
    </article>
  `).join('') : '<p>No candidates match this view.</p>';
}

async function save(b, id) {
  const c = b.closest('.card');
  const r = await fetch('/label', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      domain: currentDomain,
      definition_id: id,
      decision: c.querySelector('.decision').value,
      rationale: c.querySelector('.rationale').value,
      corrected_definition: c.querySelector('.corrected-definition').value,
      aliases: c.querySelector('.aliases').value
    })
  });
  const o = await r.json();
  if (!r.ok) { alert(o.error); return; }
  const x = data.find(v => v.definition_id === id);
  x.decision = o.decision;
  x.rationale = o.rationale;
  x.corrected_definition = o.corrected_definition;
  x.aliases = o.aliases;
  render();
}

let reqCounter = 1;
async function mcpCall(method, params) {
  const req = {
    jsonrpc: "2.0",
    id: reqCounter++,
    method: method,
    params: params || {}
  };
  document.getElementById('rpc-req').textContent = JSON.stringify(req, null, 2);
  document.getElementById('rpc-res').textContent = "// Calling MCP server over JSON-RPC 2.0...";
  try {
    const res = await fetch('/mcp-rpc?domain=' + encodeURIComponent(currentDomain), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(req)
    });
    const d = await res.json();
    document.getElementById('rpc-res').textContent = JSON.stringify(d, null, 2);
  } catch (err) {
    document.getElementById('rpc-res').textContent = "// Error: " + err;
  }
}

document.querySelector('#q').oninput = render;
document.querySelector('#f').onchange = render;
render();
</script>
</body>
</html>
"""


def serve(
    registry: MultiDomainRegistry,
    default_domain: str,
    host: str,
    port: int,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def send_body(self, status: int, kind: str, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            u = urlparse(self.path)
            path = u.path
            query = dict([pair.split("=", 1) for pair in u.query.split("&")] if u.query else [])
            domain_info = registry.get(query.get("domain", default_domain))
            store = domain_info["store"]
            if path == "/api/items":
                self.send_body(
                    200, "application/json", json.dumps(store.review_items(), default=str)
                )
            elif path == "/":
                options_html = "\n".join(
                    f'<option value="{d["id"]}" {"selected" if d["id"] == domain_info["id"] else ""}>{d["label"]}</option>'
                    for d in registry.list_domains()
                )
                html_body = PAGE_TEMPLATE.replace(
                    "__ITEMS__", json.dumps(store.review_items(), default=str)
                ).replace("__DOMAIN_OPTIONS__", options_html).replace("__CURRENT_DOMAIN__", domain_info["id"])
                self.send_body(200, "text/html; charset=utf-8", html_body)
            else:
                self.send_body(404, "text/plain", "not found")

        def do_POST(self) -> None:
            u = urlparse(self.path)
            path = u.path
            query = dict([pair.split("=", 1) for pair in u.query.split("&")] if u.query else [])
            try:
                n = int(self.headers.get("Content-Length", "0"))
                p = json.loads(self.rfile.read(n)) if n > 0 else {}
                domain_id = p.get("domain") or query.get("domain", default_domain)
                domain_info = registry.get(domain_id)
                store = domain_info["store"]
                catalog = domain_info["catalog"]
                db_path = domain_info["database_path"]
                if path == "/mcp-rpc":
                    con_target = str(db_path) if db_path and db_path.exists() else ":memory:"
                    with duckdb.connect(con_target, read_only=bool(db_path and db_path.exists())) as c:
                        svc = InvestigationService(store, catalog, c)
                        resp = handle_rpc_message(p, svc)
                    self.send_body(
                        200, "application/json", json.dumps(resp or {}, default=str)
                    )
                    return
                if path == "/investigate":
                    con_target = str(db_path) if db_path and db_path.exists() else ":memory:"
                    with duckdb.connect(con_target, read_only=bool(db_path and db_path.exists())) as c:
                        r = investigate(p["question"], store, catalog, c)
                    self.send_body(
                        200,
                        "application/json",
                        json.dumps(
                            {
                                "status": r.status,
                                "definition": r.inferred_definition,
                                "evidence": [e.source_ref for e in r.evidence],
                                "sql": r.sql,
                                "columns": r.columns,
                                "rows": r.rows,
                                "message": r.message,
                            },
                            default=str,
                        ),
                    )
                    return
                if path != "/label":
                    raise LabelingError("not found")
                r = store.label(p["definition_id"], p["decision"], p["rationale"])
                if r.decision == "APPROVE":
                  store.enrich(
                    p["definition_id"],
                    p.get("corrected_definition", ""),
                    p.get("aliases", ""),
                  )
                enrichment = store.enrichments.get(p["definition_id"], {})
                self.send_body(
                    200,
                    "application/json",
                  json.dumps({
                    "decision": r.decision,
                    "rationale": r.rationale,
                    "corrected_definition": enrichment.get("corrected_definition", ""),
                    "aliases": enrichment.get("aliases", []),
                  }),
                )
            except (KeyError, json.JSONDecodeError, LabelingError, TypeError, ValueError) as e:
                self.send_body(400, "application/json", json.dumps({"error": str(e)}))

        def log_message(self, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"analytical memory & MCP inspector live at: http://{host}:{port}")
    print("domains loaded:", [d["id"] for d in registry.list_domains()])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--domain", default="tpcds")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args()

    registry = init_multi_domain_registry()
    serve(registry, a.domain, a.host, a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())