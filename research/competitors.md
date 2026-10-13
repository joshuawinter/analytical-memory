# Competitor and Adjacent-System Matrix

Status: working analysis, 2026-09-13; warehouse-native row and deep-dive added 2026-10-12 from verified primary docs (see [prior art](prior-art.md) section 0). Related architecture: [Stage 6 validation](../docs/ARCHITECTURE.md#stage-6--validation-harness), [analytical memory target model](../docs/ARCHITECTURE.md#analytical-memory-target-model).

| Category | Representative systems | Primary job | Starting assumption | Possible integration boundary |
|---|---|---|---|---|
| Semantic-layer platforms | AtScale, dbt Semantic Layer, Cube, Looker | Define, govern, and serve metrics | The organization can author or maintain definitions | Export approved definitions; audit usage against them |
| Warehouse-native AI semantic generation | Snowflake Semantic View Autopilot (`SRC-023`), Databricks Genie Agents (`SRC-027`), Google Knowledge Catalog Preview (`SRC-017`), dbt Wizard (`SRC-011`), Fabric IQ ontology (`SRC-021`) | Draft the semantic layer from schema, code, BI files, and (Snowflake, Databricks, Google) query history | Someone will accept or reject each proposal; name uniqueness is enough conflict handling | Consume their drafts as candidate evidence; publish rulings back as verified queries, trusted assets, or metric views |
| Generative BI | ThoughtSpot, Looker Conversational Analytics, Power BI Copilot | Ask questions, explore, summarize, and investigate | A governed model/context layer exists | Supply evidence-backed definitions and review outcomes |
| Relational foundation models | Kumo Relational, RelBench ecosystem | Predict over relational context | Schema, keys, and relationships are available | Provide business semantics and provenance around relational data |
| Process intelligence | Celonis and adjacent process-mining tools | Discover and improve operational processes | Event logs and process keys are available | Connect process behavior to metrics, definitions, and findings |
| Semantic interchange | Apache Ossie | Exchange semantic models across tools | A semantic model has already been authored | Publish discovered and approved models in portable formats |
| Data catalogs and governance | Catalog, lineage, quality, and policy platforms | Describe, govern, and secure data assets | Metadata and ownership processes exist | Feed evidence, ownership, policy, and drift signals |

## Our wedge

The project does not compete first on dashboards, prediction, query serving, or model architecture. It targets the missing or expensive upstream work:

```text
actual enterprise usage -> candidate semantics -> human reconciliation -> governed semantic model
```

The strongest differentiation is evidence provenance, conflict visibility, human resolution, and drift detection. The first arrow, usage to candidates, is no longer ours alone: Snowflake and Databricks ship it (verified 2026-10-12). The three arrows after it are where no verified product goes.

### Deep-dive: warehouse-native generation vs. governed memory

As of 2026-10-12, Snowflake Semantic View Autopilot will "Surface historical SQL queries as suggestions to the semantic view" (`SRC-023`), and Databricks Genie "automatically searches for relevant popular workspace queries associated with those assets" (`SRC-027`). Both present proposals for per-item accept or reject. Neither records a reason, neither compares two definitions of the same measure (Snowflake validation is per-view and structural, `SRC-025`; Databricks tells authors to "review and resolve any inconsistencies" by hand), and neither re-checks an approved definition against later usage. Snowflake's verified queries carry a `verified_by` name (`SRC-024`), the closest shipped thing to a ruling record. Databricks Genie benchmarks score answers against gold SQL by result-set equality (`SRC-028`), the closest shipped thing to Stage 6, but over hand-written benchmarks and the agent's answers, not over induced definitions and the usage they came from. The integration boundary is therefore two-way: their drafts are candidate evidence for us, and our rulings publish back into their verified-query, trusted-asset, and metric-view slots.

## Leveraging existing standards vs. our unique capability

We stand on existing open-source standards and community projects rather than reinventing solved problems:

| Layer | Open source / community standard we adopt | What we DO NOT reinvent | What is our unique contribution |
|---|---|---|---|
| **SQL Parsing & Dialects** | `sqlglot` | AST parsing, dialect transpilation, qualifier logic | Extracting usage signatures, grains, and invariant filters across query blocks |
| **Relational Execution & Profiling** | `DuckDB` | Query execution, storage, data profiling, sampling | Statistical fan-out detection on candidate metric paths |
| **Semantic Interchange** | **Apache Ossie** (`SRC-007`) | Semantic schema specification (YAML format for datasets, dimensions, metrics, joins) | **Auto-inducing** the Ossie model from historical SQL logs and query exhaust instead of requiring human authoring of hundreds of YAML models |
| **Agent Protocol** | **Model Context Protocol (MCP)** (`SRC-010`) | JSON-RPC stdio protocol, tool/resource contracts | Approval-gated memory retrieval and deterministic execution tools |
| **Relational Prediction** | Kumo RFM / RelBench (`SRC-002`) | Neural graph transformer training and probabilistic prediction over graphs | Exact analytical metrics, accounting definitions, and governance required for corporate reporting |

### Deep-dive: Apache Ossie vs. Semantic Induction
Apache Ossie provides complete specification files (such as `tpcds_semantic_model.yaml`). However, Ossie is an **interchange standard**, not a discovery engine—every line of that YAML was hand-authored by an architect. In an enterprise with thousands of tables, stored procedures, and reports, manual authoring does not happen. Our system discovers, ranks, and reconciles metric candidates from usage, then outputs standard Apache Ossie YAML to be consumed by Cube, dbt, or AtScale.

### Deep-dive: Kumo RFM vs. Deterministic Governance
Kumo uses Graph Transformers to predict future values (e.g. predicting whether a customer will churn) via in-context learning. It does not parse query logs to induce deterministic financial metrics or GAAP-compliant accounting definitions. Our analytical memory is deterministic, exact, auditable, and governed by corporate reviewers.

## Claims discipline

Avoid saying that existing products cannot perform a capability unless verified with primary documentation or a controlled evaluation. Prefer:

- "Our current research focuses on..."
- "The reviewed product documentation emphasizes..."
- "This creates a potential integration or research opportunity..."
