from pathlib import Path

import duckdb
import pytest

from scripts.run_tier4 import SCENARIOS
from semantic_induction.conflicts import detect_conflicts
from semantic_induction.extract import extract_corpus
from semantic_induction.ingest import ingest
from semantic_induction.profile import profile_database
from semantic_induction.tier4 import Tier4Scenario, run_generated_tier4, run_tier4

ROOT = Path(__file__).parents[1]


def _conflicts(with_profiles: bool):
    root = ROOT / "data/tpcds"
    catalog, queries = ingest(root / "ddl.sql", root / "tier4/queries")
    facts = extract_corpus(queries, catalog)
    profiles = None
    if with_profiles:
        if not (root / "tpcds.duckdb").exists():
            pytest.skip("tpcds.duckdb not generated; see RUNBOOK section 9")
        with duckdb.connect(str(root / "tpcds.duckdb"), read_only=True) as connection:
            profiles = profile_database(connection, catalog, sample_size=5, top_values=5)
    return detect_conflicts(None, facts, min_support=1, profiles=profiles)


def test_tier4_fixture_scenarios_are_classified_correctly():
    conflicts = _conflicts(with_profiles=True)

    report = run_tier4(conflicts, SCENARIOS)

    incorrect = [result for result in report.results if not result.correct]
    assert not incorrect, [(r.scenario_id, r.expected, r.found, r.matched_kind) for r in incorrect]
    assert report.precision() == 1.0
    assert report.recall() == 1.0
    assert report.noise_rate() == 0.0


def test_run_tier4_reports_a_false_negative_it_does_not_hide():
    # A genuine conflict scenario that Tier 4 itself documents as a known
    # gap (a one-off filter on a high-cardinality column) must show up as a
    # false negative in the report, not be silently absorbed into a "pass".
    # This guards against the harness becoming a rubber stamp.
    conflicts = _conflicts(with_profiles=True)
    gap_scenario = Tier4Scenario(
        scenario_id="known_gap_check",
        query_ids=frozenset({"a1_gross_revenue", "c1_full_price_only_revenue"}),
        expect_conflict=True,  # deliberately mislabeled as "should conflict" to prove the report says no
        description="sanity check that run_tier4 reports failure rather than always agreeing",
    )

    report = run_tier4(conflicts, [gap_scenario])

    assert report.results[0].found is False
    assert report.results[0].correct is False
    assert report.false_negatives == 1


# -- generated set: the classifier measured against semantic labels ----------

GENERATED = ROOT / "data/tpcds/tier4/generated"
DDL = ROOT / "data/tpcds/ddl.sql"


def _profiles():
    database = ROOT / "data/tpcds/tpcds.duckdb"
    if not database.exists():
        pytest.skip("tpcds.duckdb not generated; see RUNBOOK section 9")
    catalog, _ = ingest(DDL, ROOT / "data/tpcds/tier4/queries")
    with duckdb.connect(str(database), read_only=True) as connection:
        return profile_database(connection, catalog, sample_size=5, top_values=5)


def test_generated_corpus_is_reproducible_from_the_generator(tmp_path):
    from scripts.build_tier4_corpus import build

    build(tmp_path / "generated")

    committed = sorted(path.relative_to(GENERATED) for path in GENERATED.rglob("*") if path.is_file())
    rebuilt = sorted(path.relative_to(tmp_path / "generated") for path in (tmp_path / "generated").rglob("*") if path.is_file())
    assert committed == rebuilt
    for relative in committed:
        assert (GENERATED / relative).read_text(encoding="utf-8") == (tmp_path / "generated" / relative).read_text(encoding="utf-8"), relative


def test_generated_tier4_with_profiles_matches_the_documented_baseline():
    # Labels are semantic (definition vs scope). The classifier's current
    # heuristics over-flag scope filters that recur or sit on low-cardinality
    # columns and miss a definitional filter seen once on a high-cardinality
    # column. Those are documented as known gaps in the manifest; this pins
    # the confusion matrix so a change in behaviour, better or worse, is
    # visible. See ARCHITECTURE.md's Tier 4 section for the numbers' meaning.
    report = run_generated_tier4(GENERATED, DDL, _profiles())

    assert (report.true_positives, report.false_positives, report.false_negatives, report.true_negatives) == (6, 5, 2, 10)
    assert report.precision() == pytest.approx(6 / 11)
    assert report.recall() == pytest.approx(6 / 8)
    assert report.unexpected_failures == ()
    assert report.surprising_passes == ()
    failed = {result.scenario_id for result in report.results if not result.correct}
    assert failed == {
        "single_definitional__store_revenue_by_year",
        "single_definitional__catalog_revenue_by_year",
        "low_card_scope__store_revenue_by_year",
        "low_card_scope__avg_store_price_by_category",
        "low_card_scope__catalog_quantity_by_quarter",
        "recurring_scope__store_revenue_by_year",
        "recurring_scope__catalog_revenue_by_year",
    }


def test_generated_tier4_without_profiles_flags_every_difference():
    # No Stage 1b evidence means every differing predicate is treated as
    # candidate-defining: recall goes to 100% and precision falls further.
    # The misses become hits (single_definitional) and the high-cardinality
    # scopes become over-flags; both switches are documented in the manifest.
    report = run_generated_tier4(GENERATED, DDL, None)

    assert (report.true_positives, report.false_positives, report.false_negatives, report.true_negatives) == (8, 9, 0, 6)
    assert report.recall() == 1.0
    assert report.unexpected_failures == ()
    assert report.surprising_passes == ()
