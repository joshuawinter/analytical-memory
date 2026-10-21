"""Generate the expanded Tier 4 corpus: labelled TPC-DS query groups.

Deterministic. Writes one directory per scenario under
data/tpcds/tier4/generated/ plus manifest.json, and is safe to rerun: the
output is a pure function of this file. Each scenario is an isolated corpus
(ingested on its own) so predicate recurrence in one scenario cannot leak
into another's classification.

Labels are SEMANTIC, not rule-derived. ``expect_conflict`` records what a
reviewer would say: does this group encode two different definitions of
the measure (what counts as a sale, what revenue means), or one definition
asked at different scopes, grains, or in different words? Several
scenarios are labelled against what Stage 4b's current heuristics will do,
on purpose, and carry ``known_gap: true`` with the reason. Tier 4 exists to
measure the classifier, not to pass.

Families:

  recurring_definitional    two queries add the same what-counts filter      -> conflict
  single_definitional       one query adds a what-counts filter              -> conflict (known miss: no recurrence, high-cardinality column)
  low_card_scope            one query adds a scope filter on a low-card col  -> no conflict (known over-flag: low-cardinality rule)
  recurring_scope           two queries add the same scope filter            -> no conflict (known over-flag: recurrence rule)
  high_card_scope           one query adds a scope filter on a high-card col -> no conflict (passes with profiles; over-flags without)
  grain_variation           one query adds a group-by column                 -> no conflict
  cosmetic                  aliases, ORDER BY, join wording                   -> no conflict
  different_measure         one query aggregates a different column          -> no conflict

Usage:
    .venv/Scripts/python.exe scripts/build_tier4_corpus.py
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tpcds" / "tier4" / "generated"


@dataclass(frozen=True)
class Base:
    base_id: str
    measure: str                      # e.g. "SUM(ss.ss_net_paid)"
    grain: tuple[str, ...]            # qualified columns, e.g. ("d.d_year",)
    joins: tuple[str, ...]            # FROM/JOIN lines, first is the fact table
    description: str

    def render(
        self,
        extra_filters: tuple[str, ...] = (),
        extra_grain: tuple[str, ...] = (),
        measure: str | None = None,
        style: int = 0,
    ) -> str:
        measure = measure or self.measure
        grain = (*self.grain, *extra_grain)
        alias = ("metric_value", "total", "amount")[style % 3]
        if style == 1:
            select_cols = [f"{col} AS {col.split('.')[-1]}" for col in grain]
        else:
            select_cols = list(grain)
        select = ", ".join([*select_cols, f"{measure} AS {alias}"] if style != 2 else [f"{measure} AS {alias}", *select_cols])
        joins = list(self.joins)
        if style == 2:
            joins = [joins[0], *[line.replace("JOIN ", "INNER JOIN ", 1) if line.startswith("JOIN ") else line for line in joins[1:]]]
        lines = [f"SELECT {select}", *joins]
        if extra_filters:
            lines.append("WHERE " + "\n  AND ".join(extra_filters))
        lines.append("GROUP BY " + ", ".join(grain))
        if style == 1:
            lines.append("ORDER BY " + ", ".join(grain))
        return "\n".join(lines) + "\n"


BASES = {
    "store_revenue_by_year": Base(
        "store_revenue_by_year", "SUM(ss.ss_net_paid)", ("d.d_year",),
        ("FROM store_sales ss", "JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk"),
        "store net paid by calendar year",
    ),
    "store_profit_by_year_category": Base(
        "store_profit_by_year_category", "SUM(ss.ss_net_profit)", ("d.d_year", "i.i_category"),
        ("FROM store_sales ss", "JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk", "JOIN item i ON ss.ss_item_sk = i.i_item_sk"),
        "store net profit by year and item category",
    ),
    "catalog_revenue_by_year": Base(
        "catalog_revenue_by_year", "SUM(cs.cs_net_paid)", ("d.d_year",),
        ("FROM catalog_sales cs", "JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk"),
        "catalog net paid by calendar year",
    ),
    "web_sales_by_year_month": Base(
        "web_sales_by_year_month", "SUM(ws.ws_ext_sales_price)", ("d.d_year", "d.d_moy"),
        ("FROM web_sales ws", "JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk"),
        "web extended sales price by year and month",
    ),
    "store_ticket_count_by_year": Base(
        "store_ticket_count_by_year", "COUNT(*)", ("d.d_year",),
        ("FROM store_sales ss", "JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk"),
        "store sales line count by calendar year",
    ),
    "avg_store_price_by_category": Base(
        "avg_store_price_by_category", "AVG(ss.ss_sales_price)", ("i.i_category",),
        ("FROM store_sales ss", "JOIN item i ON ss.ss_item_sk = i.i_item_sk"),
        "average store sales price by item category",
    ),
    "catalog_quantity_by_quarter": Base(
        "catalog_quantity_by_quarter", "SUM(cs.cs_quantity)", ("d.d_qoy",),
        ("FROM catalog_sales cs", "JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk"),
        "catalog quantity by quarter of year",
    ),
    "store_sales_by_customer_state": Base(
        "store_sales_by_customer_state", "SUM(ss.ss_ext_sales_price)", ("ca.ca_state",),
        ("FROM store_sales ss", "JOIN customer_address ca ON ss.ss_addr_sk = ca.ca_address_sk"),
        "store extended sales price by customer state",
    ),
}


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    family: str
    base: str
    expect_conflict: bool
    expect_conflict_without_profiles: bool
    known_gap: bool
    rationale: str
    queries: tuple[tuple[str, dict], ...]  # (query_id, render kwargs)
    # The classifier behaves differently without Stage 1b profiles (every
    # differing predicate is candidate-defining), so what counts as a
    # documented gap differs too.
    known_gap_without_profiles: bool = False


def _two_plain(base: str) -> tuple[tuple[str, dict], ...]:
    return ((f"{base}_a", {}), (f"{base}_b", {"style": 1}))


SCENARIOS: list[Scenario] = []


def _add(scenario: Scenario) -> None:
    SCENARIOS.append(scenario)


# -- recurring_definitional: two queries both exclude non-sales lines ----------
for base, filt, why in (
    ("store_revenue_by_year", "ss.ss_quantity > 0", "quantity-zero lines are voids or giveaways; excluding them changes what counts as a sale"),
    ("catalog_revenue_by_year", "cs.cs_quantity > 0", "same what-counts split on the catalog channel"),
    ("web_sales_by_year_month", "ws.ws_quantity > 0", "same what-counts split on the web channel"),
    ("store_profit_by_year_category", "ss.ss_coupon_amt = 0", "full-price-only profit is a different definition of profit, not a narrower question"),
    ("store_ticket_count_by_year", "ss.ss_quantity > 0", "counting only lines that sold vs every line is a definitional split for a count"),
    ("store_sales_by_customer_state", "ss.ss_quantity > 0", "what-counts split with a non-date dimension in the grain"),
):
    _add(Scenario(
        f"recurring_definitional__{base}", "recurring_definitional", base,
        expect_conflict=True, expect_conflict_without_profiles=True, known_gap=False,
        rationale=why,
        queries=(*_two_plain(base), (f"{base}_c", {"extra_filters": (filt,)}), (f"{base}_d", {"extra_filters": (filt,), "style": 2})),
    ))

# -- single_definitional: the filter appears once, on a high-cardinality column --
for base, filt in (
    ("store_revenue_by_year", "ss.ss_quantity > 0"),
    ("catalog_revenue_by_year", "cs.cs_quantity > 0"),
):
    _add(Scenario(
        f"single_definitional__{base}", "single_definitional", base,
        expect_conflict=True, expect_conflict_without_profiles=True, known_gap=True,
        rationale=(
            "A genuine what-counts filter observed once on a high-cardinality column. Stage 4b "
            "requires recurrence or low cardinality, so it treats this as narrowing: an expected "
            "miss, the precision-over-recall trade ARCHITECTURE.md accepts. Without profiles the "
            "conservative path flags it."
        ),
        queries=(*_two_plain(base), (f"{base}_c", {"extra_filters": (filt,)})),
        known_gap_without_profiles=False,  # the conservative no-profile path flags it
    ))

# -- low_card_scope: a scope filter on a low-cardinality column, observed once --
for base, filt, why in (
    ("store_revenue_by_year", "d.d_weekend = 'Y'", "weekend revenue is the same revenue asked about weekends; d_weekend has 2 values"),
    ("avg_store_price_by_category", "i.i_category = 'Books'", "restricting to one category is scope; i_category has 10 values"),
    ("catalog_quantity_by_quarter", "d.d_qoy = 4", "one quarter is scope; d_qoy has 4 values"),
):
    _add(Scenario(
        f"low_card_scope__{base}", "low_card_scope", base,
        expect_conflict=False, expect_conflict_without_profiles=False, known_gap=True,
        rationale=(
            f"{why}. Stage 4b's low-cardinality rule treats any single observation on a column "
            "with 12 or fewer distinct values as candidate-defining, so this is an expected "
            "over-flag. The rule was written for real status columns; TPC-DS has few of those."
        ),
        queries=(*_two_plain(base), (f"{base}_c", {"extra_filters": (filt,)})),
        known_gap_without_profiles=True,
    ))

# -- recurring_scope: the same scope filter in two queries -------------------
for base, filt, why in (
    ("store_revenue_by_year", "d.d_year = 2001", "two analysts asked about 2001; the measure's definition did not change"),
    ("catalog_revenue_by_year", "d.d_year = 2000", "same, catalog channel"),
):
    _add(Scenario(
        f"recurring_scope__{base}", "recurring_scope", base,
        expect_conflict=False, expect_conflict_without_profiles=False, known_gap=True,
        rationale=(
            f"{why}. Stage 4b's recurrence rule makes any predicate seen twice candidate-defining, "
            "so a popular scope becomes a rival definition: an expected over-flag and the clearest "
            "case for materiality ranking or rationale-learned rules over recurrence alone."
        ),
        queries=(*_two_plain(base), (f"{base}_c", {"extra_filters": (filt,)}), (f"{base}_d", {"extra_filters": (filt,), "style": 2})),
        known_gap_without_profiles=True,
    ))

# -- high_card_scope: a scope filter on a high-cardinality column, once -------
for base, filt, why in (
    ("store_revenue_by_year", "d.d_year = 2001", "one year out of 201"),
    ("store_profit_by_year_category", "i.i_manufact_id = 128", "one manufacturer out of 130"),
    ("store_sales_by_customer_state", "ca.ca_state = 'TN'", "one state out of 49"),
    ("web_sales_by_year_month", "ws.ws_ext_sales_price > 100", "a threshold on a continuous column, observed once"),
):
    _add(Scenario(
        f"high_card_scope__{base}", "high_card_scope", base,
        expect_conflict=False, expect_conflict_without_profiles=False, known_gap=False,
        rationale=(
            f"{why}; scope, not definition. With profiles Stage 4b sees high cardinality and no "
            "recurrence and correctly treats it as narrowing. Without profiles it has no evidence "
            "and flags it, which is the conservative path documented in conflicts.py."
        ),
        queries=(*_two_plain(base), (f"{base}_c", {"extra_filters": (filt,)})),
        known_gap_without_profiles=True,
    ))

# -- grain_variation ------------------------------------------------------------
for base, col in (
    ("store_revenue_by_year", "d.d_moy"),
    ("catalog_revenue_by_year", "d.d_qoy"),
    ("avg_store_price_by_category", "i.i_class"),
):
    _add(Scenario(
        f"grain_variation__{base}", "grain_variation", base,
        expect_conflict=False, expect_conflict_without_profiles=False, known_gap=False,
        rationale="A finer grain is another realization of the same measure, not a competing definition.",
        queries=(*_two_plain(base), (f"{base}_c", {"extra_grain": (col,)})),
    ))

# -- cosmetic -------------------------------------------------------------------
for base in ("store_revenue_by_year", "web_sales_by_year_month"):
    _add(Scenario(
        f"cosmetic__{base}", "cosmetic", base,
        expect_conflict=False, expect_conflict_without_profiles=False, known_gap=False,
        rationale="Aliases, ORDER BY, select order, and INNER JOIN wording change nothing about the definition.",
        queries=((f"{base}_a", {}), (f"{base}_b", {"style": 1}), (f"{base}_c", {"style": 2})),
    ))

# -- different_measure ----------------------------------------------------------
_add(Scenario(
    "different_measure__store_revenue_by_year", "different_measure", "store_revenue_by_year",
    expect_conflict=False, expect_conflict_without_profiles=False, known_gap=False,
    rationale="Net profit and net paid are different measures; nothing to arbitrate between them.",
    queries=(*_two_plain("store_revenue_by_year"), ("store_revenue_by_year_c", {"measure": "SUM(ss.ss_net_profit)"})),
))


def build(out: Path = OUT) -> dict:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    manifest = {"generator": "scripts/build_tier4_corpus.py", "scenarios": []}
    for scenario in SCENARIOS:
        directory = out / scenario.scenario_id
        directory.mkdir()
        base = BASES[scenario.base]
        query_ids = []
        for query_id, kwargs in scenario.queries:
            (directory / f"{query_id}.sql").write_text(base.render(**kwargs), encoding="utf-8")
            query_ids.append(query_id)
        manifest["scenarios"].append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "base": scenario.base,
                "base_description": base.description,
                "expect_conflict": scenario.expect_conflict,
                "expect_conflict_without_profiles": scenario.expect_conflict_without_profiles,
                "known_gap": scenario.known_gap,
                "known_gap_without_profiles": scenario.known_gap_without_profiles,
                "rationale": scenario.rationale,
                "query_ids": query_ids,
            }
        )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    manifest = build()
    families: dict[str, int] = {}
    for item in manifest["scenarios"]:
        families[item["family"]] = families.get(item["family"], 0) + 1
    print(f"wrote {len(manifest['scenarios'])} scenarios to {OUT}")
    for family, count in sorted(families.items()):
        print(f"  {family}: {count}")
    positives = sum(1 for s in manifest["scenarios"] if s["expect_conflict"])
    gaps = sum(1 for s in manifest["scenarios"] if s["known_gap"])
    print(f"positives: {positives}  negatives: {len(manifest['scenarios']) - positives}  known gaps: {gaps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
