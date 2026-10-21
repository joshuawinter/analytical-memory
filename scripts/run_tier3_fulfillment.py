"""Run the Tier 3 three-arm executable-equivalence experiment against the
order-to-cash fulfillment demo domain.

This is the demo/thesis unification piece: RUNBOOK.md's fulfillment demo
(build_fulfillment_demo.py -> investigate_fulfillment_demo.py) shows the
induced-layer answer being right and not having read truth.json, but it
never shows what a raw-schema-only answer would have gotten wrong -- there
is no counterfactual on screen. This script runs the same RAW_SCHEMA vs.
INDUCED_LAYER comparison Tier 3 already proves on TPC-H, against the
fulfillment domain itself instead of abstract benchmark queries, so the
demo and the thesis proof are the same narrative.

Requires SEMANTIC_INDUCTION_API_KEY set in the current terminal and the
optional 'anthropic' dependency installed (`pip install -e ".[anthropic]"`).

Scope, honestly stated -- deliberately narrower than the OTIF story today:

1. This does not yet include the stockout-driven "why" question
   ("how many shipments were delayed by a stockout, by warehouse?"), even
   though that is the actual causal claim in
   data/fulfillment_demo/truth.json ("W03 stockouts caused the decline").
   That question requires joining sales_order to order_event, an event log
   with 3 rows per order (CREATED/SHIPPED/DELIVERED). detect_fanout_risk
   (induce.py) correctly excludes that join once profiles are supplied,
   because it only checks raw join-key uniqueness via TableProfile -- it
   has no way to see that a filter like event_type='SHIPPED' would narrow
   the join to one row per order in practice. This is the safety check
   working as intended, not a bug, and dropping `profiles=` from induce()
   to route around it would be a real correctness regression, not a fix.
   Teaching fanout detection to trust a filter-narrowed join (using
   evidence, not just raw column uniqueness) is real, separately-scoped
   future work -- generalizable well beyond this one demo.
2. "Late delivery" (event_time > promised_date) is absent for a different
   reason: extraction only captures equality-based join edges (optionally
   with a time offset) and literal-value predicates. A column-to-column
   inequality like `event_time > promised_date` is silently dropped by
   both _join_edges (exp.EQ only) and _predicates (_is_join_comparison
   skips it) -- there is currently no way for a MetricPlan to express it.
3. The bundled question is NOT the OTIF rate itself. OTIF is a ratio
   (on-time-in-full orders / total orders), and MetricPlan currently
   supports one (aggregation, column) measure per plan -- the same
   limitation documented in run_tier3.py. The rate becomes Tier-3-
   comparable once composite/ratio metrics land (see ARCHITECTURE.md's
   "Metric-to-metric lineage" section) -- this script's scaffolding does
   not need to change when that happens, only the QUESTIONS list.

Usage:
    .venv/Scripts/python.exe scripts/run_tier3_fulfillment.py
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
from semantic_induction.spend import (  # noqa: E402
    COMPARISON_MODELS,
    DryRunClient,
    StaticModelConfig,
    estimate_dry_run,
    exact_input_tokens,
    open_cache,
    open_ledger,
    render_dry_run,
)
from semantic_induction.tier3 import (  # noqa: E402
    AnthropicPlanComposer,
    AnthropicSqlComposer,
    BusinessQuestion,
    INDUCED_LAYER,
    RAW_SCHEMA,
    dry_run_responder,
    run_tier3,
)

DOMAIN_ROOT = ROOT / "data/fulfillment_demo"
DATABASE = DOMAIN_ROOT / "fulfillment.duckdb"

# Held-out business question, decomposed from the OTIF investigation into
# the single-aggregate, single-table shape both current architecture limits
# (see module docstring) allow today. Wording is deliberately distinct from
# data/fulfillment_demo/queries/orders_by_warehouse.sql -- this is the
# held-out test, not a corpus query restated.
QUESTIONS = [
    BusinessQuestion(
        "orders_by_warehouse_feb_2026",
        "How many orders were placed in February 2026, broken out by "
        "warehouse?",
    ),
]

# Ground truth authored independently of both composers. Verified offline
# against the live database before being wired in here.
REFERENCE_SQL = {
    "orders_by_warehouse_feb_2026": (
        "SELECT warehouse_id, count(*) AS metric_value FROM sales_order "
        "WHERE order_date >= DATE '2026-02-01' AND order_date < DATE '2026-03-01' "
        "GROUP BY warehouse_id"
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
    parser.add_argument("--dry-run", action="store_true", help="make no API call; record and price what a live run would send")
    parser.add_argument("--model", default=None, help="model id for the dry-run estimate")
    parser.add_argument("--exact-tokens", action="store_true", help="with --dry-run and a key: exact input counts via count_tokens")
    args = parser.parse_args()

    config = EnvironmentNamingConfig()
    if not DATABASE.exists():
        print(f"database not found: {DATABASE}", file=sys.stderr)
        print("generate it first:", file=sys.stderr)
        print("  .venv/Scripts/python.exe scripts/build_fulfillment_demo.py", file=sys.stderr)
        return 1

    dry: DryRunClient | None = None
    if args.dry_run:
        model = args.model or config.model or "claude-sonnet-4-5"
        dry = DryRunClient(dry_run_responder, cache=open_cache())
        static = StaticModelConfig(model)
        raw_schema_composer = AnthropicSqlComposer(static, client=dry)
        induced_layer_composer = AnthropicPlanComposer(static, client=dry)
    else:
        if not config.api_key:
            print(f"missing API key environment variable: {config.api_key_env}", file=sys.stderr)
            print("set it in this terminal before running, e.g.:", file=sys.stderr)
            print('  $env:SEMANTIC_INDUCTION_API_KEY = "..."', file=sys.stderr)
            print("or run with --dry-run to see what it would cost first.", file=sys.stderr)
            return 1
        try:
            raw_schema_composer = AnthropicSqlComposer(config)
            induced_layer_composer = AnthropicPlanComposer(config)
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 1

    catalog, queries = ingest(DOMAIN_ROOT / "ddl.sql", DOMAIN_ROOT / "queries")
    facts = extract_corpus(queries, catalog)

    with tempfile.TemporaryDirectory() as answer_dir_name:
        answer_dir = Path(answer_dir_name)
        with duckdb.connect(str(DATABASE), read_only=True) as connection:
            profiles = profile_database(connection, catalog)
            layer = induce(aggregate(facts), catalog, facts, min_support=1, profiles=profiles)
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
    if dry is not None:
        print("(dry run: canned responses, so the match rates above are meaningless)")
        models = [dry.requests[0].model if dry.requests else "claude-sonnet-4-5", *COMPARISON_MODELS]
        exact: dict[str, int] | None = None
        if args.exact_tokens:
            if config.api_key:
                exact = exact_input_tokens(dry.requests, config.api_key)
            else:
                print("--exact-tokens needs SEMANTIC_INDUCTION_API_KEY; falling back to approximate counts")
        print(render_dry_run(estimate_dry_run(dry.requests, models, exact), open_ledger(), exact=exact is not None))
        return 0
    print(f"raw schema match rate:    {report.match_rate(RAW_SCHEMA):.0%}")
    print(f"induced layer match rate: {report.match_rate(INDUCED_LAYER):.0%}")
    print(f"delta (induced - raw):    {report.delta():+.0%}")
    print()
    print(open_ledger().summary().render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
