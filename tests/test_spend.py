"""Offline tests for the spend ledger, response cache, and metered client."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from semantic_induction.spend import (
    PRICES,
    CachedMessage,
    MeteredClient,
    ResponseCache,
    SpendCeilingExceeded,
    SpendEntry,
    SpendLedger,
    Usage,
    canonical_request_sha256,
    estimate_cost_usd,
    price_for,
)


class _FakeInner:
    """Stands in for the Anthropic client: counts calls, returns SDK-shaped messages."""

    def __init__(self, text: str = '{"name": "x", "description": "y"}', model: str = "claude-sonnet-4-5"):
        self.calls = 0
        self.text = text
        self.model = model
        self.messages = self

    def create(self, **request):
        self.calls += 1
        usage = type(
            "Usage",
            (),
            {
                "input_tokens": 1000,
                "output_tokens": 200,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )()
        block = type("Block", (), {"type": "text", "text": self.text})()
        return type(
            "Message",
            (),
            {"model": self.model, "stop_reason": "end_turn", "content": [block], "usage": usage},
        )()


def _client(tmp_path: Path, inner=None, **ledger_kwargs) -> tuple[MeteredClient, SpendLedger, list[str]]:
    warnings: list[str] = []
    ledger = SpendLedger(tmp_path / "ledger.jsonl", **ledger_kwargs)
    client = MeteredClient(
        inner or _FakeInner(),
        ledger,
        ResponseCache(tmp_path / "cache"),
        purpose="test",
        warn=warnings.append,
    )
    return client, ledger, warnings


def test_estimate_cost_matches_verified_list_prices():
    # Sonnet 4.5: $3 in / $15 out per MTok -> 1M of each is $18.
    assert estimate_cost_usd("claude-sonnet-4-5", Usage(1_000_000, 1_000_000)) == pytest.approx(18.0)
    # Cache tokens priced at their own rates: 1M writes at $3.75, 1M reads at $0.30.
    assert estimate_cost_usd(
        "claude-sonnet-4-5", Usage(0, 0, cache_creation_input_tokens=1_000_000, cache_read_input_tokens=1_000_000)
    ) == pytest.approx(4.05)
    # A realistic single naming call is fractions of a cent.
    assert estimate_cost_usd("claude-sonnet-4-5", Usage(1000, 200)) == pytest.approx(0.006)


def test_price_lookup_tolerates_snapshot_suffix_and_rejects_unknown():
    assert price_for("claude-sonnet-4-5-20250929") is PRICES["claude-sonnet-4-5"]
    assert price_for("claude-haiku-4-5-20251001") is PRICES["claude-haiku-4-5"]
    assert price_for("gpt-4o") is None
    assert estimate_cost_usd("not-a-model", Usage(10, 10)) is None


def test_identical_requests_hit_the_cache_and_cost_nothing(tmp_path):
    inner = _FakeInner()
    client, ledger, _ = _client(tmp_path, inner)
    request = {"model": "claude-sonnet-4-5", "max_tokens": 400, "system": "s", "messages": [{"role": "user", "content": "q"}]}

    first = client.messages.create(**request)
    second = client.messages.create(**request)

    assert inner.calls == 1
    assert isinstance(second, CachedMessage)
    assert second.content[0].text == first.content[0].text
    entries = ledger.entries()
    assert [entry.cache_hit for entry in entries] == [False, True]
    assert entries[1].cost_usd == 0.0
    assert ledger.total_usd() == pytest.approx(entries[0].cost_usd)
    summary = ledger.summary()
    assert summary.live_calls == 1 and summary.cache_hits == 1
    assert summary.by_purpose == {"test": pytest.approx(0.006)}


def test_cache_key_is_order_insensitive_but_content_sensitive():
    a = {"model": "m", "messages": [{"role": "user", "content": "q"}], "max_tokens": 1}
    b = {"max_tokens": 1, "messages": [{"role": "user", "content": "q"}], "model": "m"}
    c = {**a, "max_tokens": 2}
    assert canonical_request_sha256(a) == canonical_request_sha256(b)
    assert canonical_request_sha256(a) != canonical_request_sha256(c)


def test_cache_file_records_request_and_response(tmp_path):
    client, _, _ = _client(tmp_path)
    request = {"model": "claude-sonnet-4-5", "max_tokens": 10, "messages": [{"role": "user", "content": "q"}]}
    client.messages.create(**request)

    files = list((tmp_path / "cache").glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["request"]["model"] == "claude-sonnet-4-5"
    assert payload["response"]["usage"]["input_tokens"] == 1000
    assert payload["response"]["content"][0]["text"].startswith("{")


def test_hard_stop_refuses_before_calling_out(tmp_path):
    inner = _FakeInner()
    client, ledger, _ = _client(tmp_path, inner, ceiling_usd=25.0, hard_stop_usd=100.0)
    ledger.append(SpendEntry("2026-10-21T00:00:00+00:00", "claude-opus-5", "prior", "abc", False, Usage(1, 1), 100.0))

    with pytest.raises(SpendCeilingExceeded):
        client.messages.create(model="claude-sonnet-4-5", max_tokens=1, messages=[{"role": "user", "content": "q"}])
    assert inner.calls == 0


def test_cache_hit_is_served_even_past_the_hard_stop(tmp_path):
    inner = _FakeInner()
    client, ledger, _ = _client(tmp_path, inner, hard_stop_usd=100.0)
    request = {"model": "claude-sonnet-4-5", "max_tokens": 1, "messages": [{"role": "user", "content": "q"}]}
    client.messages.create(**request)
    ledger.append(SpendEntry("2026-10-21T00:00:00+00:00", "claude-opus-5", "prior", "abc", False, Usage(1, 1), 100.0))

    replayed = client.messages.create(**request)

    assert isinstance(replayed, CachedMessage)
    assert inner.calls == 1


def test_ceiling_warns_once_and_keeps_going(tmp_path):
    inner = _FakeInner()
    client, ledger, warnings = _client(tmp_path, inner, ceiling_usd=0.001, hard_stop_usd=100.0)
    ledger.append(SpendEntry("2026-10-21T00:00:00+00:00", "claude-opus-5", "prior", "abc", False, Usage(1, 1), 0.5))

    client.messages.create(model="claude-sonnet-4-5", max_tokens=1, messages=[{"role": "user", "content": "q1"}])
    client.messages.create(model="claude-sonnet-4-5", max_tokens=1, messages=[{"role": "user", "content": "q2"}])

    assert inner.calls == 2
    assert len([message for message in warnings if "ceiling" in message]) == 1


def test_unpriced_model_is_recorded_with_null_cost_and_one_warning(tmp_path):
    inner = _FakeInner(model="experimental-model")
    client, ledger, warnings = _client(tmp_path, inner)

    client.messages.create(model="experimental-model", max_tokens=1, messages=[{"role": "user", "content": "q1"}])
    client.messages.create(model="experimental-model", max_tokens=1, messages=[{"role": "user", "content": "q2"}])

    entries = ledger.entries()
    assert [entry.cost_usd for entry in entries] == [None, None]
    assert entries[0].usage.input_tokens == 1000
    assert ledger.summary().unpriced_calls == 2
    assert len([message for message in warnings if "no list price" in message]) == 1


def test_summary_render_names_totals_and_limits(tmp_path):
    client, ledger, _ = _client(tmp_path, ceiling_usd=25.0, hard_stop_usd=100.0)
    client.messages.create(model="claude-sonnet-4-5", max_tokens=1, messages=[{"role": "user", "content": "q"}])

    text = ledger.summary().render()

    assert "estimated spend: $0.0060" in text
    assert "ceiling $25.00" in text and "hard stop $100.00" in text
    assert "claude-sonnet-4-5" in text
    assert "Anthropic Console" in text


def test_empty_ledger_summary_is_zero(tmp_path):
    ledger = SpendLedger(tmp_path / "missing.jsonl")
    summary = ledger.summary()
    assert summary.total_usd == 0.0 and summary.live_calls == 0 and summary.cache_hits == 0
    assert "estimated spend: $0.0000" in summary.render()
