"""Export an induced semantic model to Apache Ossie YAML format.

Usage:
    .venv/Scripts/python.exe scripts/export_ossie.py --domain tpcds --out tpcds_ossie.yaml
    .venv/Scripts/python.exe scripts/export_ossie.py --domain tpch --out tpch_ossie.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from semantic_induction.aggregate import aggregate  # noqa: E402
from semantic_induction.extract import extract_corpus  # noqa: E402
from semantic_induction.induce import induce  # noqa: E402
from semantic_induction.ingest import ingest  # noqa: E402
from semantic_induction.ossie_export import export_ossie_yaml  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export induced semantic layer to Apache Ossie YAML")
    parser.add_argument("--domain", choices=("tpch", "tpcds"), default="tpcds")
    parser.add_argument("--min-support", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    data_dir = ROOT / "data" / args.domain
    ddl_path = data_dir / "ddl.sql"
    queries_dir = data_dir / "queries"

    if not ddl_path.exists() or not queries_dir.exists():
        print(f"Data not found in {data_dir}. Run scripts/fetch_{args.domain}.py first.", file=sys.stderr)
        return 1

    catalog, queries = ingest(ddl_path, queries_dir)
    facts = extract_corpus(queries, catalog)
    stats = aggregate(facts)
    layer = induce(stats, catalog, facts, min_support=args.min_support)

    model_name = f"{args.domain}_induced_model"
    yaml_text = export_ossie_yaml(layer, catalog, model_name=model_name)

    if args.out:
        args.out.write_text(yaml_text, encoding="utf-8")
        print(f"Exported {len(layer.entities)} datasets, {len(layer.measures)} measures, and {len(layer.metrics)} metrics to {args.out}")
    else:
        print(yaml_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
