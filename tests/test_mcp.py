import io
import json
import duckdb

from semantic_induction.labeling import LabelingStore
from semantic_induction.memory import (
    AnalyticalMemory,
    BusinessConcept,
    Evidence,
    MetricDefinition,
)
from semantic_induction.mcp_server import handle_rpc_message, run_stdio_server
from semantic_induction.services import InvestigationService


def _test_service(approved: bool = True) -> InvestigationService:
    memory = AnalyticalMemory(
        concepts={
            "fulfillment.otif": BusinessConcept(
                "fulfillment.otif",
                "On-Time-In-Full Fulfillment",
                aliases=("OTIF", "on time in full"),
                definition="Delivered by promised date with ordered quantity fulfilled.",
            )
        },
        evidence={
            "demo:events": Evidence("demo:events", "GENERATED_DATA", "order_event and inventory_snapshot")
        },
        metric_definitions={
            "metric:fulfillment:otif": MetricDefinition(
                "metric:fulfillment:otif",
                "fulfillment.otif",
                ("OTIF", "fulfillment"),
                (),
                evidence_ids=("demo:events",),
                inferred_definition="On-time-in-full: delivered by promised date and quantity fulfilled.",
                query_sql="SELECT '2026-01-01' AS month, 40 AS orders, 40 AS otif_orders, 0 AS late_orders",
            )
        },
    )
    store = LabelingStore(memory)
    if approved:
        store.label("metric:fulfillment:otif", "APPROVE", "Verified against operations.")
    connection = duckdb.connect()
    return InvestigationService(store, {}, connection)


def test_mcp_initialize_and_ping():
    service = _test_service()
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    }
    resp = handle_rpc_message(init_req, service)
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "semantic-induction-mcp"
    assert "tools" in resp["result"]["capabilities"]

    ping_req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    ping_resp = handle_rpc_message(ping_req, service)
    assert ping_resp["id"] == 2
    assert ping_resp["result"] == {}


def test_mcp_tools_list_and_search():
    service = _test_service()
    list_req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    list_resp = handle_rpc_message(list_req, service)
    tools = [t["name"] for t in list_resp["result"]["tools"]]
    assert "search_business_memory" in tools
    assert "run_approved_investigation" in tools
    assert "get_review_candidates" in tools

    search_req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "search_business_memory",
            "arguments": {"question": "OTIF"},
        },
    }
    search_resp = handle_rpc_message(search_req, service)
    content = json.loads(search_resp["result"]["content"][0]["text"])
    assert len(content) > 0
    assert any(hit["object_id"] == "fulfillment.otif" for hit in content)


def test_mcp_run_approved_investigation_and_approval_gate():
    service_approved = _test_service(approved=True)
    call_req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "run_approved_investigation",
            "arguments": {"question": "Why did on-time-in-full decline?"},
        },
    }
    resp = handle_rpc_message(call_req, service_approved)
    text = resp["result"]["content"][0]["text"]
    assert "STATUS: ANSWERED" in text
    assert "2026-01-01" in text

    service_unapproved = _test_service(approved=False)
    resp_unapproved = handle_rpc_message(call_req, service_unapproved)
    text_unapproved = resp_unapproved["result"]["content"][0]["text"]
    assert "STATUS: NEEDS_REVIEW" in text_unapproved


def test_mcp_resources():
    service = _test_service()
    list_req = {"jsonrpc": "2.0", "id": 6, "method": "resources/list"}
    resp = handle_rpc_message(list_req, service)
    uris = [r["uri"] for r in resp["result"]["resources"]]
    assert "memory://concepts" in uris
    assert "memory://metric_definitions" in uris

    read_req = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "resources/read",
        "params": {"uri": "memory://concepts"},
    }
    read_resp = handle_rpc_message(read_req, service)
    data = json.loads(read_resp["result"]["contents"][0]["text"])
    assert data[0]["concept_id"] == "fulfillment.otif"


def test_mcp_stdio_stream_runner():
    service = _test_service()
    in_lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n",
        json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "run_approved_investigation", "arguments": {"question": "OTIF"}},
        }) + "\n",
    ]
    in_stream = io.StringIO("".join(in_lines))
    out_stream = io.StringIO()

    run_stdio_server(service, in_stream=in_stream, out_stream=out_stream)
    out_lines = [json.loads(line) for line in out_stream.getvalue().splitlines() if line.strip()]

    assert len(out_lines) == 2
    assert out_lines[0]["id"] == 1
    assert out_lines[1]["id"] == 2
    assert "STATUS: ANSWERED" in out_lines[1]["result"]["content"][0]["text"]
