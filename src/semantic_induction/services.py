"""Client-neutral application services for analytical memory and investigations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from semantic_induction.investigate import InvestigationResult, investigate
from semantic_induction.labeling import LabelingStore
from semantic_induction.memory import RetrievalHit, retrieve
from semantic_induction.models import Catalog


@dataclass(frozen=True)
class InvestigationService:
    store: LabelingStore
    catalog: Catalog
    connection: Any

    def search(self, question: str, limit: int = 10) -> list[RetrievalHit]:
        return retrieve(question, self.store.memory, limit=limit)

    def review_items(self) -> list[dict[str, object]]:
        return self.store.review_items()

    def investigate(self, question: str) -> InvestigationResult:
        return investigate(question, self.store, self.catalog, self.connection)


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
    }
