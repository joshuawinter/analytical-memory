from pathlib import Path

import duckdb

from scripts.run_tier4 import SCENARIOS
from semantic_induction.conflicts import detect_conflicts
from semantic_induction.extract import extract_corpus
from semantic_induction.ingest import ingest
from semantic_induction.profile import profile_database
from semantic_induction.tier4 import Tier4Scenario, run_tier4

ROOT = Path(__file__).parents[1]


def _conflicts(with_profiles: bool):
    root = ROOT / "data/tpcds"
    catalog, queries = ingest(root / "ddl.sql", root / "tier4/queries")
    facts = extract_corpus(queries, catalog)
    profiles = None
    if with_profiles:
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
