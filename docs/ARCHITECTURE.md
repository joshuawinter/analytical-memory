# Decoding the Enterprise Corpus

### Enterprise analytical memory from the systems that already encode it

## Premise

An enterprise has been writing a corpus about itself for thirty years without
recognizing it as one. Every schema migration, every stored procedure written at
2am to handle an edge case, every Slack thread settling what a term means, every
query an analyst composed — the institutional knowledge is *already encoded* in
the systems. It accumulated as exhaust from operations rather than as a record
anyone intended to keep, so it was never treated as a corpus and never read back.

The goal is to decode it and make it usable — in the same sense that a
general-purpose language model is usable as a curator of domain knowledge built
from centuries of written and spoken word. Nobody hand-curated an ontology for
that model either. The structure came out of the corpus, because usage encodes
meaning and enough usage makes meaning recoverable.

**Where the analogy holds:** meaning is recoverable from usage. Nobody needs to
have written the definition down for it to be present in the corpus.

A single artifact — one query, one stored procedure — is just syntax:
structurally valid, semantically empty, the alphabet before it spells
anything. Meaning shows up only at the level of the corpus, in what recurs:
which filters travel together often enough to be a rule rather than a choice,
which join path repeats, which literal value encodes a real category. That is
the same principle distributional semantics runs on — you know a word by the
company it keeps — applied to SQL first because TPC-DS supplied ground truth
to check the method against, not because SQL is special. Every later tranche
of this corpus (execution logs, human channels, code and stored procs,
integration workflows — see "Corpus expansion" below) is the same
alphabet-to-language transformation run on a different substrate.

**Where it strains, and why it shapes the design:**

- *Sparse, not redundant.* A general corpus expresses each concept thousands of
  ways across independent sources; noise averages out. An enterprise has one
  expression of most concepts and occasionally two that disagree. You cannot
  average your way to an answer at n=2 — hence the arbitration loop (stage 4c),
  which breaks the tie once and never asks again.
- *Normative, not just descriptive.* Natural language is largely descriptive and
  consensus emerges from use. Enterprise knowledge is substantially normative:
  someone with authority decided, and the decision binds whether or not the
  corpus reflects it consistently. That layer must be *captured*, not inferred —
  which is why the resolution store is a permanent component and not scaffolding
  to be removed later.

The urgency: this knowledge currently walks out the door when people retire. It
is sitting in the systems, unread.

## Thesis

A hand-built semantic layer encodes what the business *says* it means. A query
corpus encodes what the business *actually* means — every join an analyst chose,
every filter they applied, every column they summed is a labelled assertion
about semantics. The corpus is unexploited training signal.

**Initial claim tested:** a useful semantic layer can be induced from SQL alone,
at fidelity sufficient to answer a bounded set of business questions correctly.

**Target system:** an enterprise analytical memory and reasoning system that
learns business language, intent, data structures, metric definitions, and
evidence from decades of system usage, then uses that memory to answer
questions, investigate results, and discover patterns and opportunities.

SQL induction is therefore the first evidence-acquisition substrate, not the
finished product. TPC-H and TPC-DS are calibration corpora: they provide a
cheap, executable environment for testing extraction, metric induction,
validation, and safety boundaries before moving to richer enterprise evidence.

### Product goals

The long-term platform has three goals:

1. Provide a corporate-owned analytical memory and reasoning system that the
    organization's most capable thinkers and agents can use to answer corporate
    questions and solve corporate problems.
2. Demonstrate the concept through a working, buyer-facing MVP whose claims are
    supported by evidence, validation, and a focused domain evaluation.
3. Establish a credible path to commercial adoption and continued product
    leadership without confusing the product goal with any particular employment
    or transaction outcome.

The platform leverages existing knowledge investments and infrastructure to
discover the enterprise's emergent operational business model. The initial
target is not to eliminate human authority; it is to concentrate expert
attention on ambiguity, policy, and high-impact decisions while the agent
absorbs repeatable analytical interpretation over time.

### Resource and cost constraints

The first MVP is deliberately local-first. Deterministic generation, DuckDB,
profiling, SQL compilation, validation, labeling, and investigation execution
should not require an external model call. Target API spend for the first
meaningful experiment is `$5–$15`, with a preferred ceiling of `$25`; do not
expand toward `$100+` without reviewing results and value first.

Use the local CUDA/GPU environment only where it reduces cost or materially
improves the experiment: embeddings, retrieval/reranking, batch paraphrase
generation, small-model inference, or synthetic-data generation. Keep SQL
parsing, profiling, and deterministic validation on the CPU. Cache prompts and
responses, keep contexts compact, and author evaluation truth locally.

### Focused MVP domain

The first enterprise-like extension is a narrow order-to-cash and fulfillment
domain, not a full ERP simulator:

```text
customer -> sales order -> order line -> inventory reservation
          -> shipment -> invoice -> payment -> return/cancellation
```

The first investigation is: **Why did on-time-in-full fulfillment decline this
month?** Metrics include order volume, ordered quantity, late shipment rate,
stockout rate, and supplier delay rate. Synthetic or sanitized events provide
hidden evaluation truth, while the existing TPC-H pipeline remains the
mechanics and regression scaffold.

### Expert feedback requirement

The product requirement is low-friction expert feedback that improves the
corporate agent. A card queue, table, swipe gesture, or other interaction is an
implementation option, not a requirement inferred from metaphor. The stable
contract is:

```text
agent proposes evidence-backed interpretation
  -> expert approves, rejects, corrects, or clarifies
  -> decision and rationale become corporate memory
  -> later retrieval and investigation improve
```

This is human-guided active learning over enterprise semantic and operational
hypotheses. It should not be described as a commitment to a specific gesture or
frontend pattern until validated with users.

**Second output, same pipeline.** Where induction finds two high-support
definitions for the same measure at the same grain, it has located a point where
the enterprise disagrees with itself. That falls out of stage 3 for free. Most
systems discard it as noise; here it is captured, classified, routed to a human,
and the ruling retained. Over time the accumulated rulings become the normative
governance artifact nobody ever gets around to authoring — produced as a side
effect of people asking ordinary questions.

Induction is descriptive: it learns what people *do*, including what they do
wrong. Some definitions are normative and cannot be induced at all (revenue
recognition is imposed, not emergent). The resolution store is where the
normative layer lives.

## Why TPC-DS is the right substrate

It is the only public corpus with all four artifacts aligned:

| Artifact | Role in the PoC |
|---|---|
| Schema DDL (24 tables, snowflake) | structural ground truth |
| 99 query templates | the induction corpus |
| Published business descriptions | semantic ground truth |
| Reference answer sets | **executable** ground truth |

That last row is what makes this a real experiment rather than a demo. You are
not asking an LLM to grade its own homework — you compile the induced layer back
to SQL and check result-set equality against the reference answers.

TPC-H (22 queries, 8 tables) is the smoke test. Start there.

TPC-DS can be seeded locally with the DuckDB extension at a small scale:

```text
.venv/Scripts/python.exe scripts/fetch_tpcds.py --scale 0.01 --no-answers
```

This produces the 24-table schema and 99 query templates under `data/tpcds/`.
Reference answers can be generated later with the same command without
`--no-answers`; extraction does not require executing the answer workload.

For the executable TPC-H check, generate matching persistent data and answers,
then run the validation harness:

```text
.venv/Scripts/python.exe scripts/fetch_tpch.py --scale 0.01 --database data/tpch/tpch.duckdb
```

The current corpus validates all 22 TPC-H queries against their regenerated
answers. The database and answer files are intentionally generated artifacts;
the fetch scripts use quoted CSV output and preserve SQL `NULL` values.

### Two corpus modalities

TPC-H and TPC-DS are analytical corpora: their primary evidence is SQL that
computes results. TPC-DI is an integration corpus: its primary evidence is a
replayable source-to-target workflow, including mappings, key resolution,
history policy, batches, rejects, and target row versions. TPC-DI therefore
uses a parallel integration IR rather than being forced into `QueryFacts`.

The modalities share provenance, expression lineage, conflict resolution, and
validation infrastructure. They do not share the same semantic unit:

| Modality | Semantic unit | Primary oracle |
|---|---|---|
| TPC-H / TPC-DS | Query block and metric signature | Result-set equivalence |
| TPC-DI | Mapping, batch, and target row version | Replayable target-state equivalence |

The integration IR models `MappingRule`, `BusinessKeyMapping`,
`TemporalPolicy`, `LoadBatch`, `DataQualityOutcome`, and `TargetRowVersion`.
These preserve transformation intent instead of treating ETL lookups as
business joins or data-quality filters as user predicates.

---

## Functional architecture

```
                    ┌──────────────────────────────┐
  schema DDL ──────▶│  1. INGEST & NORMALIZE       │
  99 queries ──────▶│     sqlglot → typed AST      │
                    └──────────────┬───────────────┘
                                   │  qualified ASTs
                    ┌──────────────▼───────────────┐
                    │  2. PER-QUERY EXTRACTION     │
                    │     join edges, predicates,  │
                    │     aggregations, grains     │
                    └──────────────┬───────────────┘
                                   │  QueryFacts[]
                    ┌──────────────▼───────────────┐
                    │  3. CORPUS AGGREGATION       │
                    │     frequency-weighted       │
                    │     role & path statistics   │
                    └──────────────┬───────────────┘
                                   │  CorpusStats
                    ┌──────────────▼───────────────┐
                    │  4. INDUCTION                │
                    │     entities, dimensions,    │
                    │     measures, metrics, paths │
                    └──────┬───────────────┬───────┘
                           │               │  competing signatures
       SemanticLayer       │               ▼
       (structural)        │   ┌───────────────────────────┐
                           │   │  4b. CONFLICT DETECTION   │
                           │   │      classify + rank      │
                           │   └───────────┬───────────────┘
                           │               │  material forks only
                           │   ┌───────────▼───────────────┐
                           │   │  4c. ROUTING & RESOLUTION │
                           │   │      L1 analyst / L2 exec │
                           │   │      → resolution store   │
                           │   └───────────┬───────────────┘
                           │               │  rulings (versioned)
                    ┌──────▼───────────────▼───────┐
                    │  5. LLM NAMING PASS          │
                    │     business names + defs    │
                    └──────────────┬───────────────┘
                                   │  SemanticLayer (named, adjudicated)
                    ┌──────────────▼───────────────┐
                    │  6. VALIDATION HARNESS       │
                    │     compile → execute →      │
                    │     compare to reference     │
                    └──────────────────────────────┘
```

Stages 1–4 are deterministic. The LLM enters at stage 5, and at stage 6 only as
a *consumer* of the induced layer. Keep that boundary clean — it is what lets
you attribute failures to induction rather than to prompting.

Rulings from 4c **override frequency**. A resolved definition wins even when the
corpus majority disagrees, because the corpus records habit and the ruling
records authority.

---

## Stage 1 — Ingest & normalize

Use `sqlglot`. It parses, qualifies, and lets you walk a typed AST across
dialects. Do not write a regex SQL parser; that path ends badly.

```python
def ingest(ddl_path, query_dir):
    schema = sqlglot.parse(read(ddl_path))
    catalog = build_catalog(schema)   # table -> {col: type}, PK/FK if declared

    corpus = []
    for f in query_dir:
        ast = sqlglot.parse_one(read(f), dialect="tsql")
        ast = qualify(ast, schema=catalog)   # every col -> table.col
        ast = expand_ctes(ast)               # inline WITH, flatten subqueries
        corpus.append(Query(id=f.stem, ast=ast, sql=read(f)))
    return catalog, corpus
```

`qualify` is the load-bearing call. Unqualified columns make every downstream
statistic ambiguous.

## Stage 1b — Profile & sample data

Schema and SQL reveal intended structure; data profiles reveal whether that
structure is plausible. Profile physical catalog tables before induction and
capture bounded samples for inspection and materiality checks. The profile
should include row counts, null counts, distinct counts, min/max values, and
top values. Samples are queryable evidence, not semantic truth: use bounded or
masked samples in production, retain provenance, and never let a biased sample
override an explicit business ruling.

The implementation exposes this as `profile_database(connection, catalog)` and
returns `TableProfile` and `ColumnProfile` records. Full-table statistics help
identify keys, sparse dimensions, date coverage, and join fanout; samples help
inspect candidate segments and compare competing metric signatures. Stage 3
and conflict ranking may consume profiles, while Stage 4 still requires SQL
lineage and authoritative resolutions.

---

## Stage 2 — Per-query extraction

For each query, emit a `QueryFacts` record. This is pure AST walking.

Extraction preserves query scope instead of treating a nested query as part of
the outer query's semantics. CTEs, derived tables, scalar subqueries, and
`EXISTS` queries become `QueryBlock` records; outer-to-inner references become
correlation records; and `UNION`, `UNION ALL`, `INTERSECT`, and `EXCEPT` remain
explicit set-operation records. The flat fields below remain available for
backward-compatible Stage 3 statistics, while scope-aware consumers can avoid
mixing inner aggregates and predicates into outer metric signatures.

```python
@dataclass
class QueryFacts:
    query_id:     str
    tables:       set[str]
    join_edges:   list[JoinEdge]      # (left.col, right.col, join_type)
    aggregations: list[Agg]           # (func, table.col, alias)
    group_by:     list[str]           # qualified cols -> candidate grain
    predicates:   list[Predicate]     # (table.col, op, literal_or_param)
    projections:  list[str]
    order_by:     list[str]
    window_fns:   list[Window]
```

The role-assignment heuristics, in priority order:

```python
def assign_roles(facts):
    roles = defaultdict(set)

    for e in facts.join_edges:          # join keys
        roles[e.left].add(KEY)
        roles[e.right].add(KEY)

    for a in facts.aggregations:        # measures
        if a.func in {SUM, AVG, MIN, MAX, COUNT, STDDEV}:
            roles[a.column].add(MEASURE)

    for c in facts.group_by:            # dimensions
        roles[c].add(DIMENSION)

    for p in facts.predicates:
        if p.op in {EQ, IN}:            # equality filter -> dimension
            roles[p.column].add(DIMENSION)
        if p.op in {GT, LT, BETWEEN}:   # range filter -> ordered dim or measure
            roles[p.column].add(ORDERED)

    return roles
```

A column accumulates roles across the corpus. Conflicts are signal, not noise —
a column that is both MEASURE and DIMENSION is usually a genuine dual-role field
(e.g. `ss_quantity`), and the frequency ratio tells you its dominant use.

---

## Stage 3 — Corpus aggregation

Roll the per-query facts into weighted statistics.

```python
def aggregate(facts_list):
    return CorpusStats(
        # how often each join edge appears -> canonical join paths
        edge_freq      = Counter(e for f in facts_list for e in f.join_edges),

        # role distribution per column
        role_freq      = {col: Counter(roles) for col, roles in merged_roles},

        # (func, column) pairs -> candidate measures
        agg_freq       = Counter((a.func, a.column) for f in facts_list
                                                    for a in f.aggregations),

        # co-occurring group-by sets -> candidate grains
        grain_freq     = Counter(frozenset(f.group_by) for f in facts_list),

        # recurring literal filters -> candidate named segments
        pred_freq      = Counter((p.column, p.op, p.value) for f in facts_list
                                                           for p in f.predicates),
    )
```

Two derived structures matter most:

**Join graph.** Nodes are tables, edges weighted by `edge_freq`. The heavy
edges are your canonical join paths. Tables with high degree that are never
aggregated are conformed dimensions; tables that are aggregated and have many
outbound FK edges are facts.

```python
def classify_tables(stats, catalog):
    for t in catalog:
        measures_here = count_measures_in(t, stats)
        out_degree    = join_degree(t, stats)

        if measures_here > 0 and out_degree >= 2:   yield t, FACT
        elif measures_here == 0 and out_degree >= 2: yield t, CONFORMED_DIM
        elif out_degree == 1:                        yield t, DIM
        else:                                        yield t, UNKNOWN
```

**Grain.** For each fact table, the FK columns that appear in join edges define
its dimensionality; the modal `group_by` sets define the grains analysts
actually use.

---

## Stage 4 — Induction

Emit a structural semantic layer. No LLM yet.

The implementation emits `SemanticLayer` records for physical entities,
supported measures, dominant dimensions, and recurring metric candidates.
`min_support` is explicit and configurable: the TPC-H smoke test can inspect
single-observation candidates, while larger corpora can suppress noise before
the naming pass. The layer retains source query IDs, join paths, grains, and
invariant predicates so every induced object remains auditable.

When Stage 1b profiles are supplied, induction also rejects metric join paths
whose non-grain tables can fan out rows, protecting against flattened
correlated subqueries while preserving the default profile-free behavior.

```python
def induce(stats, catalog):
    layer = SemanticLayer()

    for table, kind in classify_tables(stats, catalog):
        layer.entities.add(Entity(table, kind, grain=modal_grain(table, stats)))

    # measures: (agg_func, column) above a support threshold
    for (func, col), n in stats.agg_freq.items():
        if n >= MIN_SUPPORT:
            layer.measures.add(Measure(col, func, support=n))

    # dimensions: columns whose dominant role is DIMENSION
    for col, roles in stats.role_freq.items():
        if roles.most_common(1)[0][0] == DIMENSION:
            layer.dimensions.add(Dimension(col, support=sum(roles.values())))

    # metrics: recurring (measure, join path, default filters) triples
    for sig, queries in group_by_signature(facts_list):
        if len(queries) >= MIN_SUPPORT:
            layer.metrics.add(Metric(
                measure       = sig.measure,
                join_path     = sig.path,
                default_where = invariant_predicates(queries),
                seen_in       = [q.id for q in queries],
            ))

    return layer
```

`invariant_predicates` is the subtle one: given all queries sharing a metric
signature, the predicates present in *every* one are part of the metric
definition (e.g. every revenue query excludes returns). Predicates that vary are
user-supplied filters, not definitional. **This distinction is the whole
ballgame** — it is exactly what a hand-built semantic layer encodes and what
naive text-to-SQL gets wrong.

---

## Stage 4b — Conflict detection and ranking

The implementation now compares query-level metric signatures before they are
merged into Stage 4 candidates. It emits `Conflict` records for same-grain
filter/path disagreement and labels different grains as `GRAIN_VARIATION`.
Ranking currently uses a deterministic support/divergence proxy; it must be
replaced or supplemented by execution-backed materiality once metric
compilation is available.

A conflict is two or more signatures with meaningful support, computing the same
measure at the same grain, that disagree. Detection is trivial — it is a group-by
over `stats`. **Ranking is the hard problem**, and it is where this succeeds or
fails in production.

Most divergent signatures are not disagreements. They are context: different
grain, different scope, legitimately different questions. Flood analysts with
those and the system is ignored inside a month.

```python
def detect_conflicts(layer, stats, facts_list):
    for (measure, grain), sigs in group_by_measure_and_grain(layer.metrics):
        if len(sigs) < 2:
            continue

        kind = classify_conflict(sigs)          # see below
        if kind is GRAIN_VARIATION:             # not a conflict, annotate
            layer.annotate_disambiguation(measure, sigs)
            continue

        yield Conflict(
            measure     = measure,
            grain       = grain,
            candidates  = sigs,
            kind        = kind,
            materiality = estimate_materiality(sigs),
            support     = {s.id: s.support for s in sigs},
        )
```

Classification decides *who* sees it, and must happen before routing:

| Kind | Signal | Route to |
|---|---|---|
| `GRAIN_VARIATION` | differ only by date basis, scope column, or grain | nobody — auto-disambiguate |
| `DEFINITIONAL` | differ by invariant predicate set | **L1 analyst** |
| `NORMATIVE` | differ by what counts as the business event | **L2 owner** (VP/controller) |

The L1/L2 split matters. Analysts should rule on "these differ by order date vs
ship date." They should *not* rule on whether bookings include renewals — that is
a VP call. If L1 absorbs normative disputes it lacks authority to settle, the
rulings do not stick and quietly reopen in six months. Let analysts escalate.

**Materiality is the ranking key.** A fork only matters if it produces a
materially different number on questions people actually ask:

```python
def estimate_materiality(sigs):
    # compile each candidate, execute against a sample, compare
    results = [execute(compile_to_sql(s)) for s in sigs]
    spread  = max_pairwise_divergence(results)      # relative
    reach   = sum(s.support for s in sigs)          # how many queries affected
    return spread * log1p(reach)
```

Rank the queue by materiality and cut it hard. A short queue that is always
worth reading beats a complete one nobody opens.

## Stage 4c — Routing and the resolution store

The POC resolution store is JSON-backed and versioned by `valid_from`. A
ruling requires rationale, records who made it, and can supersede an earlier
ruling. The store is deliberately replaceable; production can move it to a
transactional table without changing the conflict contract.

Every definition carries one of three states:

- **Uncontested** — single high-support signature. Use it.
- **Contested, unresolved** — multiple candidates. Never silently pick. Answer
  with the fork exposed, or refuse.
- **Contested, resolved** — a human ruled. Ruling is durable and overrides
  frequency.

```python
@dataclass
class Ruling:
    conflict_id:  str
    chosen:       SignatureId | None    # None => "both valid, disambiguate"
    rationale:    str                   # REQUIRED — see below
    generalizes:  bool                  # is this a rule, or a one-off?
    ruled_by:     Principal
    ruled_at:     datetime
    supersedes:   RulingId | None
    valid_from:   datetime              # answers before this use the prior ruling
```

Two properties are non-negotiable.

**Rulings are versioned, never fine-tuned in.** When Finance re-rules on bookings
in Q3, last quarter's answers must remain explicable under the ruling then in
force. Weights cannot do point-in-time. Keep rulings in retrievable state and
resolve them at query time against `valid_from`.

**Capture rationale, not just the verdict.** "Sales definition wins" teaches
nothing and generalizes to nothing. "These differ by grain, not definition —
both valid, disambiguate by asking which date basis" is a rule that resolves the
next thousand conflicts without a human. `rationale` and `generalizes` are what
turn a lookup table into learning. Make the field mandatory in the UI.

The L1 loop is **active learning**: humans only ever see cases the system could
not resolve, so every label lands exactly where the model is uncertain. Labels
per unit of human effort are far higher than random curation of historical logs.
This is also the answer to "where does the training data come from" — analysts
are already making these calls in Slack threads today, where the resolution dies.
You are instrumenting a judgment, not adding work.

## Stage 5 — LLM naming pass

The naming interface is provider-neutral. The default `MockNamingProvider` is
deterministic and requires no credentials, so the POC remains runnable offline.
Remote providers should read credentials from environment variables such as
`SEMANTIC_INDUCTION_API_KEY` and model selection from
`SEMANTIC_INDUCTION_MODEL`; keys do not belong in source or test fixtures.

The only generative step. Input is the structural layer plus schema context;
output is business-readable names and definitions.

```
SYSTEM: You are naming objects in a derived semantic layer. You will be given
a structural definition mined from a query corpus. Produce a business name and
a one-sentence definition. Do not invent semantics not present in the input.
Return JSON only.

USER: {
  "measure": "ss_ext_sales_price",
  "aggregation": "SUM",
  "join_path": ["store_sales", "date_dim", "store"],
  "invariant_filters": [],
  "support": 34,
  "schema_context": {...}
}
```

Constrain hard, and never let this stage add or remove structure. It renames.

---

## Stage 6 — Validation harness

The local harness executes `qNN.sql` against DuckDB and compares its result to
the matching `qNN.csv`, including column names, row counts, nulls, numeric
values, and order-insensitive row matching by default. It is intentionally
independent of the naming provider, so induction and composition failures can
be separated from model-provider failures.

The first compiler target is deliberately conservative: simple aggregate
metrics with qualified physical columns, inner join edges, grouping columns,
and rendered invariant predicates. Unsupported expression shapes raise a
compile error rather than silently changing the metric's meaning. This gives
the POC an auditable path from an induced signature back to executable SQL;
expression-tree measures and richer join semantics can be added incrementally.

Compiler coverage is recorded per metric with status, feature flags, generated
SQL, and rejection reason. Validation results also retain execution time and
row counts. Run these reports against TPC-H and TPC-DS before expanding the
compiler; unsupported-feature counts should determine implementation order.

Three tiers, weakest to strongest.

**Tier 1 — Coverage.** What fraction of the 99 queries can be expressed as a
composition of induced objects? Purely mechanical.

**Tier 2 — Semantic agreement.** Render each induced metric to English, compare
against the published business description via embedding similarity plus a
judge model. Reports whether you recovered the *meaning*.

**Tier 3 — Executable equivalence.** The real test.

```python
def tier3(layer, business_questions, reference_answers):
    results = []
    for q in business_questions:
        # the model sees ONLY the induced layer — never the original SQL
        plan = llm_compose(question=q.text, layer=layer)
        sql  = compile_to_sql(plan, catalog)

        got  = execute(sql)
        want = reference_answers[q.id]

        results.append(Result(
            q.id,
            match = frames_equal(got, want, tol=1e-6, order_insensitive=True),
            sql   = sql,
        ))
    return results
```

Report `match_rate`. Then run the control arm: same questions, same model, raw
schema only, no induced layer. **The delta between the two is your entire
finding.** Published baselines put raw-schema text-to-SQL around 50–70% on messy
enterprise data and 86–95% with a curated layer. If induction lands in the upper
band, the thesis holds.

The implementation splits this into a validated boundary: `plan.py`'s
`MetricPlan`/`resolve_plan` are what the induced-layer arm actually composes
against, so an LLM can only select a named measure and dimensions the corpus
demonstrated -- it never supplies join paths or invariant filters, and
`resolve_plan` refuses any grain the corpus never produced. `tier3.py` runs
both arms (`run_raw_schema_arm`, `run_induced_layer_arm`) through the same
`compare_sql_to_answer` comparator `validate.py` uses for saved queries, and
`Tier3Report.delta()` reports the number this section is about. Composers are
pluggable (`SqlComposer`/`PlanComposer` protocols); `MockSqlComposer` and
`MockPlanComposer` exist only to exercise the harness offline, not to
demonstrate the thesis. `scripts/run_tier3.py` wires the real
`AnthropicSqlComposer`/`AnthropicPlanComposer` pair and requires
`SEMANTIC_INDUCTION_API_KEY` to be set in the running terminal.

Tier 3 is now treated as a calibration experiment, not the product boundary.
Its result establishes that usage-derived metric structure can improve a
bounded analytical task. The next system boundary is an evidence-backed
analytical memory that stores concepts, definitions, evidence, investigations,
findings, conflicts, and human resolutions.

### Analytical memory target model

The target model stays deliberately small. It uses SKOS-like concepts for
business vocabulary and PROV-O-like provenance for evidence and accountability;
the analytical definitions and investigation records remain project-specific.

```text
BusinessConcept
    aliases, broader/narrower terms, description

MetricDefinition
    measure, entity, grain, time basis, filters, physical realization

Evidence
    source, query/report/document, observation, confidence, timestamp

Investigation
    question, interpreted intent, assumptions, plan, result, finding

Resolution
    human decision, rationale, owner, validity period, superseded definitions

ReviewTask
    target, task type, proposed interpretation, evidence, automatic checks,
    human decision, rationale, reviewer, validity period
```

The reasoning loop is:

```text
question -> retrieve concepts and evidence -> interpret intent
                 -> propose plan -> validate and execute -> explain finding
                 -> capture feedback and resolution
```

        ### Agent interface boundary

        All clients should call a client-neutral application service rather than
        reimplementing analytical logic. The current `InvestigationService` exposes:

        ```text
        search(question)
        review_items()
        investigate(question)
        record_decision(definition_id, decision, rationale, decided_by, ...)
        ```

        The browser and CLI use this boundary, and MCP is a thin adapter over the
        same service -- `record_decision` reaches the same `LabelingStore.label`
        call and the same audit ledger regardless of which client invoked it.
        Exposing approval as an MCP tool (`record_review_decision`) means an MCP
        client is capable of writing a ruling, not merely reading memory, which is
        exactly why the write boundary is enforced in the tool contract, not left
        to client discretion: the decision and rationale must originate from the
        human the client is acting for, never fabricated by the agent. MCP does
        not add an unrestricted SQL tool and does not become the source of truth --
        it is the interoperability boundary; the analytical memory, governance
        decisions, and investigation service remain the product core.

        A `.mcp.json` at the repo root registers this project's MCP server for
        Claude Code itself, and `.claude/skills/govern/` encodes the human-in-the-
        loop contract above as an explicit, reviewable instruction set -- the
        governance protocol as an artifact, not just a convention held in one
        person's head. This makes Claude Code itself a viable governance
        interface alongside the browser UI, not a replacement for the approval
        gate: the skill's entire job is refusing to approve anything the human
        did not actually decide.

        **Interface tiering is a deliberate choice, not a placeholder.** The
        primary analyst surface is chat-plus-artifacts in a browser (Claude
        Enterprise's own web/desktop client, or an equivalent), because that is
        the near-zero-friction path for corporate IT -- no new desktop binary to
        vet, no MDM policy, no standalone vendor-risk review. VS Code + Claude
        Code is the power-user "explore mode" for the minority of reviewers
        already comfortable in dev tools -- adding one more extension to an
        already-approved editor is a trivial ask compared to approving a new
        application for a broad analyst rollout. Reaching Claude Enterprise means
        this MCP server hosted somewhere network-reachable rather than spawned as
        a local stdio process, which is a real, not cosmetic, gap: it needs an
        HTTP/SSE transport (today only stdio is implemented), `decided_by` bound
        to an authenticated identity from the customer's SSO/SCIM rather than the
        free-text field it is today, and the L1/L2 authorization this section
        already assumes conceptually but does not yet enforce in code. None of
        that is required to demonstrate the interface, which this codebase
        already does locally end-to-end -- it is required to run it for more
        than one trusted person at a time.

        The MCP design rationale and source reference are recorded in the
        [MCP research note](../research/mcp.md).

Facts, interpretations, hypotheses, and human decisions remain distinct. An
induced metric is evidence-backed structure; it is not automatically a
normative business definition. Human resolutions can approve, reject, revise,
or scope that structure without erasing the original observation.

### Human review boundary

Automation verifies mechanical validity: SQL syntax, catalog references,
join-key existence, type compatibility, fanout risk, compilation, execution,
and result-set equivalence. Humans verify business meaning: concept identity,
metric definition, grain, time basis, filter semantics, evidence relevance,
conflicts, and whether a finding is actionable. The system must not ask a
reviewer to manually certify a check that deterministic code can perform.

Human review is staged rather than presented as one large form:

1. Review metric meaning and concept identity.
2. Verify grain, time basis, and filter semantics.
3. Confirm evidence relevance and resolve competing definitions.
4. Review analytical findings for plausibility, actionability, and causal
    overclaiming.

The current local labeling interface implements the first review slice for
induced metric candidates: it displays measure, grain, joins, filters,
evidence, and confidence, then records `APPROVE`, `REJECT`, or `CLARIFY` with a
rationale. Future review tasks should use the same record shape and preserve
the original evidence.

### Business language and publication boundary

The system bridges natural-language questions to physical data assets through a
governed business vocabulary. The initial seed is deliberately local and
evidence-backed: aggregate aliases observed in SQL are added as candidate
aliases for their physical measure. Reviewers can then supply a canonical
business definition and comma-separated aliases when approving a candidate.
Those enrichments are stored separately in `labels.vocabulary.json`; the
observed definition, SQL evidence, and decision rationale are never rewritten.

Vocabulary enrichments improve later retrieval, but they do not manufacture a
new physical mapping or override an approved definition without review.

The review UI and retrieval surface publish only metric definitions that the
current simple contract can state truthfully:

```text
physical measure + physical grain + flat predicates
```

It excludes query-local CTE aliases, unqualified derived expressions,
mutually-exclusive `CASE` branches, nested subqueries, and derived ranking
predicates. Such structures are valuable evidence for a future expression and
report model, but flattening them into a measure/grain/filter sentence loses
material meaning. They must remain unpublished until that richer model can
preserve their logic.

### MVP readiness

The current implementation is reusable for the first MVP because it already
provides the evidence-to-memory-to-investigation spine:

```text
SQL corpus -> induced candidates -> profile evidence -> expert resolution
           -> approved-definition retrieval -> compiled investigation
```

Reusable now: ingestion, extraction, profiling, fanout protection, metric
induction, provenance, labeling, approval gating, deterministic compilation,
local execution, result validation, and the review interface. The MVP still
needs a focused enterprise-like domain, richer non-SQL evidence, investigation
history, drift/conflict views, access controls, and a buyer-facing evaluation
report. Those are product-scope additions, not reasons to reopen the locked
TPC-H mechanics.

**Tier 4 — Conflict precision.** Hand-author query pairs against the TPC-DS
schema with known ground truth -- some encode a genuine definitional
disagreement (a recurring invariant predicate one side has and the other
doesn't), some vary only grain, one is a documented, accepted gap -- and
measure whether 4b separates them. Optimize for **precision over recall**. A
missed conflict is a wrong number someone eventually catches. A false
conflict is a VP's time, and three of those end the pilot.

The implementation is `tier4.py`'s `Tier4Scenario`/`run_tier4`, matching this
section's original formula (`precision`, `recall`, `noise_rate` against
`DEFINITIONAL`-vs-not classification). `scripts/run_tier4.py` wires three
scenarios from `data/tpcds/tier4/queries/` -- a recurring inclusion/exclusion
predicate (real conflict), a single-observation filter on a continuous
column (documented gap, not a bug: it neither recurs nor is low-cardinality,
so 4b treats it as narrowing rather than definitional), and a finer grain
(not a conflict at all). All three currently pass. It is offline and
deterministic, so it runs in the main test suite (`test_tier4.py`) rather
than needing a live model like Tier 3.

This is a first, small labeled set, not a swept evaluation -- it proves the
harness and formula work end to end and locks in the current classification
behavior as a regression guard. Expanding it (more scenarios, perturbing
real TPC-DS templates directly rather than hand-authored pairs) is the
natural next step before trusting precision/recall numbers at any scale.

### The production metric

Escalation rate over time. If rationale capture is working, the fraction of
conflicts requiring a human should decay as generalizable rules accumulate. That
decay curve is simultaneously the technical validation and the CFO pitch — it is
the only number that shows curation labor actually falling.

Plot escalations-per-thousand-queries by month, split L1 and L2. L2 should decay
faster; normative questions are finite, and once a company has ruled on bookings
it does not re-litigate quarterly.

---

## Corpus expansion — what to add, in what order

The SQL corpus tells you *what* was computed. It does not tell you *why*, and it
does not contain rulings. Both exist elsewhere in the enterprise.

This section is where the premise gets cashed out. Each source below is another
tranche of the same thirty-year corpus, encoded in a different substrate. The
ordering is by alignment difficulty, so every layer has verified ground truth
beneath it before you add the next.

**1. SQL corpus.** Self-contained, verifiable against TPC-DS. Start and stay here
until stages 1–4 are solid.

**2. Execution and planning logs.** Aligns cleanly — shares query IDs, no
resolution problem. Underrated as semantic signal: physical placement, partition
pruning, what the optimizer materialized, what got broadcast. A column that is
the partition key across every fact table is asserting it is the primary business
grain, and no glossary anywhere records that. Plan shape also disambiguates
grain: two queries with identical SQL text but different plans are usually hitting
different partitions, hence different scopes.

**3. Human channels.** Slack, tickets, PR review comments, incident postmortems.
Highest value per token, because these frequently contain rulings *already made
and since lost* — "no, use shipped date, finance ruled on that." Mining those
back-populates the resolution store with years of adjudication for free.

**4. Code and definitions.** dbt models, stored procs, Looker/Tableau field
definitions, MDM rules. These are prior attempts at the semantic layer; treat
them as high-prior candidates, not as truth. They rot, which is the premise of
this whole project.

**5. Integration workflows.** TPC-DI-style source feeds, transformation code,
batch manifests, rejects, and target snapshots are ingested through the
integration IR. Preserve source-record and batch lineage, surrogate-key
policy, effective-date behavior, and rejected-record reasons. Do not merge
these artifacts into the analytical query counters.

### The alignment caution

Linking a Slack thread to the query it concerns is a resolution problem —
timestamps, table mentions, participants, occasionally a pasted snippet. **Favor
precision heavily.** A wrongly-linked thread injects a confident, plausible,
wrong rationale into a definition, and a wrong rationale is worse than no
rationale: it will generalize, and it will propagate silently.

Require a hard anchor (pasted SQL, explicit table plus metric mention, or a
linked ticket ID) before accepting a link. Fuzzy semantic similarity alone is not
sufficient. Log the anchor type so mis-linked rationales can be retracted in bulk
later.

**Provenance filtering applies throughout.** Real logs are largely BI-tool
emissions — the same Tableau extract 40,000 times. Those carry tool conventions,
not human intent. Tag every query with its origin (human ad-hoc, scheduled job,
BI tool, application) and weight support accordingly. One analyst writing a query
by hand is worth more signal than a dashboard firing it nightly for two years.

### Metric-to-metric lineage — the dbt-path composite case

`fetch_soma.py` and `compile_soma.py` fetch and compile SOMA's B2B SaaS metrics
(github.com/Levers-Labs/SOMA-B2B-SaaS) as a second, independently-governed
ground truth — 407 metric definitions, 115 dbt models — to test whether
induction generalizes past TPC-DS. 106 of those 407 are marked `Composite`:
defined in terms of other metrics, not raw columns (`GrossDollRetn = 1 -
GrossRevChurnRt`). Nothing in Stages 1–4 can represent that today, and testing
the gap against the actual compiled SQL — not just SOMA's abstract `expression`
field — surfaced a sharper problem than "add an expression field."

**Composition is structural, not textual.** SOMA's compiled SQL never
recomputes a composite from raw tables — it selects from another metric's
materialized output:

```sql
select ..., 1 - metric_value as metric_value
from {{ ref('ga_cube_gross_revenue_churn_rate') }}
```

Every one of SOMA's 17 compiled composite models does this — a `FROM`/`JOIN`
target that resolves to another metric's output, never a base table. Same
pattern as dbt's own `ref()` DAG, LookML's `${other_view.metric}`, or a
Tableau calc-of-a-calc: any governed semantic layer with reusable metrics is
built this way, because it is the only way a revision to the base metric
propagates instead of silently forking. So Stage 1's job here is a resolution
rule — is this relation a registered `MetricDefinition`'s output? — not a new
expression parser.

**But the join predicate carries real semantics extraction currently drops.**
10 of SOMA's 17 composite queries join components at a time offset
(`tr.metric_date = cr.metric_date - interval 1 month`, `- interval 12 month`
for the annualized CMGR variants), not a same-period equi-join — and it
recurs on purpose: every churn-rate, growth-rate, and CMGR composite measures
the current period against a prior baseline. Separately, null-handling
differs per composite independent of which components are involved: the same
four revenue components (new/expansion/contraction/churned) are `INNER
JOIN`ed for `quick_ratio` (a ratio, where a missing component should exclude
the period) and `FULL OUTER JOIN` plus `coalesce(...,0)` for `net_revenue` (a
sum, where a missing component is legitimately zero). Composition semantics
live on the composite, not the components — they cannot be inferred from the
reference graph alone.

`extract.py`'s `_join_edges` cannot see either of these today: `_is_column_pair()`
requires both sides of an equality to be a bare `exp.Column`, so any predicate
with arithmetic on one side (`metric_date - interval 1 month`, or TPC-DS's
`v1.rn = v1_lag.rn + 1`) is silently skipped, not flagged. Confirmed
independently in TPC-DS: q47 and q57's `v1`/`v1_lag`/`v1_lead` period-over-period
self-join drops exactly the predicate that makes it a lag join (`rn = rn + 1`)
while keeping the surrounding dimensional predicates, so extraction records an
ordinary self-join and loses the one thing that made it a period comparison.
TPC-H never triggers this — its date logic lives entirely in `WHERE`-clause
range filters, never a join predicate — which is why the gap went unnoticed
until SOMA's composites pushed the frequency up (10/17 vs. 2/99).

**Design decision.** A two-layer metric model, not a bigger version of the
current one:

- **Atomic metrics** (301 of SOMA's 407, and everything TPC-H/TPC-DS induce
  today) keep `MetricDefinition` exactly as-is: `measure: (aggregation,
  column)` over grain/filters.
- **Composite metrics** get `component_definition_ids: tuple[str, ...]` — live
  references to other `MetricDefinition`s, never a flattened or copied
  expression, so a resolution that revises a component (e.g.
  `GrossRevChurnRt`'s grain) propagates to every composite referencing it
  instead of leaving them silently stale. The component-to-composite join
  reuses `JoinEdge`, extended with two fields: a signed `time_offset`
  (nullable interval) and a `null_handling` mode (`required` / `coalesced`).
  `composition_expression` is stored as the raw formula text (e.g. `"1 -
  {GrossRevChurnRtₜ}"`), ungoverned — narrated by Stage 5 like any other
  label, not interpreted by the induction engine.

**Deliberately out of scope for Phase 3** — no general arithmetic expression
evaluator; that is Phase 4, once the reference graph is trustworthy. Two
things do need to change now, both minimal:

- Fix `_is_column_pair()` to accept `column [+-] interval-or-literal` on one
  side, so the join edge is recorded with its offset instead of silently
  dropped. This corrects existing Stage 1/2 mechanics rather than adding new
  scope — it was already wrong for TPC-DS.
- Stage 4b gains a conflict class: **component drift** — a composite whose
  query-level grain, offset, or null-handling does not match what its
  referenced component was itself induced with. Detection is the same
  group-by-and-compare shape Stage 4b already uses for measure/grain
  disagreement, applied to a composite's declared components instead of two
  competing signatures for the same measure.

Stage 6 validation becomes recursive for composites: validate each component
independently first, then validate the composite's reference structure
(right components, right offset, right null-handling) given already-validated
components — not a bigger flat Tier 3 comparison.

## Scope lock and next build order

The following mechanics are now the locked foundation rather than an open-ended
research backlog:

- SQL parsing, scope-aware extraction, aggregation, and role assignment;
- profile-informed key and fanout checks;
- structural induction of entities, measures, dimensions, and metric signatures;
- conflict detection, resolution boundaries, plan validation, and SQL compilation;
- executable validation and the Tier 3 raw-schema comparison harness;
- TPC-H/TPC-DS fixtures and tests as regression and calibration assets.

Do not expand the TPC-H question set or build a new relational foundation model
before the analytical-memory slice below is working. New mechanics are justified
only when they support evidence, intent, investigation, or validation.

The next build order is:

1. **Memory records.** Add small records for `BusinessConcept`,
    `MetricDefinition`, `Evidence`, `Investigation`, `Finding`, and `Resolution`.
    Convert current induced metrics into evidence-backed definitions while
    retaining source query IDs, profiles, and confidence.
2. **Deterministic retrieval.** Retrieve concepts, aliases, metric signatures,
    conflicts, and evidence for a business question. Start with token and alias
    matching in SQLite or JSON; embeddings and a graph store are optional later.
3. **One analyst loop.** Implement question → intent → evidence → validated
    plan → execution → explanation → stored investigation for the existing
    supply-cost and quantity examples.
4. **Human resolution.** Add approve, reject, clarify, revise, and scope
    decisions with rationale, owner, timestamp, and validity period.
5. **Synthetic investigation corpus.** Generate a small coherent order-to-cash
    and inventory world with known metric definitions, ambiguous questions,
    controlled conflicts, anomalies, and expected human decisions. Use Faker for
    leaf values, not for process logic.
6. **Discovery.** Add one evidence-backed anomaly or trend investigation. Every
    finding must cite the metric definition, data evidence, assumptions, and
    validation status.
7. **Corpus expansion.** Add execution logs, reports, definitions, and human
    channels only after the memory and investigation model works on the controlled
    corpus. Use hard anchors and provenance filtering when aligning those sources.

## Where this will actually hurt

- **Conflict ranking, not detection.** Detection is a group-by. Separating
  material disagreement from benign grain variation is the actual research
  problem, and the one that determines whether anyone keeps using this.
- **Machine-generated queries.** Real logs are ~90% BI-tool extracts carrying
  tool conventions, not analyst intent. Provenance filtering is mandatory, not
  a refinement.
- **Grain conflation.** Two queries with the same measure at different grains
  are different metrics. Get this wrong and every number is subtly incorrect —
  and it surfaces as a phantom conflict in 4b, poisoning the queue.
- **Rationale quality.** The whole learning loop depends on analysts writing
  generalizable reasons rather than verdicts. This is a UI and incentive
  problem more than a technical one, and it is the most likely silent failure.
- **Correlated subqueries and windows.** TPC-DS is full of them; the flattening
  in stage 1 must not silently drop semantics.
- **Support thresholds.** Too high and you miss real metrics; too low and you
  induce noise. Make `MIN_SUPPORT` a swept parameter and report sensitivity.

## What this does not eliminate

Worth stating plainly, because the pitch will overreach on its own.

- **Access control.** Definitions can be induced; entitlements cannot be. Row
  and column security stays in the warehouse and becomes *more* load-bearing,
  since the model now composes queries no one reviewed in advance.
- **Lineage and audit.** Output must remain an auditable query against source
  rows. "The model said so" does not survive a regulator.
- **Arbitration.** Governance is partly documentation labor, which this
  automates, and partly authority, which it does not. The target is stewardship
  as exception handling — humans adjudicate the contested few percent instead
  of authoring everything. Large reduction, not zero.

## Stack & Standards Adoption

Rather than reinventing established plumbing, the system leverages established open-source projects and industry standards:

- **Parsing & Qualification:** `sqlglot` (typed ASTs, dialect qualification, CTE expansion).
- **Relational Execution & Profiling:** `duckdb` (vectorized local engine, data profiling, TPC-H/TPC-DS generators).
- **Semantic Model Output:** `Apache Ossie` format (vendor-neutral YAML specification for datasets, metrics, and relationships).
- **Agent Protocol:** `Anthropic Model Context Protocol (MCP)` (standard agent tools and resources over JSON-RPC stdio).
- **Data Structures:** Standard library dataclasses and `pydantic` for serialization.
- **Testing & Verification:** `pytest` (offline test harness and ground-truth validation).

## Research record

Marketplace, competitor, and first-principles analysis is maintained in the
[research index](../research/README.md). Research notes use stable source IDs
and normally record a concise summary plus a source link; local source files
are exceptions used when offline extraction or repeatable document analysis is
needed.
