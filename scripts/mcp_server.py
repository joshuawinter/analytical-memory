"""Run the Model Context Protocol (MCP) stdio server.

Usage:
    .venv/Scripts/python.exe scripts/mcp_server.py [--domain fulfillment]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from semantic_induction.ingest import ingest  # noqa: E402
from semantic_induction.mcp_server import run_stdio_server  # noqa: E402
from semantic_induction.services import InvestigationService  # noqa: E402
from labeling_app import build_fulfillment_store, build_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Analytical Memory MCP Stdio Server")
    parser.add_argument("--domain", choices=("tpch", "tpcds", "fulfillment"), default="fulfillment")
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--labels", type=Path, default=None)
    args = parser.parse_args()

    if args.domain == "fulfillment":
        database = args.database or (ROOT / "data" / "fulfillment_demo" / "fulfillment.duckdb")
        labels = args.labels or (ROOT / "data" / "fulfillment_demo" / "labels.json")
        if not database.exists():
            print(f"database not found: {database}", file=sys.stderr)
            return 1
        store, catalog = build_fulfillment_store(database, labels)
    elif args.domain == "tpcds":
        database = args.database or (ROOT / "data" / "tpcds" / "tpcds.duckdb")
        labels = args.labels or (ROOT / "data" / "tpcds" / "labels.json")
        store, catalog = build_store(database, labels, domain="tpcds")
    else:
        database = args.database or (ROOT / "data" / "tpch" / "tpch.duckdb")
        labels = args.labels or (ROOT / "data" / "tpch" / "labels.json")
        if not database.exists():
            print(f"database not found: {database}", file=sys.stderr)
            return 1
        store, catalog = build_store(database, labels, domain="tpch")

    if database and database.exists():
        with duckdb.connect(str(database), read_only=True) as connection:
            service = InvestigationService(store, catalog, connection)
            run_stdio_server(service)
    else:
        connection = duckdb.connect()
        service = InvestigationService(store, catalog, connection)
        run_stdio_server(service)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
