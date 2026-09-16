"""Model Context Protocol (MCP) server for analytical memory and investigations."""
from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from semantic_induction.labeling import LabelingError
from semantic_induction.services import InvestigationService, investigation_payload

SERVER_INFO = {
    "name": "semantic-induction-mcp",
    "version": "0.1.0",
}

TOOLS = [
    {
        "name": "search_business_memory",
        "description": "Search corporate analytical memory for concepts, metric definitions, and aliases matching a question.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The business question or search keywords.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of matched items to return.",
                    "default": 10,
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "get_review_candidates",
        "description": "List all metric candidates in analytical memory along with their inferred definitions, review decisions, and evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "run_approved_investigation",
        "description": "Execute an analytical investigation for a business question using approved metric definitions only. Returns NEEDS_REVIEW if unapproved.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The business question to investigate.",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "record_review_decision",
        "description": (
            "Record a human's APPROVE/REJECT/CLARIFY ruling on a metric candidate, with rationale, on the "
            "tamper-evident audit ledger. The decision and rationale must come from the human the calling "
            "client is acting for -- never fabricate a decision or invent a rationale on their behalf. "
            "decided_by must identify that human, not the calling agent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "definition_id": {
                    "type": "string",
                    "description": "The definition_id from get_review_candidates identifying which candidate this ruling is for.",
                },
                "decision": {
                    "type": "string",
                    "enum": ["APPROVE", "REJECT", "CLARIFY"],
                },
                "rationale": {
                    "type": "string",
                    "description": "Why -- ideally a generalizable rule, not just a verdict. Required.",
                },
                "decided_by": {
                    "type": "string",
                    "description": "Who is actually making this ruling (a name or identifier for the human), not the calling agent.",
                },
                "corrected_definition": {
                    "type": "string",
                    "description": "Optional canonical business definition, only used when decision is APPROVE.",
                    "default": "",
                },
                "aliases": {
                    "type": "string",
                    "description": "Optional comma-separated business aliases, only used when decision is APPROVE.",
                    "default": "",
                },
            },
            "required": ["definition_id", "decision", "rationale", "decided_by"],
        },
    },
]

RESOURCES = [
    {
        "uri": "memory://concepts",
        "name": "Business Concepts",
        "description": "All known business concepts and their aliases.",
        "mimeType": "application/json",
    },
    {
        "uri": "memory://metric_definitions",
        "name": "Metric Definitions",
        "description": "All metric definitions, inferred logic, and review status.",
        "mimeType": "application/json",
    },
    {
        "uri": "memory://evidence",
        "name": "Evidence Registry",
        "description": "All registered evidence sources and queries.",
        "mimeType": "application/json",
    },
    {
        "uri": "memory://resolutions",
        "name": "Human Resolutions",
        "description": "All recorded human review decisions and rationales.",
        "mimeType": "application/json",
    },
]


def _format_investigation_text(payload: dict[str, Any]) -> str:
    lines = [f"STATUS: {payload['status']}"]
    if payload.get("message"):
        lines.append(f"MESSAGE: {payload['message']}")
    if payload.get("definition"):
        lines.append(f"DEFINITION: {payload['definition']}")
    if payload.get("evidence"):
        lines.append("EVIDENCE: " + ", ".join(payload["evidence"]))
    if payload.get("sql"):
        lines.append(f"SQL: {payload['sql']}")
    if payload.get("columns"):
        lines.append("RESULT:")
        lines.append(" | ".join(payload["columns"]))
        for row in payload.get("rows", []):
            lines.append(" | ".join(str(val) for val in row))
    return "\n".join(lines)


def handle_rpc_message(msg: dict[str, Any], service: InvestigationService) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 MCP request and return the response."""
    msg_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params", {}) or {}

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                },
                "serverInfo": SERVER_INFO,
            },
        }

    if method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {},
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": TOOLS,
            },
        }

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {}) or {}

        if tool_name == "search_business_memory":
            question = args.get("question", "")
            limit = args.get("limit", 10)
            hits = service.search(question, limit=limit)
            hit_data = [
                {
                    "kind": hit.kind,
                    "object_id": hit.object_id,
                    "score": hit.score,
                    "matched_terms": list(hit.matched_terms),
                }
                for hit in hits
            ]
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(hit_data, indent=2),
                        }
                    ],
                    "isError": False,
                },
            }

        if tool_name == "get_review_candidates":
            items = service.review_items()
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(items, indent=2, default=str),
                        }
                    ],
                    "isError": False,
                },
            }

        if tool_name == "run_approved_investigation":
            question = args.get("question", "")
            result = service.investigate(question)
            payload = investigation_payload(result)
            text = _format_investigation_text(payload)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ],
                    "isError": result.status in {"UNSUPPORTED", "EXECUTION_FAILED"},
                },
            }

        if tool_name == "record_review_decision":
            try:
                resolution = service.record_decision(
                    args.get("definition_id", ""),
                    args.get("decision", ""),
                    args.get("rationale", ""),
                    args.get("decided_by", ""),
                    args.get("corrected_definition", ""),
                    args.get("aliases", ""),
                )
            except LabelingError as error:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"REJECTED: {error}"}],
                        "isError": True,
                    },
                }
            text = (
                f"RECORDED: {resolution.decision} on {resolution.target_id} "
                f"by {resolution.decided_by} ({resolution.resolution_id})"
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Unknown tool: {tool_name}",
            },
        }

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "resources": RESOURCES,
            },
        }

    if method == "resources/read":
        uri = params.get("uri")
        mem = service.store.memory
        data: Any = None
        if uri == "memory://concepts":
            data = [
                {
                    "concept_id": c.concept_id,
                    "preferred_label": c.preferred_label,
                    "aliases": list(c.aliases),
                    "definition": c.definition,
                }
                for c in mem.concepts.values()
            ]
        elif uri == "memory://metric_definitions":
            data = [
                {
                    "definition_id": m.definition_id,
                    "concept_id": m.concept_id,
                    "inferred_definition": m.inferred_definition,
                    "status": m.status,
                    "confidence": m.confidence,
                }
                for m in mem.metric_definitions.values()
            ]
        elif uri == "memory://evidence":
            data = [
                {
                    "evidence_id": e.evidence_id,
                    "source_type": e.source_type,
                    "source_ref": e.source_ref,
                }
                for e in mem.evidence.values()
            ]
        elif uri == "memory://resolutions":
            data = [
                {
                    "resolution_id": r.resolution_id,
                    "target_id": r.target_id,
                    "decision": r.decision,
                    "rationale": r.rationale,
                    "decided_by": r.decided_by,
                    "decided_at": str(r.decided_at),
                }
                for r in mem.resolutions.values()
            ]

        if data is not None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(data, indent=2),
                        }
                    ]
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32602,
                "message": f"Resource not found: {uri}",
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}",
        },
    }


def run_stdio_server(service: InvestigationService, in_stream: TextIO = sys.stdin, out_stream: TextIO = sys.stdout) -> None:
    """Run the MCP server reading JSON-RPC messages from stdin and writing to stdout."""
    for line in in_stream:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            out_stream.write(json.dumps(err_resp) + "\n")
            out_stream.flush()
            continue

        resp = handle_rpc_message(req, service)
        if resp is not None:
            out_stream.write(json.dumps(resp) + "\n")
            out_stream.flush()
