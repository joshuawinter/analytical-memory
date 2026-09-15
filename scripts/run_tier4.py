"""Run the Tier 4 conflict-precision harness (ARCHITECTURE.md's Tier 4 section).

Offline and deterministic -- no LLM, no API key, no database required
(profiles sharpen the result but are optional; see below).

Detection is a group-by; separating a real definitional disagreement from
benign scoping/grain variation is "the actual research problem." This script
runs Stage 4b's detect_conflicts against a small set of hand-authored TPC-DS
query pairs with known ground truth and reports precision, recall, and noise
rate against ARCHITECTURE.md's own Tier 4 formula.

Usage:
    .venv/Scripts/python.exe scripts/run_tier4.py
    .venv/Scripts/python.exe scripts/run_tier4.py --database data/tpcds/tpcds.duckdb
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from semantic_induction.conflicts import detect_conflicts  # noqa: E402
from semantic_induction.extract import extract_corpus  # noqa: E402
from semantic_induction.ingest import ingest  # noqa: E402
from semantic_induction.profile import profile_database  # noqa: E402
from semantic_induction.tier4 import Tier4Scenario, run_tier4  # noqa: E402

# Ground truth for the fixture queries in data/tpcds/tier4/queries/. Each
# scenario names which query IDs should (or should not) end up as competing
# DEFINITIONAL candidates. See that directory's queries for the actual SQL.
SCENARIOS = [
    Tier4Scenario(
        scenario_id="returned_ticket_inclusion",
        query_ids=frozenset({"a1_gross_revenue", "a2_gross_revenue", "b1_returned_ticket_revenue", "b2_returned_ticket_revenue"}),
        expect_conflict=True,
        description=(
            "Revenue including vs excluding tickets tied to a return is a genuine "
            "definitional split. The inclusion predicate recurs across both "
            "b1 and b2, so it should be treated as candidate-defining, not "
            "a one-off narrowing filter."
        ),
    ),
    Tier4Scenario(
        scenario_id="wholesale_cost_floor",
        query_ids=frozenset({"a1_gross_revenue", "c1_full_price_only_revenue"}),
        expect_conflict=False,
        description=(
            "A single-observation filter on a continuous, high-cardinality "
            "column (wholesale_cost) is a known, accepted gap: it neither "
            "recurs nor is low-cardinality, so it is treated as a narrowing "
            "choice rather than a rival definition. Precision over recall, "
            "per ARCHITECTURE.md -- not a bug."
        ),
    ),
    Tier4Scenario(
        scenario_id="monthly_grain",
        query_ids=frozenset({"a1_gross_revenue", "d1_monthly_revenue"}),
        expect_conflict=False,
        description="Grouping by year+month vs year alone is a grain difference, not a competing definition.",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "data/tpcds/tpcds.duckdb")
    args = parser.parse_args()

    root = ROOT / "data/tpcds"
    catalog, queries = ingest(root / "ddl.sql", root / "tier4/queries")
    facts = extract_corpus(queries, catalog)

    profiles = None
    if args.database.exists():
        with duckdb.connect(str(args.database), read_only=True) as connection:
            profiles = profile_database(connection, catalog, sample_size=5, top_values=5)
    else:
        print(f"note: {args.database} not found; running without profile evidence", file=sys.stderr)

    conflicts = detect_conflicts(None, facts, min_support=1, profiles=profiles)
    report = run_tier4(conflicts, SCENARIOS)

    for result in report.results:
        status = "PASS" if result.correct else "FAIL"
        print(f"[{status}] {result.scenario_id}: expected={result.expected} found={result.found} (matched_kind={result.matched_kind})")
        print(f"    {result.description}")

    print()
    precision = report.precision()
    recall = report.recall()
    noise_rate = report.noise_rate()
    print(f"precision:  {precision:.0%}" if precision is not None else "precision:  n/a (nothing flagged)")
    print(f"recall:     {recall:.0%}" if recall is not None else "recall:     n/a (no real conflicts labeled)")
    print(f"noise_rate: {noise_rate:.0%}" if noise_rate is not None else "noise_rate: n/a")

    return 0 if all(result.correct for result in report.results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
