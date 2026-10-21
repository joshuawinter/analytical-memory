"""Tier 3 preparation: dry runs count and price live calls without a key."""
from __future__ import annotations

import json

import pytest

from semantic_induction.models import Dimension, Measure, Metric, Predicate, SemanticLayer
from semantic_induction.spend import (
    DryRunClient,
    ResponseCache,
    SpendLedger,
    StaticModelConfig,
    approximate_tokens,
    estimate_dry_run,
    render_dry_run,
    request_text_chars,
)
from semantic_induction.tier3 import (
    AnthropicPlanComposer,
    AnthropicSqlComposer,
    BusinessQuestion,
    dry_run_responder,
    layer_vocabulary,
)


def _layer():
    return SemanticLayer(
        measures={("SUM", "orders.amount"): Measure("orders.amount", "SUM", 3)},
        dimensions={"orders.status": Dimension("orders.status", 3)},
        metrics=[
            Metric(("SUM", "orders.amount"), frozenset({"orders.status"}), (), (Predicate("orders.voided", "EQ", "false"),), 3, ("q1", "q2", "q3"))
        ],
    )


def test_dry_run_client_records_requests_and_writes_nothing(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    ledger = SpendLedger(tmp_path / "ledger.jsonl")
    client = DryRunClient(dry_run_responder, cache=cache)

    sql_composer = AnthropicSqlComposer(StaticModelConfig("claude-sonnet-4-5"), client=client)
    plan_composer = AnthropicPlanComposer(StaticModelConfig("claude-sonnet-4-5"), client=client)
    sql = sql_composer.compose(BusinessQuestion("q", "What is revenue?"), "orders(amount, status)")
    plan = plan_composer.compose(BusinessQuestion("q", "What is revenue?"), layer_vocabulary(_layer()))

    assert sql == "SELECT 1 AS metric_value"
    assert plan.measure == ("SUM", "orders.amount") and plan.dimensions == ("orders.status",)
    assert len(client.requests) == 2
    assert all(not item.cached for item in client.requests)
    assert all(item.max_tokens == 1024 for item in client.requests)
    assert not (tmp_path / "cache").exists()
    assert ledger.entries() == []


def test_dry_run_client_reports_requests_a_live_run_would_get_from_cache(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    request = {"model": "claude-sonnet-4-5", "max_tokens": 10, "messages": [{"role": "user", "content": json.dumps({"schema": "x"})}]}
    fake_response = type("R", (), {"model": "claude-sonnet-4-5", "stop_reason": "end_turn", "content": [type("B", (), {"type": "text", "text": "{}"})()], "usage": None})()
    from semantic_induction.spend import canonical_request_sha256

    cache.put(canonical_request_sha256(request), request, fake_response)

    client = DryRunClient(dry_run_responder, cache=cache)
    client.messages.create(**request)

    assert client.requests[0].cached is True


def test_request_text_chars_counts_system_and_message_text():
    request = {
        "system": "abcd",
        "messages": [{"role": "user", "content": "efgh"}, {"role": "user", "content": [{"type": "text", "text": "ij"}]}],
    }
    assert request_text_chars(request) == 10
    assert approximate_tokens(10) == 2  # 2.5 rounds to 2 (banker's rounding); labelled approximate


def test_estimate_dry_run_prices_live_calls_only_and_flags_unpriced_models():
    from semantic_induction.spend import RecordedRequest

    requests = [
        RecordedRequest("claude-sonnet-4-5", "a", 4000, 1024, False, {}),
        RecordedRequest("claude-sonnet-4-5", "b", 4000, 1024, False, {}),
        RecordedRequest("claude-sonnet-4-5", "c", 4000, 1024, True, {}),
    ]
    estimates = estimate_dry_run(requests, ["claude-sonnet-4-5", "mystery-model"], typical_output_tokens=200)

    sonnet, mystery = estimates
    assert sonnet.live_calls == 2 and sonnet.cached_calls == 1
    assert sonnet.input_tokens == 2000
    # 2000 in * $3 + 400 out * $15 = $0.006 + $0.006
    assert sonnet.typical_cost_usd == pytest.approx(0.012)
    # upper bound uses max_tokens: 2048 out * $15 = $0.03072
    assert sonnet.upper_cost_usd == pytest.approx(0.006 + 0.03072)
    assert mystery.typical_cost_usd is None

    text = render_dry_run(estimates, SpendLedger(__import__("pathlib").Path("nonexistent.jsonl")))
    assert "2 live call(s)" in text and "1 already cached" in text
    assert "no list price" in text and "nothing was sent" in text


def test_exact_tokens_override_the_approximation():
    from semantic_induction.spend import RecordedRequest

    requests = [RecordedRequest("claude-sonnet-4-5", "a", 4000, 100, False, {})]
    [estimate] = estimate_dry_run(requests, ["claude-sonnet-4-5"], exact_tokens={"a": 1234})
    assert estimate.input_tokens == 1234
