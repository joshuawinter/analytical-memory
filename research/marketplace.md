# Marketplace Landscape

Status: working analysis, 2026-09-13. Related architecture: [analytical memory target model](../docs/ARCHITECTURE.md#analytical-memory-target-model), [scope lock](../docs/ARCHITECTURE.md#scope-lock-and-next-build-order).

## Market center of gravity

The market is converging on governed semantic context for Generative BI and agentic analytics. AtScale, dbt, Cube, Looker, and ThoughtSpot all position semantic models as the control plane between probabilistic AI and enterprise data. [SRC-001, pp. 2-5] [SRC-003] [SRC-004] [SRC-005] [SRC-006]

Common promises include:

- consistent metric definitions;
- deterministic or governed query generation;
- business ownership and approval;
- lineage and explainability;
- security and policy enforcement;
- conversational and agentic analytics;
- portability across BI tools and AI agents.

## Strategic implication

"Trusted semantic layer for Generative BI" is crowded positioning. The differentiated question is upstream:

> How are incomplete, contradictory, or undocumented enterprise semantics discovered, reconciled, approved, and kept current?

Our project should be positioned as a semantic discovery and governance system that can feed existing semantic platforms, not as another BI frontend or query engine.

## Capability layers

```text
Enterprise evidence
  SQL, reports, dashboards, schemas, logs, documents, decisions
                         |
Semantic discovery and reconciliation
  candidate concepts, metrics, grains, filters, conflicts, provenance
                         |
Governed semantic publication
  dbt, Ossie, AtScale, Cube, LookML, internal APIs
                         |
Generative BI and analytical agents
  questions, investigations, explanations, actions
```

## Open market questions

- Do existing platforms offer reliable import from historical SQL usage, or mainly authoring and serving?
- How do they distinguish human intent from repeated BI-tool emissions?
- How do they represent conflicting definitions and rejected interpretations?
- How do they detect semantic drift between certified definitions and actual usage?
- Which portable semantic format becomes durable: Apache Ossie, vendor formats, or both?

These are research questions, not claims of absence. Verify them against product documentation and demonstrations before presenting them externally.
