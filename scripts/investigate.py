"""Ask a question against approved analytical-memory definitions.

Usage:
    .venv/Scripts/python.exe scripts/investigate.py "What is total quantity by status?"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from semantic_induction.ingest import ingest  # noqa: E402
from semantic_induction.services import InvestigationService  # noqa: E402
from labeling_app import build_fulfillment_store, build_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--domain", choices=("tpch", "tpcds", "fulfillment"), default="tpch")
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--labels", type=Path, default=None)
    args = parser.parse_args()

    if args.domain == "fulfillment":
        db = args.database or (ROOT / "data/fulfillment_demo/fulfillment.duckdb")
        labels = args.labels or (ROOT / "data/fulfillment_demo/labels.json")
        store, catalog = build_store(db, labels, domain="fulfillment") if False else build_fulfillment_store(db, labels)
    elif args.domain == "tpcds":
        db = args.database or (ROOT / "data/tpcds/tpcds.duckdb")
        labels = args.labels or (ROOT / "data/tpcds/labels.json")
        store, catalog = build_store(db, labels, domain="tpcds")
    else:
        db = args.database or (ROOT / "data/tpch/tpch.duckdb")
        labels = args.labels or (ROOT / "data/tpch/labels.json")
        store, catalog = build_store(db, labels, domain="tpch")

    if not db.exists():
        print(f"database not found: {db}", file=sys.stderr)
        return 1

    with duckdb.connect(str(db), read_only=True) as connection:
        result = InvestigationService(store, catalog, connection).investigate(args.question)

    print(f"status: {result.status}")
    if result.message:
        print(result.message)
    if result.inferred_definition:
        print(f"definition: {result.inferred_definition}")
    if result.evidence:
        print("evidence:", ", ".join(item.source_ref for item in result.evidence))
    if result.sql:
        print(f"sql: {result.sql}")
    if result.columns:
        print("columns:", ", ".join(result.columns))
        for row in result.rows:
            print(row)
    return 0 if result.status == "ANSWERED" else 2


if __name__ == "__main__":
    raise SystemExit(main())