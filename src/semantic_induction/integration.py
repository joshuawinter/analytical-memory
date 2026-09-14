"""TPC-DI integration artifacts kept separate from analytical query facts."""
from __future__ import annotations

from dataclasses import dataclass, field

from semantic_induction.models import (
    BusinessKeyMapping,
    DataQualityOutcome,
    LoadBatch,
    MappingRule,
    TargetRowVersion,
    TemporalPolicy,
)


@dataclass
class IntegrationWorkflow:
    """A replayable source-to-target workflow and its observed evidence."""

    workflow_id: str
    mappings: list[MappingRule] = field(default_factory=list)
    key_mappings: list[BusinessKeyMapping] = field(default_factory=list)
    temporal_policies: list[TemporalPolicy] = field(default_factory=list)
    batches: list[LoadBatch] = field(default_factory=list)
    quality_outcomes: list[DataQualityOutcome] = field(default_factory=list)
    target_versions: list[TargetRowVersion] = field(default_factory=list)