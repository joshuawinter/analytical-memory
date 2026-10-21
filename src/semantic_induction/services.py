"""Client-neutral application services for analytical memory and investigations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from semantic_induction.investigate import InvestigationResult, investigate
from semantic_induction.labeling import LabelingStore
from semantic_induction.memory import Resolution, RetrievalHit, retrieve
from semantic_induction.models import Catalog


@dataclass(frozen=True)
class InvestigationService:
    store: LabelingStore
    catalog: Catalog
    connection: Any

    def search(self, question: str, limit: int = 10) -> list[RetrievalHit]:
        return retrieve(question, self.store.memory, limit=limit)

    def review_items(self) -> list[dict[str, object]]:
        return self.store.review_items(self.catalog)

    def investigate(self, question: str, as_of: datetime | None = None) -> InvestigationResult:
        return investigate(question, self.store, self.catalog, self.connection, as_of=as_of)

    def record_decision(
        self,
        definition_id: str,
        decision: str,
        rationale: str,
        decided_by: str,
        corrected_definition: str = "",
        aliases: str = "",
        valid_from: datetime | None = None,
    ) -> Resolution:
        """Record a human's Stage 4c ruling. The decision and rationale must

        come from the human on the other end of whatever client called this
        -- an MCP client (Claude Code included) must never fabricate
        ``decided_by`` or invent a rationale on the reviewer's behalf. This
        is the same call ``labeling_app.py``'s ``/label`` endpoint makes;
        every client goes through one path, one audit trail.

        ``valid_from`` dates the ruling's effect; it defaults to now. A later
        ruling on the same definition supersedes this one from its own
        ``valid_from`` onward, and answers asked "as of" an earlier moment
        still resolve under this one.
        """
        resolution = self.store.label(definition_id, decision, rationale, decided_by, valid_from=valid_from)
        if resolution.decision == "APPROVE" and (corrected_definition or aliases):
            self.store.enrich(definition_id, corrected_definition, aliases)
        return resolution


def investigation_payload(result: InvestigationResult) -> dict[str, object]:
    """Serialize an investigation result for browser, CLI, or MCP clients."""
    return {
        "question": result.question,
        "status": result.status,
        "definition": result.inferred_definition,
        "evidence": [item.source_ref for item in result.evidence],
        "sql": result.sql,
        "columns": result.columns,
        "rows": result.rows,
        "message": result.message,
        "candidates": list(result.candidates),
    }
