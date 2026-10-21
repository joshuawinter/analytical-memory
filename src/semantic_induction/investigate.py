"""Execute evidence-backed analytical investigations without inventing structure."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from semantic_induction.compile import CompileError, compile_metric
from semantic_induction.labeling import LabelingStore
from semantic_induction.memory import Evidence, MetricDefinition, retrieve
from semantic_induction.models import Catalog, Metric


@dataclass(frozen=True)
class InvestigationResult:
    question: str
    status: str
    definition_id: str | None = None
    inferred_definition: str | None = None
    evidence: tuple[Evidence, ...] = ()
    sql: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    message: str | None = None
    # The fork, when there is one: every rival definition the question
    # matched. Non-empty on NEEDS_REVIEW for a contested measure and on
    # AMBIGUOUS, so a client can show the reviewer what has to be ruled on
    # instead of a bare refusal.
    candidates: tuple[str, ...] = ()


def _metric_from_definition(definition: MetricDefinition) -> Metric:
    return Metric(
        measure=definition.measure,
        grain=frozenset(definition.grain),
        join_path=definition.join_path,
        default_filters=definition.default_filters,
        support=0,
        seen_in=definition.evidence_ids,
    )


def investigate(
    question: str,
    store: LabelingStore,
    catalog: Catalog,
    connection: Any,
    as_of: datetime | None = None,
) -> InvestigationResult:
    """Answer only from the definition approved as of ``as_of``, otherwise request review.

    ``as_of`` defaults to now. Passing an earlier moment answers the question
    under the ruling that was in force then, which is what makes last
    quarter's number explicable after this quarter's re-ruling (Stage 4c:
    "weights cannot do point-in-time").
    """
    hits = [hit for hit in retrieve(question, store.memory) if hit.kind == "METRIC_DEFINITION"]
    definitions = {hit.object_id: store.memory.metric_definitions[hit.object_id] for hit in hits}
    approved = [
        hit.object_id
        for hit in hits
        if (ruling := store.resolution_as_of(hit.object_id, as_of)) is not None
        and ruling.decision == "APPROVE"
    ]

    if len(approved) > 1:
        return InvestigationResult(
            question=question,
            status="AMBIGUOUS",
            message="Multiple approved metric definitions matched the question.",
            candidates=tuple(approved),
        )
    if not approved:
        contested = tuple(
            definition_id
            for definition_id, definition in definitions.items()
            if definition.conflict_id is not None
        )
        if contested:
            return InvestigationResult(
                question=question,
                status="NEEDS_REVIEW",
                message=(
                    "Competing definitions exist for this measure and no ruling is in "
                    "force as of the requested moment. A human must rule before the "
                    "question can be answered; the system will not pick by frequency."
                ),
                candidates=contested,
            )
        return InvestigationResult(
            question=question,
            status="NEEDS_REVIEW",
            message="No approved metric definition matched the question.",
        )

    definition = definitions[approved[0]]
    evidence = tuple(
        store.memory.evidence[item]
        for item in definition.evidence_ids
        if item in store.memory.evidence
    )
    sql: str | None = None
    try:
        sql = definition.query_sql or compile_metric(_metric_from_definition(definition), catalog)
        result = connection.execute(sql)
        columns = tuple(item[0] for item in result.description)
        rows = tuple(result.fetchall())
    except CompileError as error:
        return InvestigationResult(
            question, "UNSUPPORTED", definition.definition_id,
            definition.inferred_definition, evidence, message=str(error)
        )
    except Exception as error:
        return InvestigationResult(
            question, "EXECUTION_FAILED", definition.definition_id,
            definition.inferred_definition, evidence, sql=sql, message=str(error)
        )
    return InvestigationResult(
        question=question,
        status="ANSWERED",
        definition_id=definition.definition_id,
        inferred_definition=definition.inferred_definition,
        evidence=evidence,
        sql=sql,
        columns=columns,
        rows=rows,
    )
