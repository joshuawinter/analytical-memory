"""Spend ledger and response cache for the project's live model calls.

RUNBOOK section 14 sets a target of $5-$15 for the first live experiment, a
preferred ceiling of $25, and a hard stop at $100, and says to cache every
external prompt and response. Until this module existed none of that was
enforced or even measured: ``AnthropicNamingProvider`` and the Tier 3
composers called ``client.messages.create`` directly and nothing recorded
``response.usage``.

Three pieces, all offline and dependency-free:

- ``SpendLedger`` -- an append-only JSONL file, one line per call, carrying
  the model, purpose, token usage, the estimated cost in USD, and whether the
  call was served from cache. Totals are derived by reading it back, never
  stored, so the file is the record.
- ``ResponseCache`` -- content-addressed by the SHA-256 of the canonical
  request (model, system, messages, max_tokens, everything). An identical
  request is answered from disk at zero cost. This is what makes a Tier 3 or
  Stage 5 run reproducible for anyone who clones the repo without a key.
- ``MeteredClient`` -- wraps any object exposing ``messages.create(**request)``
  and threads every call through the cache and the ledger, warning once at
  the ceiling and refusing to call out at the hard stop.

Prices are an estimate, not a bill. They are first-party Claude API list
prices verified against the pricing page on ``PRICES_VERIFIED``; the
Anthropic Console is the source of truth for what was actually charged.
A model missing from ``PRICES`` is still recorded, with ``cost_usd`` null,
and the summary counts it so the gap is visible rather than silent.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PRICES_VERIFIED = "2026-10-21"
PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"

SPEND_DIR_ENV = "SEMANTIC_INDUCTION_SPEND_DIR"
CEILING_ENV = "SEMANTIC_INDUCTION_SPEND_CEILING_USD"
HARD_STOP_ENV = "SEMANTIC_INDUCTION_SPEND_HARD_STOP_USD"
DEFAULT_CEILING_USD = 25.0
DEFAULT_HARD_STOP_USD = 100.0

LEDGER_FILENAME = "ledger.jsonl"
CACHE_DIRNAME = "cache"


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens. ``cache_write`` is the 5-minute cache write rate."""

    input_per_mtok: float
    output_per_mtok: float
    cache_write_per_mtok: float
    cache_read_per_mtok: float


# First-party Claude API list prices, USD per MTok, verified PRICES_VERIFIED
# against PRICES_SOURCE. Batch and fast-mode rates are not modelled; nothing
# in this project uses them.
PRICES: dict[str, ModelPrice] = {
    "claude-fable-5-1": ModelPrice(10.0, 50.0, 12.50, 0.25),
    "claude-fable-5": ModelPrice(10.0, 50.0, 12.50, 1.00),
    "claude-opus-5-5": ModelPrice(4.0, 20.0, 5.00, 0.20),
    "claude-opus-5": ModelPrice(5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-8": ModelPrice(5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-7": ModelPrice(5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-6": ModelPrice(5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-5": ModelPrice(5.0, 25.0, 6.25, 0.50),
    "claude-sonnet-5-5": ModelPrice(2.0, 10.0, 2.50, 0.10),
    "claude-sonnet-5": ModelPrice(2.0, 10.0, 2.50, 0.20),
    "claude-sonnet-4-6": ModelPrice(3.0, 15.0, 3.75, 0.30),
    "claude-sonnet-4-5": ModelPrice(3.0, 15.0, 3.75, 0.30),
    "claude-haiku-4-5": ModelPrice(1.0, 5.0, 1.25, 0.10),
}


def price_for(model: str) -> ModelPrice | None:
    """Look up a price by model id, tolerating a trailing ``-YYYYMMDD`` snapshot suffix."""
    if model in PRICES:
        return PRICES[model]
    head, _, tail = model.rpartition("-")
    if head and len(tail) == 8 and tail.isdigit():
        return PRICES.get(head)
    return None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @classmethod
    def from_response(cls, response: Any) -> "Usage":
        """Read ``response.usage`` from an SDK message, a cached message, or a dict."""
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, Mapping):
            usage = response.get("usage")
        if usage is None:
            return cls()

        def _int(name: str) -> int:
            value = usage.get(name) if isinstance(usage, Mapping) else getattr(usage, name, None)
            return int(value or 0)

        return cls(
            input_tokens=_int("input_tokens"),
            output_tokens=_int("output_tokens"),
            cache_creation_input_tokens=_int("cache_creation_input_tokens"),
            cache_read_input_tokens=_int("cache_read_input_tokens"),
        )

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


def estimate_cost_usd(model: str, usage: Usage) -> float | None:
    """Estimated first-party list cost of one call, or None if the model is unpriced."""
    price = price_for(model)
    if price is None:
        return None
    return (
        usage.input_tokens * price.input_per_mtok
        + usage.output_tokens * price.output_per_mtok
        + usage.cache_creation_input_tokens * price.cache_write_per_mtok
        + usage.cache_read_input_tokens * price.cache_read_per_mtok
    ) / 1_000_000


class SpendCeilingExceeded(RuntimeError):
    """Raised before a live call when the ledger total has reached the hard stop."""


@dataclass(frozen=True)
class SpendEntry:
    recorded_at: str
    model: str
    purpose: str
    request_sha256: str
    cache_hit: bool
    usage: Usage
    cost_usd: float | None

    def to_json(self) -> str:
        payload = asdict(self)
        return json.dumps(payload, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "SpendEntry":
        payload = json.loads(line)
        payload["usage"] = Usage(**payload.get("usage", {}))
        return cls(**payload)


@dataclass
class SpendSummary:
    total_usd: float
    live_calls: int
    cache_hits: int
    unpriced_calls: int
    ceiling_usd: float
    hard_stop_usd: float
    by_model: dict[str, float] = field(default_factory=dict)
    by_purpose: dict[str, float] = field(default_factory=dict)
    first_recorded_at: str | None = None
    last_recorded_at: str | None = None

    def render(self) -> str:
        lines = [
            f"estimated spend: ${self.total_usd:.4f} "
            f"(ceiling ${self.ceiling_usd:.2f}, hard stop ${self.hard_stop_usd:.2f})",
            f"live calls: {self.live_calls}   cache hits: {self.cache_hits}   "
            f"unpriced calls: {self.unpriced_calls}",
        ]
        if self.by_model:
            lines.append("by model:")
            lines.extend(f"  {model}: ${cost:.4f}" for model, cost in sorted(self.by_model.items()))
        if self.by_purpose:
            lines.append("by purpose:")
            lines.extend(f"  {purpose}: ${cost:.4f}" for purpose, cost in sorted(self.by_purpose.items()))
        if self.first_recorded_at:
            lines.append(f"span: {self.first_recorded_at} .. {self.last_recorded_at}")
        lines.append(f"prices verified {PRICES_VERIFIED}; the Anthropic Console is the bill")
        return "\n".join(lines)


class SpendLedger:
    """Append-only JSONL ledger. Totals are always recomputed from the file."""

    def __init__(
        self,
        path: Path,
        ceiling_usd: float = DEFAULT_CEILING_USD,
        hard_stop_usd: float = DEFAULT_HARD_STOP_USD,
    ):
        self.path = path
        self.ceiling_usd = ceiling_usd
        self.hard_stop_usd = hard_stop_usd

    def entries(self) -> list[SpendEntry]:
        if not self.path.exists():
            return []
        return [
            SpendEntry.from_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def append(self, entry: SpendEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry.to_json() + "\n")

    def total_usd(self) -> float:
        return sum(entry.cost_usd for entry in self.entries() if entry.cost_usd is not None)

    def summary(self) -> SpendSummary:
        entries = self.entries()
        summary = SpendSummary(
            total_usd=0.0,
            live_calls=0,
            cache_hits=0,
            unpriced_calls=0,
            ceiling_usd=self.ceiling_usd,
            hard_stop_usd=self.hard_stop_usd,
        )
        for entry in entries:
            if entry.cache_hit:
                summary.cache_hits += 1
                continue
            summary.live_calls += 1
            if entry.cost_usd is None:
                summary.unpriced_calls += 1
                continue
            summary.total_usd += entry.cost_usd
            summary.by_model[entry.model] = summary.by_model.get(entry.model, 0.0) + entry.cost_usd
            summary.by_purpose[entry.purpose] = summary.by_purpose.get(entry.purpose, 0.0) + entry.cost_usd
        if entries:
            summary.first_recorded_at = entries[0].recorded_at
            summary.last_recorded_at = entries[-1].recorded_at
        return summary


@dataclass(frozen=True)
class CachedTextBlock:
    text: str
    type: str = "text"


@dataclass(frozen=True)
class CachedMessage:
    """The subset of an SDK ``Message`` this project reads, replayed from disk."""

    model: str
    stop_reason: str | None
    content: tuple[CachedTextBlock, ...]
    usage: Usage
    from_cache: bool = True


def canonical_request_sha256(request: Mapping[str, Any]) -> str:
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ResponseCache:
    """One JSON file per distinct request, named by the request's SHA-256."""

    def __init__(self, directory: Path):
        self.directory = directory

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> CachedMessage | None:
        path = self._path(key)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        response = payload["response"]
        return CachedMessage(
            model=response.get("model", ""),
            stop_reason=response.get("stop_reason"),
            content=tuple(
                CachedTextBlock(text=block.get("text", ""), type=block.get("type", "text"))
                for block in response.get("content", [])
            ),
            usage=Usage(**response.get("usage", {})),
        )

    def put(self, key: str, request: Mapping[str, Any], response: Any) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        blocks = []
        for block in getattr(response, "content", ()) or ():
            blocks.append(
                {
                    "type": getattr(block, "type", "text"),
                    "text": getattr(block, "text", ""),
                }
            )
        payload = {
            "recorded_at": _now(),
            "request_sha256": key,
            "request": json.loads(json.dumps(request, default=str)),
            "response": {
                "model": getattr(response, "model", request.get("model", "")),
                "stop_reason": getattr(response, "stop_reason", None),
                "content": blocks,
                "usage": asdict(Usage.from_response(response)),
            },
        }
        self._path(key).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _warn_to_stderr(message: str) -> None:
    print(f"[spend] {message}", file=sys.stderr)


class _MeteredMessages:
    def __init__(self, owner: "MeteredClient"):
        self._owner = owner

    def create(self, **request: Any) -> Any:
        return self._owner._create(request)


class MeteredClient:
    """Wrap a client whose ``messages.create(**request)`` returns an SDK-shaped message.

    Every call is answered from ``cache`` when the identical request has been
    seen, otherwise forwarded to ``inner`` after checking the ledger against
    the ceiling (warn once) and the hard stop (refuse). Both outcomes are
    appended to ``ledger``.
    """

    def __init__(
        self,
        inner: Any,
        ledger: SpendLedger,
        cache: ResponseCache | None,
        purpose: str = "unspecified",
        warn: Callable[[str], None] = _warn_to_stderr,
    ):
        self.inner = inner
        self.ledger = ledger
        self.cache = cache
        self.purpose = purpose
        self.warn = warn
        self.messages = _MeteredMessages(self)
        self._warned_ceiling = False
        self._warned_unpriced: set[str] = set()

    def _create(self, request: Mapping[str, Any]) -> Any:
        model = str(request.get("model", ""))
        key = canonical_request_sha256(request)

        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                self.ledger.append(
                    SpendEntry(_now(), model, self.purpose, key, True, cached.usage, 0.0)
                )
                return cached

        spent = self.ledger.total_usd()
        if spent >= self.ledger.hard_stop_usd:
            raise SpendCeilingExceeded(
                f"estimated spend ${spent:.2f} has reached the hard stop "
                f"${self.ledger.hard_stop_usd:.2f}; review {self.ledger.path} and raise "
                f"{HARD_STOP_ENV} deliberately before making more live calls"
            )
        if spent >= self.ledger.ceiling_usd and not self._warned_ceiling:
            self._warned_ceiling = True
            self.warn(
                f"estimated spend ${spent:.2f} is past the preferred ceiling "
                f"${self.ledger.ceiling_usd:.2f}; calls continue until the hard stop "
                f"${self.ledger.hard_stop_usd:.2f}"
            )

        response = self.inner.messages.create(**request)
        usage = Usage.from_response(response)
        cost = estimate_cost_usd(model, usage)
        if cost is None and model not in self._warned_unpriced:
            self._warned_unpriced.add(model)
            self.warn(
                f"no list price for model {model!r}; tokens are recorded but cost is null. "
                f"Add it to semantic_induction.spend.PRICES"
            )
        if self.cache is not None:
            self.cache.put(key, request, response)
        self.ledger.append(SpendEntry(_now(), model, self.purpose, key, False, usage, cost))
        return response


def default_spend_dir() -> Path:
    override = os.getenv(SPEND_DIR_ENV)
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "data" / "spend"


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a number, got {raw!r}") from error


def open_ledger(directory: Path | None = None) -> SpendLedger:
    directory = directory or default_spend_dir()
    return SpendLedger(
        directory / LEDGER_FILENAME,
        ceiling_usd=_float_env(CEILING_ENV, DEFAULT_CEILING_USD),
        hard_stop_usd=_float_env(HARD_STOP_ENV, DEFAULT_HARD_STOP_USD),
    )


def open_cache(directory: Path | None = None) -> ResponseCache:
    directory = directory or default_spend_dir()
    return ResponseCache(directory / CACHE_DIRNAME)


def metered_anthropic_client(
    config: Any,
    purpose: str,
    *,
    component: str = "Anthropic provider",
    directory: Path | None = None,
) -> MeteredClient:
    """Build the real Anthropic client and wrap it. The single live-call entry point.

    ``config`` is an ``EnvironmentNamingConfig`` (api_key / model / *_env
    attributes). Error messages match what the providers raised before this
    module existed so callers and scripts keep their behaviour.
    """
    if not config.api_key:
        raise RuntimeError(f"missing API key environment variable: {config.api_key_env}")
    if not config.model:
        raise RuntimeError(f"missing model environment variable: {config.model_env}")
    try:
        from anthropic import Anthropic
    except ImportError as error:
        raise RuntimeError(
            f"the 'anthropic' optional dependency is required by {component}; "
            "install it with: pip install -e \".[anthropic]\""
        ) from error
    inner = Anthropic(api_key=config.api_key)
    return MeteredClient(inner, open_ledger(directory), open_cache(directory), purpose=purpose)


# ---------------------------------------------------------------------------
# Dry runs: count and price the calls a live run would make, with no key.
# ---------------------------------------------------------------------------

TYPICAL_OUTPUT_TOKENS = 200
COMPARISON_MODELS = ("claude-sonnet-4-5", "claude-sonnet-5", "claude-opus-5", "claude-fable-5-1")


class StaticModelConfig:
    """A config with a fixed model and optional key, for dry runs and tests.

    Mirrors ``EnvironmentNamingConfig``'s attributes so the Tier 3 composers
    and the naming provider accept it unchanged.
    """

    api_key_env = "SEMANTIC_INDUCTION_API_KEY"
    model_env = "SEMANTIC_INDUCTION_MODEL"

    def __init__(self, model: str, api_key: str | None = None):
        self._model = model
        self._api_key = api_key

    @property
    def api_key(self) -> str | None:
        return self._api_key

    @property
    def model(self) -> str | None:
        return self._model


def request_text_chars(request: Mapping[str, Any]) -> int:
    """Characters of prompt text in a request: system plus every message's content."""

    def _chars(content: Any) -> int:
        if content is None:
            return 0
        if isinstance(content, str):
            return len(content)
        if isinstance(content, Mapping):
            return _chars(content.get("text")) + _chars(content.get("content"))
        if isinstance(content, (list, tuple)):
            return sum(_chars(item) for item in content)
        return len(str(content))

    total = _chars(request.get("system"))
    for message in request.get("messages", ()) or ():
        total += _chars(message.get("content") if isinstance(message, Mapping) else message)
    return total


def approximate_tokens(chars: int) -> int:
    """Rough token estimate from character count. Labelled approximate wherever shown."""
    return max(1, round(chars / 4))


@dataclass(frozen=True)
class RecordedRequest:
    model: str
    request_sha256: str
    input_chars: int
    max_tokens: int
    cached: bool
    request: Mapping[str, Any]


class DryRunClient:
    """Record what a live run would send and answer from a canned responder.

    Touches neither the ledger nor the cache. If a ``cache`` is supplied it is
    only consulted to report which requests a live run would get for free.
    ``responder`` receives the request mapping and returns the text block a
    real model would have produced.
    """

    def __init__(self, responder: Callable[[Mapping[str, Any]], str], cache: ResponseCache | None = None):
        self.responder = responder
        self.cache = cache
        self.requests: list[RecordedRequest] = []
        self.messages = self

    def create(self, **request: Any) -> CachedMessage:
        model = str(request.get("model", ""))
        key = canonical_request_sha256(request)
        cached = self.cache is not None and self.cache.get(key) is not None
        self.requests.append(
            RecordedRequest(model, key, request_text_chars(request), int(request.get("max_tokens", 0) or 0), cached, dict(request))
        )
        return CachedMessage(
            model=model,
            stop_reason="end_turn",
            content=(CachedTextBlock(self.responder(request)),),
            usage=Usage(),
            from_cache=False,
        )


def exact_input_tokens(requests: Iterable[RecordedRequest], api_key: str) -> dict[str, int]:
    """Exact input token counts from the API's free count_tokens endpoint.

    Needs a key but costs nothing. Returns ``{request_sha256: input_tokens}``.
    """
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    counts: dict[str, int] = {}
    for recorded in requests:
        if recorded.request_sha256 in counts:
            continue
        kwargs: dict[str, Any] = {"model": recorded.model, "messages": recorded.request["messages"]}
        if recorded.request.get("system") is not None:
            kwargs["system"] = recorded.request["system"]
        counts[recorded.request_sha256] = int(client.messages.count_tokens(**kwargs).input_tokens)
    return counts


@dataclass(frozen=True)
class DryRunEstimate:
    model: str
    live_calls: int
    cached_calls: int
    input_tokens: int
    typical_output_tokens: int
    max_output_tokens: int
    typical_cost_usd: float | None
    upper_cost_usd: float | None


def estimate_dry_run(
    requests: Iterable[RecordedRequest],
    models: Iterable[str],
    exact_tokens: Mapping[str, int] | None = None,
    typical_output_tokens: int = TYPICAL_OUTPUT_TOKENS,
) -> list[DryRunEstimate]:
    recorded = list(requests)
    live = [item for item in recorded if not item.cached]
    cached = len(recorded) - len(live)
    if exact_tokens:
        input_tokens = sum(exact_tokens.get(item.request_sha256, approximate_tokens(item.input_chars)) for item in live)
    else:
        input_tokens = sum(approximate_tokens(item.input_chars) for item in live)
    typical_out = len(live) * typical_output_tokens
    max_out = sum(item.max_tokens for item in live)
    estimates = []
    for model in dict.fromkeys(models):
        price = price_for(model)
        if price is None:
            estimates.append(DryRunEstimate(model, len(live), cached, input_tokens, typical_out, max_out, None, None))
            continue
        base = input_tokens * price.input_per_mtok
        estimates.append(
            DryRunEstimate(
                model, len(live), cached, input_tokens, typical_out, max_out,
                (base + typical_out * price.output_per_mtok) / 1_000_000,
                (base + max_out * price.output_per_mtok) / 1_000_000,
            )
        )
    return estimates


def render_dry_run(
    estimates: Iterable[DryRunEstimate],
    ledger: SpendLedger | None = None,
    exact: bool = False,
) -> str:
    estimates = list(estimates)
    if not estimates:
        return "dry run: no requests recorded"
    first = estimates[0]
    token_note = "exact (count_tokens)" if exact else "approximate (chars / 4)"
    lines = [
        f"dry run: {first.live_calls} live call(s) would be made; {first.cached_calls} already cached (free)",
        f"input tokens: {first.input_tokens:,} {token_note}; output: ~{first.typical_output_tokens:,} typical, "
        f"{first.max_output_tokens:,} at max_tokens",
        "estimated cost by model (typical / upper bound at max_tokens):",
    ]
    for item in estimates:
        if item.typical_cost_usd is None:
            lines.append(f"  {item.model:20} no list price in spend.PRICES")
        else:
            lines.append(f"  {item.model:20} ${item.typical_cost_usd:.4f} / ${item.upper_cost_usd:.4f}")
    if ledger is not None:
        spent = ledger.total_usd()
        lines.append(
            f"ledger so far: ${spent:.4f}; ceiling ${ledger.ceiling_usd:.2f}; hard stop ${ledger.hard_stop_usd:.2f}; "
            f"headroom to hard stop ${max(0.0, ledger.hard_stop_usd - spent):.2f}"
        )
    lines.append(f"prices verified {PRICES_VERIFIED}; nothing was sent and nothing was recorded")
    return "\n".join(lines)
