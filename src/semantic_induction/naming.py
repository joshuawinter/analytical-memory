"""Stage 5 - provider-neutral naming of structural semantic objects."""
from __future__ import annotations

import os
import json
from dataclasses import asdict, is_dataclass
from collections.abc import Iterable
from typing import Protocol

from semantic_induction.memory import MetricDefinition
from semantic_induction.models import Entity, Measure, NamedDefinition, SemanticLayer


class NamingProvider(Protocol):
    source: str

    def name(self, object_id: str, structure: object) -> NamedDefinition: ...


class MockNamingProvider:
    """Deterministic local provider; no network or credentials required."""

    source = "mock"

    def name(self, object_id: str, structure: object) -> NamedDefinition:
        label = object_id.replace(".", " ").replace("_", " ").title()
        return NamedDefinition(object_id, label, f"Induced {label.lower()}.", self.source)


class AnthropicNamingProvider:
    """Claude-backed naming provider with an injectable client for testing."""

    source = "anthropic"

    def __init__(
        self,
        config: "EnvironmentNamingConfig | None" = None,
        client: object | None = None,
    ):
        self.config = config or EnvironmentNamingConfig()
        if client is None:
            # Every real call goes through the spend ledger and response cache
            # (RUNBOOK section 14). An injected client bypasses both on purpose
            # so tests and callers that bring their own client are unaffected.
            from semantic_induction.spend import metered_anthropic_client

            client = metered_anthropic_client(self.config, purpose="naming")
        self.client = client

    def name(self, object_id: str, structure: object) -> NamedDefinition:
        payload = asdict(structure) if is_dataclass(structure) else structure
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=400,
            system=(
                "Propose a business name and definition for this evidence-backed "
                "semantic-layer object, for a human reviewer to approve, reject, "
                "or correct. The name must be a short, human-readable business "
                "phrase (e.g. 'Total Revenue by Region') -- never a code "
                "identifier, and never snake_case or underscores.\n\n"
                "If the payload includes raw_sql, use it as your primary source "
                "for reading intent -- it is the actual query text behind this "
                "signature, richer than the extracted structural fields alone. "
                "If any invariant_filters compare a column to a literal string "
                "or enum-like value (a status, a category, a flag), gloss what "
                "that value plausibly means in one clause, grounded in the SQL "
                "and column name -- do not invent a meaning the SQL gives no "
                "basis for.\n\n"
                "If structured is true: state only what the supplied evidence "
                "shows (the measure, its grain, invariant filters, observed "
                "profile evidence) as a precise one-sentence definition. Do not "
                "invent business semantics beyond what is given, and do not "
                "change the supplied structure.\n\n"
                "If structured is false: this shape (a CTE-derived column, a "
                "CASE branch, a nested subquery) cannot be safely stated as a "
                "governed business definition -- flattening it into "
                "measure/grain/filter form would lose meaning the SQL actually "
                "encodes. Instead, read raw_sql and explain in one to three "
                "plain-language sentences what it actually computes. Begin the "
                "description with 'Unreviewed SQL interpretation:' and make "
                "clear this is a reading of the query, not an approved "
                "definition -- a human must verify it against the SQL before it "
                "governs anything.\n\n"
                "Return JSON only with exactly two string fields: name and "
                "description."
            ),
            messages=[
                {
                    "role": "user",
                    "content": json.dumps({"object_id": object_id, "structure": payload}, default=str),
                }
            ],
        )
        try:
            text = response.content[0].text.strip()
            result = _parse_json_object(text)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as error:
            raise ValueError("Anthropic naming response was not valid JSON content") from error
        name = result.get("name") if isinstance(result, dict) else None
        description = result.get("description") if isinstance(result, dict) else None
        if not isinstance(name, str) or not name.strip() or not isinstance(description, str) or not description.strip():
            raise ValueError("Anthropic naming response must contain non-empty name and description")
        return NamedDefinition(object_id, name.strip(), description.strip(), f"{self.source}:{self.config.model}")


def _parse_json_object(text: str) -> dict[str, object]:
    """Parse JSON returned as raw text or inside a Markdown code fence."""
    candidates = [text]
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        candidates.append("\n".join(lines[1:-1]).strip())
    for candidate in candidates:
        try:
            result = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            return result
    raise ValueError("response did not contain a JSON object")


class EnvironmentNamingConfig:
    """Credential placeholders for a future remote naming provider."""

    api_key_env: str = "SEMANTIC_INDUCTION_API_KEY"
    model_env: str = "SEMANTIC_INDUCTION_MODEL"

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env)

    @property
    def model(self) -> str | None:
        return os.getenv(self.model_env)


def _metric_definition_payload(
    definition: MetricDefinition, raw_sql: Iterable[str] = (), structured: bool = True
) -> dict[str, object]:
    aggregation, column = definition.measure
    return {
        "measure": column,
        "aggregation": aggregation,
        "grain": list(definition.grain),
        "join_path": [f"{edge.left} = {edge.right}" for edge in definition.join_path],
        "invariant_filters": [
            f"{predicate.column} {predicate.op} {predicate.value}" for predicate in definition.default_filters
        ],
        "evidence_count": len(definition.evidence_ids),
        "confidence": definition.confidence,
        "profile_notes": list(definition.profile_notes),
        "raw_sql": list(raw_sql),
        "structured": structured,
    }


def name_metric_definition(
    definition: MetricDefinition,
    provider: NamingProvider | None = None,
    raw_sql: Iterable[str] = (),
    structured: bool = True,
) -> NamedDefinition:
    """Stage 5: propose a business name and definition for one evidence-backed metric.

    Unlike ``name_layer`` (which names bare structural ``Entity``/``Measure``
    objects with no relational or data context), this sends the provider the
    full evidence a human reviewer already sees: join path, invariant
    filters, profile evidence such as observed values and ranges, and now
    the actual SQL text that produced the signature -- matching the payload
    shape documented in ARCHITECTURE.md's Stage 5 section, which the
    implementation previously fell short of (structural facts only, no raw
    SQL). The provider renames; it must not be trusted to add or remove
    structure, so the returned name/description are the only fields used.

    ``structured=False`` marks a candidate the flat measure/grain/filter
    contract cannot represent faithfully (a CTE-derived column, a CASE
    branch, a nested subquery -- see ``is_publishable_metric`` and
    ARCHITECTURE.md's publication boundary). Those candidates are excluded
    from ``review_items()``'s governed-definition path entirely today --
    they simply vanish. The provider is asked to narrate what the SQL
    computes in plain language instead of asserting a governed definition,
    so a reviewer sees *something* rather than nothing; that narration is
    presented as unstructured evidence, never as an approved definition.
    """
    provider = provider or MockNamingProvider()
    payload = _metric_definition_payload(definition, raw_sql, structured)
    return provider.name(definition.definition_id, payload)


def name_layer(layer: SemanticLayer, provider: NamingProvider | None = None) -> SemanticLayer:
    """Add names without changing any induced structural objects."""
    provider = provider or MockNamingProvider()
    for entity in layer.entities.values():
        layer.names[entity.table] = provider.name(entity.table, entity)
    for measure in layer.measures.values():
        object_id = f"{measure.aggregation.lower()}:{measure.column}"
        layer.names[object_id] = provider.name(object_id, measure)
    return layer