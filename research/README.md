# Research Index

This directory contains external evidence and analysis supporting the enterprise semantic discovery and governance thesis.

## Working rules

- Preserve downloaded primary sources unchanged.
- Prefer a one-paragraph summary plus a stable source link; do not download a
	source unless local extraction or offline access is necessary.
- Give each source a stable ID such as `SRC-001`.
- Separate sourced claims from our interpretation.
- Cite sources inline as `[SRC-001, p. 3]` for PDFs or `[SRC-002]` for web sources.
- Record access dates for web sources.
- Use research notes to sharpen goals and positioning; do not silently turn hypotheses into product requirements.

## Sources

| ID | Source | Type | Local artifact / URL | Relevance |
|---|---|---|---|---|
| SRC-001 | TDWI & AtScale, *Building a Trusted Semantic Foundation for Generative BI*, sponsored viewpoint, 2026 | Web / Report | https://www.atscale.com/resource/trusted-semantic-foundation-generative-bi/ | Governed semantic foundations, deterministic query paths, ownership, evaluation, explainability, and security |
| SRC-002 | NVIDIA, *How Kumo Relational Works* | Web | https://docs.nvidia.com/sdgm/rfm/introduction | Relational foundation models and prediction over relational context |
| SRC-003 | dbt, *Semantic models* | Web | https://docs.getdbt.com/docs/build/semantic-models | Open semantic model structure: entities, dimensions, metrics, and relationships |
| SRC-004 | Cube, *Agentic analytics platform* | Web | https://cube.dev/product | Governed semantic context for AI agents and BI |
| SRC-005 | Google Cloud, *Looker* | Web | https://cloud.google.com/looker | LookML semantic modeling and conversational/agentic BI |
| SRC-006 | ThoughtSpot, *Modern Analytics Cloud* | Web | https://www.thoughtspot.com/product | Search, automated insights, governed models, and analytics agents |
| SRC-007 | Apache Ossie, incubating | Web | https://github.com/apache/ossie | Vendor-neutral semantic model exchange across BI and AI tools |
| SRC-008 | W3C, *PROV-O: The PROV Ontology* | Web | https://www.w3.org/TR/prov-o/ | Provenance, evidence, derivation, agents, activities, and resolutions |
| SRC-009 | W3C, *SKOS Simple Knowledge Organization System* | Web | https://www.w3.org/TR/skos-reference/ | Concepts, aliases, broader/narrower terms, and taxonomies |
| SRC-010 | Anthropic, *Model Context Protocol* | Web | https://modelcontextprotocol.io/ | Standard agent-facing resources, tools, and prompts interface |
| SRC-011 | dbt Labs, *How to use dbt Wizard: Build Semantic Layer definitions*, updated 2026-09-08, accessed 2026-10-12 | Web | https://docs.getdbt.com/best-practices/how-to-use-wizard/wizard-7-semantic-layer | Semantic model generation is induced from dbt model code and lineage, with warehouse sampling as fallback; no query history or BI usage |
| SRC-012 | dbt Labs, *Model query history* and *View downstream exposures*, updated 2026-07-23, accessed 2026-10-12 | Web | https://docs.getdbt.com/docs/explore/model-query-history ; https://docs.getdbt.com/docs/explore/view-downstream-exposures | Warehouse query logs and Tableau lineage are ingested but reduced to consumption counts and dashboard lineage, not definitions |
| SRC-013 | dbt Labs, *How dbt Wizard works*, updated 2026-10-05, accessed 2026-10-12 | Web | https://docs.getdbt.com/docs/dbt-ai/wizard-how-it-works | Metadata index built from dbt artifacts only; approval per session, "no dedicated audit log" |
| SRC-014 | dbt Labs, *Semantic Layer validation* and *SL FAQs*, updated 2026-09-10, accessed 2026-10-12 | Web | https://docs.getdbt.com/docs/build/validation ; https://docs.getdbt.com/docs/use-dbt-semantic-layer/sl-faqs | Conflict handling is metric-name uniqueness plus prose guidance; no semantic conflict detection |
| SRC-015 | dbt Labs, *dbt platform release notes*, Jan and Jul 2026 entries, accessed 2026-10-12 | Web | https://docs.getdbt.com/docs/dbt-versions/dbt-cloud-release-notes | Open Semantic Interchange artifact emitted at parse time; dbt as publish target |
| SRC-016 | Google Cloud blog, *Looker self-service Explores* (2026-04-06) and *Looker Data Apps* (2026-10-12), accessed 2026-10-12 | Web | https://cloud.google.com/blog/products/business-intelligence/looker-self-service-explores ; https://cloud.google.com/blog/products/business-intelligence/introducing-looker-data-apps | Gemini features consume an authored LookML model; no LookML induction from usage described |
| SRC-017 | Google Cloud blog, *Introducing the Google Cloud Knowledge Catalog* and *What's new in the Agentic Data Cloud*, 2026-04-22, accessed 2026-10-12 | Web | https://cloud.google.com/blog/products/data-analytics/introducing-the-google-cloud-knowledge-catalog ; https://cloud.google.com/blog/products/data-analytics/whats-new-in-the-agentic-data-cloud | Preview: mines "structured schemas, query logs, and BI semantic models"; names "resolving conflicting definitions" as a pillar; no mechanism, verifier, or ruling record described |
| SRC-018 | Google Cloud blog, *Build data agents with the Conversational Analytics API* (2026-02-19) and *Conversational Analytics in Looker now GA* (2025-11-13), accessed 2026-10-12 | Web | https://cloud.google.com/blog/products/data-analytics/build-data-agents-with-conversational-analytics-api ; https://cloud.google.com/blog/products/business-intelligence/looker-conversational-analytics-now-ga | Agent context (system instructions, example and golden queries) is developer-supplied, not mined |
| SRC-019 | Microsoft Learn, *Prep data for AI* (Power BI Copilot): overview, verified answers, AI instructions, ms.date 2026-05 to 2026-09, accessed 2026-10-12 | Web | https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai ; https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai-verified-answers | Hand-authored context; checkbox approval; verified answers explicitly not synced to source visuals |
| SRC-020 | Microsoft Learn, *Fabric data agent concept* and *configurations*, ms.date 2026-05-11 and 2026-08-31, accessed 2026-10-12 | Web | https://learn.microsoft.com/en-us/fabric/data-science/concept-data-agent ; https://learn.microsoft.com/en-us/fabric/data-science/data-agent-configurations | User-supplied example queries; AI recommendations schema- and conversation-based |
| SRC-021 | Microsoft Learn, *Fabric IQ ontology overview* (ms.date 2026-09-15), *Endorsement overview*, *Semantic models in Fabric Data Warehouse* (ms.date 2025-12-05), accessed 2026-10-12 | Web | https://learn.microsoft.com/en-us/fabric/iq/ontology/overview ; https://learn.microsoft.com/en-us/fabric/governance/endorsement-overview ; https://learn.microsoft.com/en-us/fabric/data-warehouse/semantic-models | Ontology generated from existing Power BI semantic models with a proposal-first review and versioned checkpoints; default auto semantic models discontinued Sep 2025 |
| SRC-022 | AWS docs, *Quick Sight Topics*, *custom instructions*, *dataset enrichment*; *DataZone AI recommendations*, accessed 2026-10-12 | Web | https://docs.aws.amazon.com/quicksuite/latest/userguide/topics.html ; https://docs.aws.amazon.com/quicksuite/latest/userguide/dataset-enrichment.html ; https://docs.aws.amazon.com/datazone/latest/userguide/autodoc.html | Semantic context hand-built or imported from dbt/Databricks/Alation files; baseline model sees "only column names and data types"; per-item accept/reject with no rationale |
| SRC-023 | Snowflake docs, *Semantic View Autopilot* (Snowsight wizard), no page date shown, accessed 2026-10-12 | Web | https://docs.snowflake.com/en/user-guide/views-semantic/ui ; https://docs.snowflake.com/en/user-guide/views-semantic/autopilot | **Generates tables, relationships, and metrics from selected tables, sample values, metadata, example SQL, Tableau/Power BI files, and query history**: "Surface historical SQL queries as suggestions to the semantic view." Review is column pick plus inline diff accept/reject; no rationale captured |
| SRC-024 | Snowflake docs, *Cortex Analyst verified query repository*, no page date shown, accessed 2026-10-12 | Web | https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/verified-query-repository | Verified queries carry `verified_by` and `verified_at` but no reason field; Snowsight "offers potential new verified queries based on user behavior," human accepts |
| SRC-025 | Snowflake docs, *Semantic view validation rules*, no page date shown, accessed 2026-10-12 | Web | https://docs.snowflake.com/en/user-guide/views-semantic/validation-rules | Structural rules applied per view at definition time (granularity, relationships, cycles); no cross-view duplicate or conflicting-metric detection |
| SRC-026 | Snowflake-Labs, *semantic-model-generator* README (GitHub), accessed 2026-10-12 | Web | https://github.com/Snowflake-Labs/semantic-model-generator | Open-source predecessor, now "replaced by the native Cortex Analyst Semantic View Generator"; inputs were table metadata, sample values, LLM descriptions, dbt and Looker files; no query history |
| SRC-027 | Databricks docs, *Set up a Genie Agent* and *Tune Genie Agent quality*, updated 2026-10-09, accessed 2026-10-12 | Web | https://docs.databricks.com/aws/en/genie-agents/set-up ; https://docs.databricks.com/aws/en/genie-agents/tune-quality | **"Genie automatically searches for relevant popular workspace queries associated with those assets"**, permission-scoped; author thumbs-up triggers suggested measures, filters, joins; accept/reject dialog, SQL not editable before acceptance, no rationale; conflicts handled by prose ("review and resolve any inconsistencies") |
| SRC-028 | Databricks docs, *Test and monitor a Genie Agent* (benchmarks), updated 2026-09-17, accessed 2026-10-12 | Web | https://docs.databricks.com/aws/en/genie/benchmarks | **Executable validation shipped**: benchmark questions with gold SQL scored by result-set equality (order-insensitive, 4 significant digits, up to 5,000 rows); humans override ratings and "Update ground truth"; benchmarks hand-written, not mined |
| SRC-029 | Databricks docs, *Unity Catalog metric views* overview and *Manage metric views*, updated 2026-09-11 and 2026-10-09, accessed 2026-10-12 | Web | https://docs.databricks.com/aws/en/metric-views/ ; https://docs.databricks.com/aws/en/uc-semantics/metric-views/manage | Authored via SQL DDL, YAML, or UI; Genie "Export to metric view" is author-initiated; owner-only edit, no version history, no certification, no cross-view conflict detection |
| SRC-030 | illumex, LinkedIn company page and posts, accessed 2026-10-12 (vendor site illumex.ai did not resolve from this network) | Web | https://www.linkedin.com/company/illumexai | Marketing-level only: "Generative Semantic Fabric" over the "organizational corpus of knowledge"; claims "10–15% of business logic is conflicted" and will "auto-reconcile definitions"; inputs, mechanism, approval, and rationale not described |
| SRC-031 | Teradata, *teradata-mcp-server* README, *Customizing* guide, *Skills* guide, and DBA tool README (GitHub, MIT), accessed 2026-10-12 | Web | https://github.com/Teradata/teradata-mcp-server ; https://github.com/Teradata/teradata-mcp-server/blob/main/docs/server_guide/CUSTOMIZING.md ; https://github.com/Teradata/teradata-mcp-server/blob/main/docs/server_guide/SKILLS.md | Semantic layer is hand-authored YAML (`cube` with `dimensions`/`measures`, `tool`, `prompt`, `glossary` with synonyms) or a registry of views in the database; an Agent Skill drafts it "based on your existing documentation," not schema or query history. DBQL is read by DBA tools and skills (recent SQL per user/table, "traces table lineage from SQL history") for operations only |
| SRC-032 | Teradata, *Enterprise MCP* and *AI Studio* product pages, no dates shown, accessed 2026-10-12 | Web | https://www.teradata.com/platform/ai-studio/enterprise-mcp ; https://www.teradata.com/platform/ai-studio | Governance means RBAC and tool tiers, plus a "SQL-Gen tool" that "Translates natural language questions into SQL"; no semantic layer, glossary, or review workflow described. AI Studio "will be generally available soon," Enterprise MCP first |
| SRC-033 | Teradata, *Tera* product page (early access), no date shown, accessed 2026-10-12 | Web | https://www.teradata.com/platform/tera | "Tera Context Engine" supplies "governed definitions, industry knowledge, lineage, policies"; source of those definitions and any human review not described; "Request early access" |
| SRC-034 | Teradata, *Agents* product page, no date shown, accessed 2026-10-12 | Web | https://www.teradata.com/platform/agents | Platform agents "continuously analyze DBQL, telemetry, and cost signals," "surface drift and propose tuning, sizing, and FinOps policies"; "DBAs review and approve higher-impact changes." The propose-review-approve-drift loop applied to performance, not to meaning. Analytics agents: "Text-to-SQL generates Teradata SQL" |

All sources are cited by reference and URL without storing local binary artifacts.

## Note template

```markdown
### [SRC-NNN] Title

Summary: One paragraph stating the relevant claim, why it matters, and any
limits or uncertainty.

Source: https://example.com/source
Accessed: YYYY-MM-DD
Architecture relevance: [section](../docs/ARCHITECTURE.md#section-anchor)
```

## Notes

- [Marketplace landscape](marketplace.md)
- [Competitor matrix](competitors.md)
- [Prior art](prior-art.md) — vendor rows verified against primary docs (SRC-011 to SRC-030); academic and analyst rows still unverified recall
- [First principles](first-principles.md)
- [MCP integration](mcp.md)

## Architecture links

- [Project architecture](../docs/ARCHITECTURE.md)
- [Analytical memory target model](../docs/ARCHITECTURE.md#analytical-memory-target-model)
- [Scope lock and next build order](../docs/ARCHITECTURE.md#scope-lock-and-next-build-order)
