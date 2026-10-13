"""Human labeling workflow for evidence-backed metric definitions."""
from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from semantic_induction.audit import AuditLedger
from semantic_induction.compile import CompileError, compile_metric
from semantic_induction.memory import AnalyticalMemory, Resolution, is_publishable_metric
from semantic_induction.models import Catalog, Metric
from semantic_induction.store import MemoryStore, parse_front_matter, render_entry, safe_segment

DECISIONS = {"APPROVE", "REJECT", "CLARIFY"}


class LabelingError(ValueError):
    """Raised when a human label cannot be applied."""


class LabelingStore:
    """Apply and persist human decisions without modifying source evidence.

    Two durable records are kept side by side. ``labels.json`` is the mutable
    convenience projection the browser UI reads. The ``<labels>.memory/``
    directory is the system of record: every ruling and vocabulary enrichment
    is written as an immutable, content-addressed markdown entry whose version
    event is chained into the same audit ledger as the decision itself (see
    ``store.py`` and ARCHITECTURE.md "Memory storage format").
    """

    def __init__(self, memory: AnalyticalMemory, path: Path | None = None):
        self.memory = memory
        self.path = path
        self.enrichments: dict[str, dict[str, object]] = {}

    @property
    def enrichment_path(self) -> Path | None:
        return self.path.with_suffix(".vocabulary.json") if self.path else None

    @property
    def audit_path(self) -> Path | None:
        return self.path.with_suffix(".audit.jsonl") if self.path else None

    @property
    def audit_ledger(self) -> AuditLedger:
        return AuditLedger(self.audit_path)

    @property
    def memory_root(self) -> Path | None:
        return self.path.with_suffix(".memory") if self.path else None

    @property
    def memory_store(self) -> MemoryStore | None:
        """Append-only shared memory, chained into the same ledger as rulings."""
        if self.memory_root is None:
            return None
        return MemoryStore(self.memory_root, self.audit_ledger)

    def label(
        self,
        definition_id: str,
        decision: str,
        rationale: str,
        decided_by: str = "reviewer",
    ) -> Resolution:
        decision = decision.upper().strip()
        if definition_id not in self.memory.metric_definitions:
            raise LabelingError(f"unknown metric definition: {definition_id!r}")
        if decision not in DECISIONS:
            raise LabelingError(f"decision must be one of {sorted(DECISIONS)!r}")
        if not rationale.strip():
            raise LabelingError("rationale is required")
        if not decided_by.strip():
            raise LabelingError("decided_by is required")

        previous = self.memory.resolutions.get(definition_id)
        resolution = Resolution(
            resolution_id=f"resolution:{definition_id}:{len(self.memory.resolutions) + 1}",
            target_id=definition_id,
            decision=decision,
            rationale=rationale.strip(),
            decided_by=decided_by.strip(),
            decided_at=datetime.now(timezone.utc),
        )
        self.memory.resolutions[definition_id] = resolution
        self.save()
        self.audit_ledger.append(
            "KNOWLEDGE_DECISION",
            resolution.decided_by,
            {
                "definition_id": definition_id,
                "decision": resolution.decision,
                "rationale": resolution.rationale,
                "resolution_id": resolution.resolution_id,
            },
        )
        store = self.memory_store
        if store is not None:
            store.write(
                f"resolutions/{safe_segment(definition_id)}",
                self.render_resolution(resolution, supersedes_id=previous.resolution_id if previous else None),
                actor=resolution.decided_by,
            )
        return resolution

    def render_resolution(self, resolution: Resolution, supersedes_id: str | None = None) -> str:
        """Render a ruling as the small text entry an agent reads verbatim."""
        definition = self.memory.metric_definitions[resolution.target_id]
        concept = self.memory.concepts.get(definition.concept_id)
        enrichment = self.enrichments.get(resolution.target_id, {})
        metadata = {
            "kind": "resolution",
            "resolution_id": resolution.resolution_id,
            "target": resolution.target_id,
            "concept": concept.preferred_label if concept else definition.concept_id,
            "decision": resolution.decision,
            "decided_by": resolution.decided_by,
            "decided_at": resolution.decided_at.isoformat(),
            "supersedes": supersedes_id,
            "measure": f"{definition.measure[0]}({definition.measure[1]})",
            "grain": list(definition.grain),
            "filters": [f"{item.column} {item.op} {item.value}" for item in definition.default_filters],
            "evidence": list(definition.evidence_ids),
        }
        body_lines = [f"# {metadata['concept']}: {resolution.decision}", "", "## Rationale", "", resolution.rationale]
        corrected = str(enrichment.get("corrected_definition", "")).strip()
        fallback = f"{metadata['measure']} by {', '.join(definition.grain) or 'total'} (observed, not yet described)"
        body_lines += ["", "## Definition", "", corrected or definition.inferred_definition or fallback]
        return render_entry(metadata, "\n".join(body_lines))

    def enrich(self, definition_id: str, corrected_definition: str, aliases: str) -> None:
        """Save reviewer language without overwriting the inferred evidence record."""
        if definition_id not in self.memory.metric_definitions:
            raise LabelingError(f"unknown metric definition: {definition_id!r}")
        alias_list = tuple(dict.fromkeys(
            alias.strip() for alias in aliases.split(",") if alias.strip()
        ))
        self.enrichments[definition_id] = {
            "corrected_definition": corrected_definition.strip(),
            "aliases": list(alias_list),
        }
        concept_id = self.memory.metric_definitions[definition_id].concept_id
        concept = self.memory.concepts.get(concept_id)
        if concept and alias_list:
            self.memory.concepts[concept_id] = replace(
                concept, aliases=tuple(dict.fromkeys((*concept.aliases, *alias_list)))
            )
        self.save()
        self.audit_ledger.append(
            "VOCABULARY_ENRICHMENT",
            "reviewer",
            {
                "definition_id": definition_id,
                "corrected_definition": corrected_definition.strip(),
                "aliases": list(alias_list),
            },
        )
        store = self.memory_store
        if store is not None:
            metadata = {
                "kind": "vocabulary",
                "target": definition_id,
                "concept": concept.preferred_label if concept else concept_id,
                "aliases": list(alias_list),
            }
            body = corrected_definition.strip() or "Aliases only."
            store.write(f"vocabulary/{safe_segment(definition_id)}", render_entry(metadata, body), actor="reviewer")
            resolution = self.memory.resolutions.get(definition_id)
            if resolution is not None:
                path = f"resolutions/{safe_segment(definition_id)}"
                current = parse_front_matter(store.read(path) or "")
                supersedes_id = current.get("supersedes")
                store.write(
                    path,
                    self.render_resolution(resolution, supersedes_id=str(supersedes_id) if supersedes_id else None),
                    actor=resolution.decided_by,
                )

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: asdict(value) for key, value in self.memory.resolutions.items()}
        self.path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        if self.enrichment_path:
            self.enrichment_path.write_text(
                json.dumps(self.enrichments, indent=2) + "\n", encoding="utf-8"
            )

    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        for definition_id, values in payload.items():
            if definition_id not in self.memory.metric_definitions:
                continue
            values["decided_at"] = datetime.fromisoformat(values["decided_at"])
            values["valid_from"] = (
                datetime.fromisoformat(values["valid_from"]) if values.get("valid_from") else None
            )
            values["valid_to"] = (
                datetime.fromisoformat(values["valid_to"]) if values.get("valid_to") else None
            )
            self.memory.resolutions[definition_id] = Resolution(**values)
        if self.enrichment_path and self.enrichment_path.exists():
            self.enrichments = json.loads(self.enrichment_path.read_text(encoding="utf-8"))
            for definition_id, enrichment in self.enrichments.items():
                definition = self.memory.metric_definitions.get(definition_id)
                concept = self.memory.concepts.get(definition.concept_id) if definition else None
                if concept:
                    aliases = tuple(enrichment.get("aliases", []))
                    self.memory.concepts[concept.concept_id] = replace(
                        concept, aliases=tuple(dict.fromkeys((*concept.aliases, *aliases)))
                    )

    def review_items(self, catalog: Catalog | None = None) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for definition in self.memory.metric_definitions.values():
            structured = is_publishable_metric(definition, set(self.memory.profiles))
            concept = self.memory.concepts.get(definition.concept_id)
            evidence = [self.memory.evidence[item] for item in definition.evidence_ids if item in self.memory.evidence]
            resolution = self.memory.resolutions.get(definition.definition_id)
            enrichment = self.enrichments.get(definition.definition_id, {})
            tables = set()
            tables.update(definition.profile_tables)
            if "." in definition.measure[1]:
                tables.add(definition.measure[1].split(".", 1)[0])
            tables.update(item.split(".", 1)[0] for item in definition.grain if "." in item)
            tables.update(item.left.split(".", 1)[0] for edge in definition.join_path for item in [edge])
            tables.update(item.right.split(".", 1)[0] for edge in definition.join_path for item in [edge])
            samples = []
            for table in sorted(tables):
                profile = self.memory.profiles.get(table)
                if not profile or not profile.sample_rows:
                    continue
                samples.append(
                    {
                        "table": table,
                        "columns": list(profile.sample_columns),
                        "rows": [list(row) for row in profile.sample_rows[:3]],
                    }
                )
            sql = definition.query_sql
            if sql is None and catalog is not None:
                try:
                    sql = compile_metric(
                        Metric(
                            measure=definition.measure,
                            grain=frozenset(definition.grain),
                            join_path=definition.join_path,
                            default_filters=definition.default_filters,
                            support=0,
                            seen_in=(),
                        ),
                        catalog,
                    )
                except CompileError:
                    sql = None
            items.append(
                {
                    "definition_id": definition.definition_id,
                    "label": concept.preferred_label if concept else definition.measure[1],
                    "inferred_definition": definition.inferred_definition,
                    "structured": structured,
                    "profile_notes": list(definition.profile_notes),
                    "samples": samples,
                    "sql": sql,
                    "measure": f"{definition.measure[0]}({definition.measure[1]})",
                    "grain": list(definition.grain),
                    "filters": [f"{item.column} {item.op} {item.value}" for item in definition.default_filters],
                    "joins": [f"{item.left} = {item.right}" for item in definition.join_path],
                    "evidence": [item.source_ref for item in evidence],
                    "confidence": definition.confidence,
                    "decision": resolution.decision if resolution else None,
                    "rationale": resolution.rationale if resolution else "",
                    "corrected_definition": enrichment.get("corrected_definition", ""),
                    "aliases": enrichment.get("aliases", list(concept.aliases) if concept else []),
                }
            )
        return items