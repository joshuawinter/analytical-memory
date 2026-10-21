"""Run the Tier 4 conflict-precision harness (ARCHITECTURE.md's Tier 4 section).

Offline and deterministic -- no LLM, no API key. A database is optional:
Stage 1b profiles sharpen the classifier (they are what lets it tell a
one-off scope filter on a high-cardinality column from a definitional one),
and the generated set's labels differ between the two modes.

Two scenario sets run:

  handcrafted  the original three TPC-DS pairs in data/tpcds/tier4/queries/
  generated    23 labelled scenarios in data/tpcds/tier4/generated/, one
               isolated corpus each, written by scripts/build_tier4_corpus.py.
               Labels are semantic (definition vs scope), so several are set
               against what the classifier is expected to do and carry
               known_gap. Precision and recall are reported against the
               labels; the exit code only fails on misclassifications that
               are NOT documented gaps, and lists documented gaps that
               unexpectedly pass so the documentation gets fixed.

Usage:
    .venv/Scripts/python.exe scripts/run_tier4.py
    .venv/Scripts/python.exe scripts/run_tier4.py --set generated
    .venv/Scripts/python.exe scripts/run_tier4.py --database data/tpcds/tpcds.duckdb
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from semantic_induction.conflicts import detect_conflicts  # noqa: E402
from semantic_induction.extract import extract_corpus  # noqa: E402
from semantic_induction.ingest import ingest  # noqa: E402
from semantic_induction.profile import profile_database  # noqa: E402
from semantic_induction.tier4 import Tier4Report, Tier4Scenario, run_generated_tier4, run_tier4  # noqa: E402

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


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _print_report(title: str, report: Tier4Report, verbose: bool) -> None:
    print(f"== {title}: {len(report.results)} scenarios ==")
    for result in report.results:
        status = "PASS" if result.correct else ("GAP " if result.known_gap else "FAIL")
        print(f"[{status}] {result.scenario_id}: expected={result.expected} found={result.found} (matched_kind={result.matched_kind})")
        if verbose or not result.correct:
            print(f"    {result.description}")
    print(
        f"tp={report.true_positives} fp={report.false_positives} fn={report.false_negatives} tn={report.true_negatives}  "
        f"precision={_percent(report.precision())} recall={_percent(report.recall())} noise_rate={_percent(report.noise_rate())}"
    )
    print()


def _family_breakdown(report: Tier4Report) -> None:
    by_family: dict[str, list] = defaultdict(list)
    for result in report.results:
        family = result.description.split("]")[0].lstrip("[") if result.description.startswith("[") else "handcrafted"
        by_family[family].append(result)
    print("by family (correct / total):")
    for family, results in sorted(by_family.items()):
        correct = sum(1 for r in results if r.correct)
        print(f"  {family:24} {correct}/{len(results)}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "data/tpcds/tpcds.duckdb")
    parser.add_argument("--set", choices=("handcrafted", "generated", "all"), default="all")
    parser.add_argument("--verbose", action="store_true", help="print every scenario's rationale, not just failures")
    args = parser.parse_args()

    root = ROOT / "data/tpcds"
    ddl = root / "ddl.sql"
    catalog, _ = ingest(ddl, root / "tier4/queries")

    profiles = None
    if args.database.exists():
        with duckdb.connect(str(args.database), read_only=True) as connection:
            profiles = profile_database(connection, catalog, sample_size=5, top_values=5)
        print(f"profiles: from {args.database}")
    else:
        print(f"note: {args.database} not found; running without profile evidence (labels switch to the no-profile column)", file=sys.stderr)
    print()

    reports: list[Tier4Report] = []
    if args.set in ("handcrafted", "all"):
        _, queries = ingest(ddl, root / "tier4/queries")
        facts = extract_corpus(queries, catalog)
        handcrafted = run_tier4(detect_conflicts(None, facts, min_support=1, profiles=profiles), SCENARIOS)
        _print_report("handcrafted", handcrafted, args.verbose)
        reports.append(handcrafted)
    if args.set in ("generated", "all"):
        generated = run_generated_tier4(root / "tier4/generated", ddl, profiles)
        _print_report("generated", generated, args.verbose)
        _family_breakdown(generated)
        reports.append(generated)

    combined = Tier4Report(tuple(result for report in reports for result in report.results))
    if len(reports) > 1:
        print(
            f"combined: {len(combined.results)} scenarios  tp={combined.true_positives} fp={combined.false_positives} "
            f"fn={combined.false_negatives} tn={combined.true_negatives}  precision={_percent(combined.precision())} "
            f"recall={_percent(combined.recall())} noise_rate={_percent(combined.noise_rate())}"
        )
    unexpected = combined.unexpected_failures
    surprising = combined.surprising_passes
    if unexpected:
        print(f"UNEXPECTED FAILURES ({len(unexpected)}): " + ", ".join(r.scenario_id for r in unexpected))
    if surprising:
        print(f"documented gaps that now pass ({len(surprising)}), update the manifest: " + ", ".join(r.scenario_id for r in surprising))
    print("tier 4:", "PASS (no undocumented misclassification)" if not unexpected else "FAIL")
    return 0 if not unexpected else 1


if __name__ == "__main__":
    raise SystemExit(main())
