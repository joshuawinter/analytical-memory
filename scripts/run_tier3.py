"""Run the Tier 3 three-arm executable-equivalence experiment against TPC-H.

Requires SEMANTIC_INDUCTION_API_KEY set in the current terminal and the
optional 'anthropic' dependency installed (`pip install -e ".[anthropic]"`).
Prints per-question results for both arms plus the match-rate delta, which
is the whole finding described in docs/ARCHITECTURE.md's Tier 3 section.

Two caveats the printed numbers do not carry on their own:

1. MetricPlan currently supports one (aggregation, column) measure per
   plan, so the induced-layer arm can only answer single-measure questions.
   A question requiring several aggregates in one row (e.g. TPC-H q01's
   full 8-aggregate report) cannot be matched by this arm regardless of
   composer quality -- that is a coverage gap, not evidence of bad
   induction. The bundled question below is deliberately scoped to what
   the current architecture can honestly attempt.
2. Do not use a famous, widely-published benchmark query's literal text as
   the raw-schema arm's "business question": a frontier model has likely
   memorized it, so a high raw-schema match rate may reflect recall, not
   schema-driven reasoning, which invalidates it as a control. Reference
   answers here are computed from independently-authored SQL, never copied
   from data/tpch/answers/, so neither arm is graded against its own or a
   memorized reference's column aliases.

Usage:
    .venv/Scripts/python.exe scripts/run_tier3.py
    .venv/Scripts/python.exe scripts/run_tier3.py --database data/tpch/tpch.duckdb
"""
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from semantic_induction.aggregate import aggregate  # noqa: E402
from semantic_induction.extract import extract_corpus  # noqa: E402
from semantic_induction.induce import induce  # noqa: E402
from semantic_induction.ingest import ingest  # noqa: E402
from semantic_induction.naming import EnvironmentNamingConfig  # noqa: E402
from semantic_induction.profile import profile_database  # noqa: E402
from semantic_induction.tier3 import (  # noqa: E402
    AnthropicPlanComposer,
    AnthropicSqlComposer,
    BusinessQuestion,
    INDUCED_LAYER,
    RAW_SCHEMA,
    run_tier3,
)

# A small, honestly-scoped set of held-out business questions. Each
# composer only ever sees this natural-language text -- never the original
# SQL in data/tpch/queries/, and never a famous benchmark query's exact
# wording (see the memorization caveat above).
QUESTIONS = [
    BusinessQuestion(
        "quantity_by_flag_status",
        "What is the total quantity shipped, grouped by return flag and "
        "line status, for line items shipped on or before 1998-09-02?",
    ),
    BusinessQuestion(
        "supply_cost_by_part_germany",
        "For each individual part (grouped by part number, not part "
        "category), what is its total supply cost across suppliers based "
        "in Germany?",
    ),
]

# Ground truth authored independently of both composers and of the bundled
# reference CSVs in data/tpch/answers/ -- neither arm is grading its own or
# a memorized query's homework. Kept to a single aggregate to match what
# MetricPlan supports today (see caveat 1 above).
#
# quantity_by_flag_status is a single-table sanity check: it should be
# close to trivial for any competent model and mainly proves the harness
# works end to end.
#
# supply_cost_by_part_germany is the informative one: it requires a real
# three-table join (partsupp -> supplier -> nation) and an exact-match
# string filter. The induced-layer arm gets that join path and filter
# attached automatically from a corpus-demonstrated signature (verified
# offline against this exact reference SQL before being wired in here);
# the raw-schema arm has to independently discover the correct join keys
# and reproduce the filter's exact literal from the schema alone.
REFERENCE_SQL = {
    "quantity_by_flag_status": (
        "SELECT l_returnflag, l_linestatus, SUM(l_quantity) AS metric_value "
        "FROM lineitem WHERE l_shipdate <= DATE '1998-09-02' "
        "GROUP BY l_returnflag, l_linestatus"
    ),
    "supply_cost_by_part_germany": (
        "SELECT ps.ps_partkey, SUM(ps.ps_supplycost) AS metric_value "
        "FROM partsupp ps, supplier s, nation n "
        "WHERE ps.ps_suppkey = s.s_suppkey AND s.s_nationkey = n.n_nationkey "
        "AND n.n_name = 'GERMANY' GROUP BY ps.ps_partkey"
    ),
}


def _write_reference_csv(connection, sql: str, path: Path) -> None:
    result = connection.execute(sql)
    columns = [description[0] for description in result.description]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(result.fetchall())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "data/tpch/tpch.duckdb")
    parser.add_argument("--min-support", type=int, default=1)
    args = parser.parse_args()

    config = EnvironmentNamingConfig()
    if not config.api_key:
        print(f"missing API key environment variable: {config.api_key_env}", file=sys.stderr)
        print("set it in this terminal before running, e.g.:", file=sys.stderr)
        print('  $env:SEMANTIC_INDUCTION_API_KEY = "..."', file=sys.stderr)
        return 1
    if not args.database.exists():
        print(f"database not found: {args.database}", file=sys.stderr)
        print("generate it first, e.g.:", file=sys.stderr)
        print(
            "  .venv/Scripts/python.exe scripts/fetch_tpch.py --scale 0.01 "
            f"--database {args.database}",
            file=sys.stderr,
        )
        return 1

    try:
        raw_schema_composer = AnthropicSqlComposer(config)
        induced_layer_composer = AnthropicPlanComposer(config)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1

    catalog, queries = ingest(ROOT / "data/tpch/ddl.sql", ROOT / "data/tpch/queries")
    facts = extract_corpus(queries, catalog)

    with tempfile.TemporaryDirectory() as answer_dir_name:
        answer_dir = Path(answer_dir_name)
        with duckdb.connect(str(args.database), read_only=True) as connection:
            profiles = profile_database(connection, catalog)
            layer = induce(
                aggregate(facts),
                catalog,
                facts,
                min_support=args.min_support,
                profiles=profiles,
            )
            for question in QUESTIONS:
                _write_reference_csv(
                    connection, REFERENCE_SQL[question.question_id], answer_dir / f"{question.question_id}.csv"
                )
            report = run_tier3(
                QUESTIONS,
                catalog,
                layer,
                connection,
                answer_dir,
                raw_schema_composer,
                induced_layer_composer,
            )

    for result in report.results:
        status = "MATCH" if result.match else "MISMATCH"
        detail = f" ({result.error})" if result.error else ""
        sql_line = f"\n    SQL: {result.sql}" if result.sql else ""
        print(f"[{result.arm}] {result.question_id}: {status}{detail}{sql_line}")

    print()
    print(f"raw schema match rate:    {report.match_rate(RAW_SCHEMA):.0%}")
    print(f"induced layer match rate: {report.match_rate(INDUCED_LAYER):.0%}")
    print(f"delta (induced - raw):    {report.delta():+.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
