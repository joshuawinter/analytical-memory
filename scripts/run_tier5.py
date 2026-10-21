"""Run the Tier 5 harness: do human rulings outrank frequency?

Offline and deterministic. No database file, no API key. Builds the fixture
world in an in-memory DuckDB from data/tpcds/ddl.sql and
data/tpcds/tier5/seed.sql, induces the thirteen fixture queries, and runs
the four scenarios described in ARCHITECTURE.md's Tier 5 section. Rulings,
the audit ledger, and the memory store are written to a temporary directory
and discarded.

Usage:
    .venv/Scripts/python.exe scripts/run_tier5.py
    .venv/Scripts/python.exe scripts/run_tier5.py --keep-labels out/tier5_labels.json
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from semantic_induction.tier5 import run_tier5  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keep-labels", type=Path, default=None,
        help="write rulings, ledger, and memory store here instead of a temp dir, for inspection",
    )
    args = parser.parse_args()

    if args.keep_labels is not None:
        report = run_tier5(labels_path=args.keep_labels)
    else:
        with tempfile.TemporaryDirectory() as directory:
            report = run_tier5(labels_path=Path(directory) / "labels.json")

    print(
        f"fork: majority {report.majority_definition_id} ({report.majority_support} queries) "
        f"vs minority {report.minority_definition_id} ({report.minority_support} queries)"
    )
    print()
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.scenario_id}")
        print(f"    {result.detail}")
    print()
    print(f"answered from frequency while a ruling was in force: {report.answered_from_frequency} (must be 0)")
    print(f"answered while contested with no ruling in force:    {report.answered_while_contested} (must be 0)")
    print(f"tier 5: {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
