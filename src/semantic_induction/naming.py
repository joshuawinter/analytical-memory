"""Stage 5 - provider-neutral naming of structural semantic objects."""
from __future__ import annotations

import os
import json
from dataclasses import asdict, is_dataclass
from collections.abc import Iterable
from typing import Protocol

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
            if not self.config.api_key:
                raise RuntimeError(
                    f"missing API key environment variable: {self.config.api_key_env}"
                )
            if not self.config.model:
                raise RuntimeError(
                    f"missing model environment variable: {self.config.model_env}"
                )
            try:
                from anthropic import Anthropic
            except ImportError as error:
                raise RuntimeError(
                    "Anthropic provider requires the 'anthropic' optional dependency"
                ) from error
            client = Anthropic(api_key=self.config.api_key)
        self.client = client

    def name(self, object_id: str, structure: object) -> NamedDefinition:
        payload = asdict(structure) if is_dataclass(structure) else structure
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=256,
            system=(
                "Name a structural semantic-layer object. Return JSON only with "
                "exactly two string fields: name and description. Do not change "
                "the supplied structure or invent business semantics."
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


def name_layer(layer: SemanticLayer, provider: NamingProvider | None = None) -> SemanticLayer:
    """Add names without changing any induced structural objects."""
    provider = provider or MockNamingProvider()
    for entity in layer.entities.values():
        layer.names[entity.table] = provider.name(entity.table, entity)
    for measure in layer.measures.values():
        object_id = f"{measure.aggregation.lower()}:{measure.column}"
        layer.names[object_id] = provider.name(object_id, measure)
    return layer