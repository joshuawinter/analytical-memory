# Prior Art: Has Anyone Looked Into This Before?

Status: **PARTIALLY VERIFIED, 2026-10-21.** Section 0 is verified against
primary vendor documentation and carries `SRC-NNN` IDs. On 2026-10-21 the
rows the paper cites were verified against arXiv, Crossref, or the
publisher: PA-01, PA-04, PA-07, PA-14, PA-15, PA-20, PA-21 (BIRD, Spider 2.0,
BEAVER), and PA-26 (Uber only). Those rows now carry `SRC-035` to `SRC-044`
and are in [README.md](README.md). Everything else in sections 1, 2, and 4
remains model recall: a verification queue, not evidence. Nothing cited in
ARCHITECTURE.md, the deck, or the paper may come from an unverified row.
Provisional IDs are `PA-NN`. Sources that could not be reached from this
network are marked as such rather than deleted.

Related: [competitors](competitors.md), [marketplace](marketplace.md),
[first principles](first-principles.md),
[Premise](../docs/ARCHITECTURE.md#premise).

## The question

The thesis has five parts. Prior art has to be checked against each one
separately, because the honest answer differs by part:

```text
A. Usage encodes meaning      (SQL corpus is labelled assertions about semantics)
B. Induce a semantic layer     (metrics, joins, filters, grains) from that corpus
C. Detect self-disagreement    (two high-support definitions of one measure)
D. Human ruling, stored        (normative layer captured, outranks frequency, ledgered)
E. Executable validation       (compile back to SQL, check result equality)
```

Short form of the verdict after vendor verification: **A is well established.
B is shipping: Snowflake and Databricks both induce semantic context from
warehouse query history today, and Google has announced the same in Preview.
C is named by Google and illumex but no shipped mechanism is documented
anywhere. D exists only as accept/reject with, at best, a verifier name.
E exists as Databricks Genie benchmarks, which validate answers against gold
SQL by result-set equality, but not as validation of induced definitions
against the usage they came from. C, D, and E as a connected, ledgered loop
are not occupied by anyone verified.** The vocabulary the field uses for the
neighbourhood is "active metadata", "metric store / semantic layer",
"ontology", "knowledge graph + LLM", and lately "context layer for agents".

## Verification procedure

For each row: fetch the primary URL, confirm title/venue/year, write a
one-paragraph summary in the README note template, assign an `SRC-NNN`, and
move the row to [README.md](README.md). Mark rows that turn out not to exist
as such rather than deleting them, so the same recall error is not repeated.

Priority order: section 3 (vendors) first, because if Snowflake or Databricks
already induce semantic models from query history the wedge narrows and the
deck's Slide 1 claim needs rewording. **Done 2026-10-12: they do. See
section 0 and the revised verdict in section 5.** Then section 2 (LLM-era
academic), because it supplies the benchmark and the lift numbers. Section 1
last; it is citation hygiene, not strategy.

## 0. Verified (accessed 2026-10-12)

dbt, Snowflake, Databricks, Google, Microsoft, and AWS were reached through
primary documentation; illumex only through its LinkedIn page. The pattern
splits in two. **dbt, Microsoft, and AWS** generate from schema or authored
code. **Snowflake and Databricks** generate from query history as well, and
Google has announced the same. Across all of them, conflict detection is
name uniqueness or prose guidance, approval is accept/reject with no
rationale, and nothing re-checks an approved definition against later usage.

| Vendor | Feature | Induction source | Conflicts | Ruling + rationale | Drift | Source |
|---|---|---|---|---|---|---|
| dbt Labs | dbt Wizard "Build Semantic Layer definitions"; dbt Copilot one-click semantic models | **dbt model code**: grain, columns, lineage, nearby YAML; warehouse sampling as fallback. No query history, no BI usage. | No | Per-file diff accept/reject. Docs state "no dedicated audit log" and approval is not scoped per action. | No | [SRC-011], [SRC-013] |
| dbt Labs | Catalog "Model query history" | **Warehouse query logs** (Snowflake, BigQuery, Redshift, Databricks) ingested, reduced to SELECT counts per model. Not used for generation. | No | No | Usage counts only | [SRC-012] |
| dbt Labs | `dbt sl validate` | n/a | **Name uniqueness only**, not semantic equivalence. FAQ handles differing team definitions with prose guidance. | No | No | [SRC-014] |
| dbt Labs | Catalog auto-exposures | **Tableau workbook lineage**, dashboard level, no measure ingestion. Power BI "coming soon". | No | No | No | [SRC-012] |
| dbt Labs | Open Semantic Interchange (Ossie / OSI) artifact | Publish format, written at parse time since Jul 2026. Confirms dbt as a publish target. | n/a | n/a | n/a | [SRC-015] |
| **Snowflake** | **Semantic View Autopilot** (Snowsight); CoCo conversational generation; Semantic Studio | **Query history**: "Surface historical SQL queries as suggestions to the semantic view," scoped to the creating role's visible history, used for relationships and verified-query suggestions. Plus selected tables and columns, sample values, metadata (cardinality counting for keys), typed or CSV example SQL, Tableau and Power BI files, existing YAML. Generates logical tables, relationships, and metrics. | No. Validation rules are per view and structural [SRC-025]. | Column pick before generation; post-generation suggestions applied "as needed"; CoCo changes are inline diffs to accept or reject. No rationale. | No | [SRC-023], [SRC-025] |
| Snowflake | Cortex Analyst verified query repository | Human-saved question plus SQL pairs. Snowsight "offers potential new verified queries based on user behavior." | No | **`verified_by` and `verified_at` fields.** Closest verified thing to a named verifier. No reason field. | No | [SRC-024] |
| Snowflake | Open-source semantic-model-generator (Streamlit) | Table metadata, sample values, LLM descriptions flagged with `__` for human confirmation, dbt and Looker files. No query history. **Superseded** by the native generator. | No | Fill-in placeholders fail validation if left. | No | [SRC-026] |
| **Databricks** | **Genie Agents** (formerly Genie spaces): set-up knowledge mining | **Query history**: "Genie automatically searches for relevant popular workspace queries associated with those assets," scoped to queries the author has CAN VIEW on. Genie Code "reads your data and suggests context" (table descriptions, example queries). Author thumbs-up or result download triggers suggested measures, filters, fields, and joins. UC primary and foreign keys auto-saved as joins. | No. Docs: guidance must be "free from conflicting or ambiguous information"; "a key task is to review and resolve any inconsistencies." | "Review Suggested Queries" dialog: accept, edit title, or reject per item; SQL not editable until accepted. Trusted assets are marked by anyone with CAN EDIT. No rationale. | "Periodic" monitoring tab; "behavior does not change based on user feedback alone" | [SRC-027] |
| Databricks | Genie benchmarks | Hand-written questions with optional gold SQL; "Add as benchmark" from any chat response; Genie drafts the SQL answer for review. | No | Humans override Good/Bad and "Update ground truth." | Re-run on demand | [SRC-028] |
| Databricks | Unity Catalog metric views | Authored (SQL DDL, YAML, UI). Genie "Export to metric view" is author-initiated. | No | Owner-only edit; no version history, no certification. | No | [SRC-029] |
| **illumex** | Generative Semantic Fabric; illumex Echo (unstructured) | "Organizational corpus of knowledge." Inputs not enumerated on the pages reached. | **Claimed**: "10–15% of business logic is conflicted"; will "auto-reconcile definitions." No mechanism described. | Not described | Posts discuss "semantic drift"; no mechanism described | [SRC-030], marketing-level only |
| **Teradata** | teradata-mcp-server (open source) semantic layer: `cube`, `tool`, `prompt`, `glossary` YAML; database registry views | **Hand-authored.** The only automation is an Agent Skill that drafts config "based on your existing documentation." DBQL is read by DBA tools (recent SQL per user and table) and skills ("traces table lineage from SQL history") for operations, lineage, and drop impact, never for definitions. | No. Glossary terms are "automatically enriched with references from cubes and tools," which is cross-linking, not conflict detection. | None. YAML in a config directory; Guard Mode confirmations are for destructive SQL. | No | [SRC-031] |
| Teradata | Enterprise MCP; AI Studio; Tera (early access) with "Tera Context Engine" | Context Engine supplies "governed definitions, industry knowledge, lineage, policies." Where the definitions come from is not stated anywhere reached. Enterprise MCP's "SQL-Gen tool" is schema-based text-to-SQL. AI Studio not yet GA. | No | Governance is RBAC and tool tiers. No review workflow for definitions. | No | [SRC-032], [SRC-033] |
| Teradata | Tera platform agents (tuning, sizing, FinOps) | **DBQL mined continuously**, but for performance: agents "surface drift and propose tuning, sizing, and FinOps policies." | n/a | **"DBAs review and approve higher-impact changes. Low-impact actions run within defined guardrails."** The project's loop shape, applied to query tuning rather than meaning. No rationale field described. | Yes, for workload drift, not semantic drift | [SRC-034] |
| Looker | Self-service Explores; Gemini in Explores; Looker Data Apps; Conversational Analytics | File upload creates an Explore; Gemini generates queries and expressions over an **authored** LookML model. Conversational Analytics API context (`system_instruction`, `example_queries`, "golden queries") is developer-supplied. | No ("governed centrally" means central authoring) | No | No; "review agent traces and user feedback" only | [SRC-016], [SRC-018] |
| **Google** | **Knowledge Catalog (ex-Dataplex) continuous enrichment, automated context curation, verified queries** | **Query logs, schemas, and BI semantic models.** Blog: "actively mine structured schemas, query logs, and BI semantic models"; "analyzing usage logs across your organization and profiling data." Generates glossaries, relationships, "verified SQL patterns." **Preview as of 2026-04-22.** | **Named as a pillar** ("Aggregation: unifying context and resolving conflicting definitions") but **no mechanism described** | Not described. "Verified" has no named verifier. | Not described | [SRC-017] |
| Google | LookML Agent (Preview); BigQuery measures (Preview) | Blog says only "automating business logic." Inputs unknown; docs unreachable. | not verified | not verified | not verified | [SRC-017] |
| Google | BigQuery Studio Gemini job-history analysis | Query history, used for cost and troubleshooting, not definitions. | No | No | No | [SRC-017] |
| Microsoft | Power BI "Prep data for AI": AI instructions, verified answers, "Approved for Copilot" | **User-supplied.** Copilot suggests trigger phrases from the chosen visual, not from usage. | No; docs only warn that conflicting instructions confuse the model | Checkbox-grade. No rationale field. | **Explicitly none**: verified answer visuals "aren't synced" to the report | [SRC-019] |
| Microsoft | Fabric data agents; "Build Agent with AI" (Preview) | User-supplied example queries (up to 100 per source); AI recommendations are **schema- and conversation-based**, not query logs. | No | Draft/publish, Git versioning. No rationale. | "Periodic review" recommended; consumer feedback surfaced (Preview, Sep 2026) | [SRC-020] |
| Microsoft | **Fabric IQ ontology (Preview)** | **Generated from existing Power BI semantic models** (DAX measures carried as metrics) or RDF/OWL import. | Claims "reduced duplication and inconsistent definitions"; no detection mechanism | **"Proposal-first" model**: agent proposes, human applies. Named versions record date, creator, description. Closest verified thing to a ruling record. No rationale per ruling. | No | [SRC-021] |
| Microsoft | Endorsement (Promoted/Certified); Purview glossary | Hand-authored. Default auto semantic models were **discontinued Sep 2025.** | Duplicate-name warning only | Certifier designation; draft/publish/expire. No rationale. | No revocation on drift | [SRC-021] |
| AWS | Quick Sight Topics, dataset enrichment, custom instructions | **User-supplied or imported from dbt/Databricks/Alation files.** Docs state the baseline model sees "only column names and data types." Metrics are natural-language rules. | No; "avoid contradictions" is a best-practice line | Publish/share only | No | [SRC-022] |
| AWS | DataZone / SageMaker Catalog AI recommendations | **Schema and metadata.** Suggests names, descriptions, and existing glossary terms. No query history. | No | Accept/Reject/Edit per item; unreviewed suggestions excluded from publish. Most mature approval flow verified, still no rationale. | No | [SRC-022] |

Implication, revised after Snowflake and Databricks: **part B from query
history is a shipped platform feature, not a gap.** Snowflake Autopilot and
Databricks Genie both mine the warehouse's own query history to propose
relationships, example queries, and (Databricks, from author feedback)
measures and filters. Google has announced the same in Preview with conflict
resolution named as a pillar. Both shipped systems stop at the same place:
proposals are accepted or rejected per item, the SQL is not editable before
acceptance, no reason is recorded, and nothing compares two high-support
definitions of the same measure or re-checks an approved one against later
usage. Snowflake's `verified_by` field and Microsoft's Fabric IQ versioned
checkpoints are the closest verified things to a ruling record; neither
carries rationale or outranks frequency.

Part E has a shipped neighbour: Databricks Genie benchmarks score answers
against gold SQL by result-set equality. That validates the agent's output,
not the induced definition against the usage it was induced from, and the
benchmarks are hand-written. It is still the closest thing verified to the
Tier 3 harness, and the project should say so rather than claim executable
validation is novel in itself.

Not reached: Euno, Alation, Select Star, Cube, AtScale, Honeydew, Zenlytic,
Push.ai, Malloy, Kyvos, Google docs pages (LookML Agent inputs), Redshift
generative SQL, illumex's own site (DNS failure from this network), and all
academic sources. Those rows below remain unverified.

## 1. Pre-LLM academic precedent

| ID | Work (recalled) | Part | What it did | What it did not do | Status |
|---|---|---|---|---|---|
| PA-01 | Elmeleegy, Ouzzani, Elmagarmid, *Usage-Based Schema Matching*, ICDE 2008 | A | Used query logs (which columns are joined, compared, co-occur) as evidence for schema matching. Direct ancestor of "the corpus is labelled assertions." | Matching only. No metric induction, no conflicts, no human loop. | **verified 2026-10-21, [SRC-040]** |
| PA-02 | Jain, Moritz, Halperin, Howe, Lazowska, *SQLShare: Results from a Multi-Year SQL-as-a-Service Experiment*, SIGMOD 2016 | A | Empirical study of real analyst SQL; what people actually write versus benchmark assumptions. | Descriptive study, no induction. | unverified |
| PA-03 | Jain, Yan, Cruanes, Howe, *Query2Vec*, arXiv 2018 | A/B | Embeddings over SQL workloads for workload summarisation and similarity. Precedent for treating the workload as a corpus. | No semantic layer output, no validation. | unverified |
| PA-04 | Khoussainova, Kwon, Balazinska, Suciu, *SnipSuggest*, PVLDB 2010 | A | Mined query logs to recommend SQL fragments (joins, predicates) by co-occurrence. Closest pre-LLM precedent for "which filters travel together." | Autocomplete, not governance. | **verified 2026-10-21, [SRC-044]; year corrected from 2011 to 2010** |
| PA-05 | Yang, Procopiuc, Srivastava, *Summarizing Relational Databases*, VLDB 2009 | B | Schema summarisation weighted by query-log usage; which tables matter. | Importance ranking, not definitions. | unverified |
| PA-06 | Golfarelli, Rizzi et al., OLAP query-log mining and session similarity, 2011-2014 | A/B | Mined OLAP logs for user preferences and recurring analytical patterns. Grain and dimension precedent. | Recommendation focus. | unverified |
| PA-07 | Halevy, Korn, Noy, Olston, Polyzotis, Roy, Whang, *Goods: Organizing Google's Datasets*, SIGMOD 2016 | A/B | Post-hoc inference of dataset metadata, provenance, and schema from logs and content at Google scale, with no authoring step. Canonical "nobody wrote it down, recover it anyway" paper. | Dataset-level metadata, not metric semantics. No normative layer. | **verified 2026-10-21, [SRC-041]** |
| PA-08 | Taheriyan, Knoblock, Szekely, Ambite, *Learning the Semantics of Structured Data Sources* (Karma), JWS 2016 and ISWC prior | B | Learned semantic models of new sources from previously modelled ones. Induction of semantics, human-corrected. | Ontology mapping, not SQL usage; no conflicts. | unverified |
| PA-09 | Hainaut et al., database reverse engineering / DB-MAIN, 1990s-2000s; Premerlani & Blaha, CACM 1994 | A/B | Recover conceptual schema from physical schema plus program code. Treats code as encoding intent. Foundation for "stored procedures are part of the corpus." | Structural, not analytical semantics. | unverified |
| PA-10 | Sneed, *Extracting Business Logic from Existing COBOL Programs*, IWPC 2001; Huang et al., *Business Rule Extraction from Legacy Code*, COMPSAC 1996 | A | Business-rule extraction from legacy code. The code-side version of the premise. | Migration-oriented, no governance artefact. | unverified |
| PA-11 | Rostin et al., *A Machine Learning Approach to Foreign Key Discovery*, WebDB 2009; Zhang et al., *On Multi-Column Foreign Key Discovery*, VLDB 2010 | B | Join-path discovery from data. Complements join discovery from usage. | Data-driven, not usage-driven. | unverified |
| PA-12 | Sherlock (KDD 2019), Sato (VLDB 2020), DODUO (SIGMOD 2022) | B | Semantic column-type detection from content. | Content signal only, no usage, no metrics. | unverified |
| PA-13 | Spanos, Stavrou, Mitrou, *Bringing Relational Databases into the Semantic Web: A Survey*, SWJ 2012; Sequeda, Arenas, Miranker, WWW 2012 | B | Ontology learning and direct mapping from relational schemas. | Schema-only; usage ignored. | unverified |
| PA-14 | Rozinat & van der Aalst, *Conformance checking of processes based on monitoring real behavior*, Information Systems 2008 (van der Aalst, *Process Mining*, for the field) | C analog | Discover the real process from event logs, then check conformance against the normative model. Structurally the same descriptive-vs-normative split as Stage 4c. | Different object (processes, not metrics). Cite as analogy only. | **verified 2026-10-21, [SRC-043]** |
| PA-15 | Halevy, Norvig, Pereira, *The Unreasonable Effectiveness of Data*, IEEE Intelligent Systems 2009 | A | Canonical citation for "meaning is recoverable from enough usage." Supports the Premise section's distributional-semantics analogy. | Not about enterprises. | **verified 2026-10-21, [SRC-042]** |

## 2. LLM-era academic and industrial research

| ID | Work (recalled) | Part | What it did | Gap vs thesis | Status |
|---|---|---|---|---|---|
| PA-20 | Sequeda, Allemang, Jacob, *A Benchmark to Understand the Role of Knowledge Graphs on LLM Accuracy for Enterprise SQL Questions*, arXiv 2311.07509, 2023 | E | Measured GPT-4 zero-shot text-to-SQL accuracy with and without an ontology/knowledge graph over an insurance schema: **16% on the raw database, 54% over the knowledge graph**. The closest published version of the Tier 3 experiment. | Ontology was hand-authored, not induced. No conflicts, no ruling store. | **verified 2026-10-21, numbers exact, [SRC-035]** |
| PA-21 | BIRD (Li et al., NeurIPS 2023, arXiv 2305.03111); Spider 2.0 (Lei et al., ICLR 2025 oral, arXiv 2411.07763); BEAVER (Chen et al., arXiv 2409.02038, v3 2026); KaggleDBQA (ACL 2021) | E | Benchmarks. BIRD names "external knowledge between NL questions and database contents" as a challenge (best model 40.08% vs human 92.96%). Spider 2.0: enterprise workflows, 21.3% solved vs 91.2% on Spider 1.0. BEAVER: private warehouses, 10.8% with GPT-5.2, 30.1% with oracle sub-task hints, so the bottleneck is domain knowledge. | None induce the knowledge; they supply it. | **BIRD, Spider 2.0, BEAVER verified 2026-10-21 [SRC-036], [SRC-037], [SRC-038]; KaggleDBQA unverified** |
| PA-22 | Uber QueryGPT engineering blog, 2024 | B | Text-to-SQL with curated "workspaces" and sample SQL as context. | Curation by humans, not induction. | unverified |
| PA-23 | Pinterest text-to-SQL engineering blog, 2024 | A/B | Used historical query logs to select tables and summarise them for the model. Closest big-tech example of usage-as-context. | Table selection only; no metric definitions, no governance. | unverified |
| PA-24 | TAG / LOTUS semantic operators (Berkeley, 2024) | adjacent | LLM operators over tables. | Not about semantics recovery. Low priority. | unverified |
| PA-25 | LLM business-rule extraction from COBOL / stored procedures, multiple arXiv 2024-2026; IBM watsonx Code Assistant for Z | A | Code-side extraction of business logic with LLMs. | Migration framing; output is documentation, not governed memory. | unverified |
| PA-26 | Uber uMetric, *The Journey Towards Metric Standardization* (2021-01-12); Airbnb Minerva (2021); LinkedIn Unified Metrics Platform (2019) blog series | C | Each was motivated by the same disease: the same named metric computed differently across teams. Uber: "multiple versions of metrics defined or generated in different channels for the same business logic"; "Shopping Session" showed 6.53M in one tool and 6.20M in another for the same city and period, traced to outdated filters. All three cured it by authoring a certified metric store. | **They solved C by fiat, not by detection.** Nobody published the "discover the conflicts from usage" step. Strong framing material for Slide 3 and the paper. | **Uber verified 2026-10-21, [SRC-039]. Airbnb (Medium returned 403) and LinkedIn (URL now 404) not reached from this network; cite Uber only** |

## 3. Vendors and products (highest priority to verify)

| ID | Vendor / feature (recalled) | Induction source | C conflicts | D ruling + rationale | Drift | Status |
|---|---|---|---|---|---|---|
| PA-30 | Snowflake Semantic View Autopilot; Cortex Analyst verified query repository | **Query history plus schema, sample values, example SQL, Tableau and Power BI files.** | per-view structural validation only | accept/reject; `verified_by` name, no rationale | no | **verified, see section 0** |
| PA-31 | Databricks Genie Agents, Unity Catalog metric views, Genie benchmarks | **Popular workspace queries mined automatically**, plus author feedback and UC keys. Metric views authored. | prose guidance only | accept/reject dialog, no rationale | monitoring tab only | **verified, see section 0** |
| PA-32 | dbt Wizard / Copilot semantic model generation; MetricFlow | dbt model code, not warehouse query history. | name uniqueness only | diff accept/reject, no audit log | no | **verified, see section 0** |
| PA-33 | Google Knowledge Catalog; LookML Agent; BigQuery Conversational Analytics | **Knowledge Catalog (Preview) claims query-log and BI-model mining.** Looker and Conversational Analytics consume authored context. | Knowledge Catalog names it, no mechanism | no | no | **verified at blog level, see section 0**; docs pages still unreached |
| PA-34 | Microsoft Fabric IQ ontology, data agents, Power BI Prep data for AI, Purview | Fabric IQ: existing Power BI semantic models. Everything else user-supplied or schema. | duplicate-name only | proposal-first, versioned; no rationale | explicitly none for verified answers | **verified, see section 0** |
| PA-35 | Alation (origin: query-log mining for popularity, "Behavioral Analysis Engine") | Query history, for popularity and lineage. **Closest living precedent for A.** | no | stewardship workflow, yes | partial | unverified |
| PA-36 | Select Star, Secoda, DataHub, OpenMetadata | Query-log lineage and popularity. | no | ownership, light | no | unverified |
| PA-37 | illumex ("Generative Semantic Fabric") | Marketing says "organizational corpus of knowledge"; inputs not enumerated on pages reached. **Vendor site unreachable; check docs for whether "usage" means query logs.** | claims conflict quantification and auto-reconciliation, no mechanism shown | not described | not described | **partially verified at marketing level, see section 0**; docs still unreached |
| PA-38 | Euno.ai | Mines Looker and dbt lineage to consolidate semantic layers. Close to B for BI-emitted semantics. | duplicate detection, claimed | not known | not known | unverified |
| PA-39 | AtScale auto-modelling | Schema plus BI usage, claimed. | no | no | no | unverified |
| PA-40 | Datalogz | BI sprawl and duplicate-dashboard detection. Partial C over reports, not SQL. | yes, dashboards | no | no | unverified |
| PA-41 | Timbr.ai, Stardog, data.world AI Context Engine | Ontology layers over SQL; authored, not induced. Sequeda's benchmark (PA-20) came out of data.world. | no | no | no | unverified |
| PA-42 | Palantir Foundry Ontology / AIP | Authored. The "back room" version of the idea, and the one CTOs have actually bought. Critique: it is hand-modelled and platform-bound. | no | yes, in-platform | no | unverified |
| PA-43 | Honeydew, Cube, Omni, Zenlytic, Push.ai, Lightdash, Steep | Authored semantic layers; Omni promotes workbook SQL into the model, a small instance of usage-to-definition. | no | no | no | unverified |
| PA-44 | Waii, Wren AI, Vanna, Dot, TextQL, Wisdom AI | Text-to-SQL with retrieval over past SQL and docs. Use history as few-shot context, not as induction. | no | no | no | unverified |
| PA-45 | Teradata: teradata-mcp-server semantic layer, Enterprise MCP, Tera Context Engine, platform agents | **Hand-authored YAML cubes and glossary**; Agent Skill drafts from documentation. DBQL mined for DBA operations and tuning proposals only. Tera Context Engine sources unstated, early access. | no | DBA approve/reject on tuning proposals; nothing for definitions | workload drift only | **verified, see section 0** |

## 4. Analyst and thought-leader vocabulary

| ID | Source (recalled) | Frames knowledge as | Status |
|---|---|---|---|
| PA-50 | Gartner, *Market Guide for Active Metadata Management*, 2021 onward | **Harvested from usage, logs, lineage.** Closest analyst vocabulary to the Premise. | unverified |
| PA-51 | Gartner, semantic layer and metrics store guides, 2024-2026 | Authored. | unverified |
| PA-52 | Gartner, "digital twin of an organization" | Authored model of the enterprise. | unverified |
| PA-53 | Benn Stancil essays on the metrics layer (benn.substack.com) | Has argued definitions should emerge from how people already query. Find the specific posts. | unverified |
| PA-54 | Tristan Handy, Analytics Engineering Roundup | Define-once-in-dbt; the authored position. | unverified |
| PA-55 | Juan Sequeda, data.world, knowledge graphs plus LLMs | Authored ontology, measured lift. | unverified |
| PA-56 | VC essays 2024-2026 on "context layer", "semantic layer for agents", "enterprise context graph" | Mostly authored infrastructure; some gesture at mining. | unverified |

## 5. Working verdict (to be revised after verification)

**Has nobody looked into this?** Every component has been looked into, some
for thirty years. What has not been assembled, as far as recall goes, is the
loop: induce from usage, surface where usage disagrees with itself, get a
human ruling with rationale, ledger it so it outranks frequency, validate by
execution, and publish into interchange formats.

**Who is in the back room, and what are they saying?** Three conversations
are happening, under three vocabularies, and they are not talking to each
other:

1. **Active metadata / catalog people** (Alation, Select Star, Gartner's
   active-metadata framing) mine query logs. They stop at popularity, lineage,
   and ownership. They do not induce definitions.
2. **Semantic layer / metric store people** (dbt, Cube, AtScale, Minerva,
   uMetric, Palantir Ontology) solve metric inconsistency by authoring a
   certified store. They assume someone will write the definitions, and they
   know from experience that someone mostly does not.
3. **Text-to-SQL / agent people** (Snowflake, Databricks, Google, the
   startups) need a semantic layer under the model and **now generate one
   from query history** (Snowflake Autopilot, Databricks Genie, verified
   2026-10-12; Google Knowledge Catalog in Preview). This group has occupied
   part B. What they ship is per-item accept/reject with no rationale, no
   conflict mechanism, and no re-check against later usage.

The project's language ("decode the enterprise corpus", "SQL2Text") is not
how any of the three groups talk. To be found by them, the docs should map
the thesis onto their terms: active metadata that produces definitions,
not just lineage; a metric store that is seeded from evidence, not authored
from scratch; the context layer text-to-SQL needs, induced rather than
written.

**What is genuinely unoccupied, verified:** part C as a product (two
high-support definitions of one measure surfaced as a conflict, with the
evidence for each), part D as a durable, ledgered ruling store with rationale
that outranks frequency, and drift detection against the approved definition.
Part E has a shipped neighbour in Genie benchmarks and should be framed as
"validate the induced definition against the usage it came from," which no
one verified does, rather than "execute SQL to check an answer," which
Databricks does. The combination is the wedge. Part B alone is not, and the
deck's Slide 1 has been reworded to stop implying it is.

**What would change this verdict:** a shipped conflict mechanism from Google
Knowledge Catalog, Snowflake, or Databricks that compares definitions rather
than names, or a ruling record with rationale that the agent retrieves in
preference to frequency. Databricks is closest: it already mines author
feedback into measure suggestions and has a benchmark harness. If Genie adds
"these two trusted assets disagree" and a reason field on acceptance, parts
C and D become platform features and the project's remaining ground is the
cross-platform ledger and drift loop. None of the verified products describe
any of that today, so the positioning should sit on the governance loop now.
