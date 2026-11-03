# Rulings Outrank Frequency

## Governing induced metric definitions with an append-only analytical memory

**Josh Parsons** -- github.com/joshuawinter/analytical-memory
Draft v0.1, 2026-10-21. Technical report. Every number in this document is
reproducible from the repository at the commit named in Section 8; every
external claim carries a source id resolved in Section 9.

---

### Abstract

Data warehouses now induce semantic layers from their own query history.
Snowflake, Databricks, and Google ship it. What they ship stops at the same
place: a proposal you accept or reject per item, with no record of why, no
comparison between two definitions of the same measure, and no re-check of an
approved definition against what people query next. This report describes a
self-hosted analytical memory that supplies the missing loop: surface rival
definitions as a fork, require a dated human ruling with a rationale, store
every ruling and memory entry as an immutable, content-addressed version
chained into one auditable ledger, and answer questions only from the ruling
in force at the moment asked. Two offline, deterministic harnesses measure the
two claims that matter. Tier 5 builds a corpus in which ten of thirteen
analyst queries encode the wrong definition of revenue and shows that the
system refuses to answer until a human rules, answers from the ruling rather
than the majority, reverts when asked as of an earlier date, and honours a
later superseding ruling with history intact. Tier 4 measures the conflict
classifier against 26 scenarios labelled by meaning rather than by the
classifier's own rules and reports 55% precision and 75% recall: the
structural heuristics over-flag scope filters, which argues for
execution-backed materiality ranking. Building Tier 5 exposed the mechanism
by which frequency wins silently in the induction path: rival signatures
were merged by predicate intersection, so no fork ever reached memory. The
repository is Apache-2.0 and runs from a clean clone with no API key.

---

## 1. The problem, in one number

In January 2021 Uber's data platform team described why they built a metrics
platform. The same business metric, "Shopping Session", read 6.53 million in
one tool and 6.20 million in another for the same city and time range. The
cause was that one tool carried outdated filters. Their diagnosis: "multiple
versions of metrics defined or generated in different channels for the same
business logic" [SRC-039]. Their cure was a certified store with a "strictly
ONE to ONE mapping" between a metric and its logic.

That cure is authored. Someone writes the definitions down, and the platform
enforces the one that was written. Airbnb and LinkedIn published the same
story in the same years. None of them published the step before: discovering
from usage that two definitions were in circulation, and recording who
settled it and why.

Five years on, the warehouses have taken over the writing-down. Snowflake's
Semantic View Autopilot will "surface historical SQL queries as suggestions to
the semantic view" [SRC-023]. Databricks Genie "automatically searches for
relevant popular workspace queries associated with those assets" and turns
author feedback into suggested measures, filters, and joins [SRC-027].
Google's Knowledge Catalog, in preview, mines "structured schemas, query logs,
and BI semantic models" and names "resolving conflicting definitions" as a
pillar [SRC-017]. Induction from query history is a platform checkbox.

What each of them produces is a proposal accepted or rejected per item.
Snowflake's verified queries carry a `verified_by` name and no reason field
[SRC-024]; its validation rules are structural and per view [SRC-025].
Databricks tells authors to "review and resolve any inconsistencies" by hand
[SRC-027], and its metric views have no version history [SRC-029]. Microsoft's
Fabric IQ ontology comes closest to a ruling record, with proposal-first
review and named versions, and still has no rationale per ruling [SRC-021].
Google has named conflict resolution and described no mechanism [SRC-017].

So the Uber failure is still possible inside every one of these platforms.
Two teams' queries disagree; the induced layer absorbs whichever is more
common; a reviewer clicks accept; the reason the other team had is lost.

The gap matters more now than when Uber met it. When the analyst's surface
was SQL, a definition sat in a `WHERE` clause a colleague could read and
question, and that informal review was the control. In chat and agent
interfaces the person asking never sees the SQL, so the control disappears at
the same time as induction makes the majority definition official and agents
repeat it in every answer. Better models do not close this. Two definitions
of a measure can both be valid SQL, and which one the organization chose is a
decision, not a property of the data. As SQL generation improves, a larger
share of the remaining error is about meaning. BEAVER shows the shape:
agentic frameworks reach 10.8% on private warehouses, and 30.1% only when the
domain knowledge is supplied [SRC-038].

What this calls for is a supervised correction loop. People label only the
disputed cases, the memory keeps each label with its reason, and every later
question reads it. Nothing is retrained. Whether answer accuracy improves as
rulings accumulate is a hypothesis this report does not test (Section 2).
This report is about the loop that closes the gap, and about measuring
whether it actually closes it.

## 2. What is claimed, and what is not

The thesis has five parts. The repository's prior-art audit checked each
against primary vendor documentation [SRC-011 to SRC-034]:

```text
A. Usage encodes meaning       (a SQL corpus is labelled assertions about semantics)
B. Induce a semantic layer      (metrics, joins, filters, grains) from that corpus
C. Detect self-disagreement     (two high-support definitions of one measure)
D. Human ruling, stored         (normative layer captured, outranks frequency, ledgered)
E. Executable validation        (compile back to SQL, check result equality)
```

A is well established; B is shipping. This report does not claim either. It
takes "a usable induced layer exists" as a premise and makes three claims
about C, D, and E:

1. Rival definitions of one measure are surfaced to a human as a fork with
   the evidence for each, and nothing is answered from frequency while the
   fork is unresolved.
2. A dated ruling with a rationale is what the agent gets, at the right point
   in time, and a later ruling supersedes it without erasing it.
3. Every ruling and memory entry is an immutable, content-addressed version
   in a hash-chained ledger a person can audit with a text editor, and an
   approved definition compiles back to SQL and executes.

Two things are explicitly not claimed. The report does not measure a
downstream improvement in answer correctness on real usage; that needs a
pilot. And the conflict classifier does not yet meet the precision goal the
design set for it; Section 5.2 reports that plainly.

## 3. Related work

Three conversations touch this ground, under three vocabularies, and they do
not cite each other.

**Active metadata and catalogs** mine query logs for popularity, lineage, and
ownership. The pre-LLM literature here is direct ancestry. Elmeleegy, Ouzzani,
and Elmagarmid used query logs (which columns are joined, compared, and
co-occur) as evidence for schema matching [SRC-040]. SnipSuggest mined logs to
recommend SQL fragments by co-occurrence, the closest precedent for "which
filters travel together" [SRC-044]. Goods inferred dataset metadata and
provenance at Google scale from logs and content with no authoring step
[SRC-041]. Halevy, Norvig, and Pereira supplied the slogan that meaning is
recoverable from enough usage [SRC-042]. None of these induce metric
definitions, and none have a normative layer.

**Metric stores** solve inconsistency by authoring. Uber's uMetric is the
documented case [SRC-039]; the diagnosis is exactly part C and the cure skips
detection entirely. dbt's semantic layer validates metric-name uniqueness and
handles differing team definitions with prose guidance [SRC-014]. Databricks
metric views are authored, owner-edited, and unversioned [SRC-029].

**Text-to-SQL and agents** need a context layer under the model and now
generate one. The benchmarks establish why the layer is needed. Sequeda,
Allemang, and Jacob measured GPT-4 zero-shot on an insurance schema at 16%
accuracy over the raw database and 54% over a knowledge-graph representation
with an ontology and mappings [SRC-035]. BIRD names "external knowledge
between NL questions and database contents" as a required input and reports
its best model at 40.08% against a human 92.96% [SRC-036]. Spider 2.0 moves to
enterprise workflows over thousand-column schemas and reports 21.3% solved
against 91.2% on the original Spider [SRC-037]. BEAVER, built from private
data warehouses, reports 10.8% for agentic frameworks on GPT-5.2, rising to
30.1% when oracle answers to the domain-knowledge sub-tasks are supplied
[SRC-038]. The gap is domain knowledge, and in every case the knowledge is
supplied by hand rather than induced and governed.

**Process mining** offers the structural analogy. Rozinat and van der Aalst
discover the real process from event logs and check it for conformance
against the normative model [SRC-043]. The descriptive-versus-normative split
is the same one this design makes between what the corpus does and what the
organization has ruled; the object differs.

The verified vendor table in the repository's prior-art audit records, for
each of dbt, Snowflake, Databricks, Google, Microsoft, AWS, Teradata, and
illumex, what induction source is used, whether conflicts are compared,
whether a ruling carries a rationale, and whether drift is re-checked. Across
all of them conflict handling is name uniqueness or prose guidance, approval
is accept or reject, and nothing re-checks an approved definition against
later usage [SRC-011 to SRC-034].

## 4. Design

### 4.1 The loop

```text
usage (SQL corpus, platform-generated drafts)
  -> induce candidate definitions                  (Stage 4,  feeder)
  -> detect same-grain filter disagreement          (Stage 4b, the fork)
  -> promote rivals into memory as CONTESTED        (memory_from_layer)
  -> human rules, with rationale, dated             (Stage 4c, the ledger)
  -> answer only from the ruling in force as of t   (investigate)
  -> compile to SQL, execute, compare to truth      (Stage 6)
  -> publish approved definitions outward           (Ossie, verified queries)
```

Every definition is in one of three states. **Uncontested**: a single
high-support signature; use it. **Contested, unresolved**: rivals exist; never
pick silently; refuse with the fork exposed. **Contested, resolved**: a human
ruled; the ruling is durable and overrides frequency.

### 4.2 The ruling

A ruling records the decision, a mandatory rationale, who decided, when it was
decided, and when it takes effect (`valid_from`, optionally `valid_to`). Two
properties are non-negotiable. Rulings are versioned, never trained in: when
finance re-rules in Q3, last quarter's answers must remain explicable under
the ruling then in force, so rulings are resolved at question time against
the moment asked. And the rationale is captured, not just the verdict:
"Sales definition wins" teaches nothing, while "these differ by grain, not
definition; both valid, disambiguate by date basis" is a rule that resolves
the next thousand cases without a human.

### 4.3 The memory

The memory is a directory of small, path-addressed markdown documents with
flat front matter, each change an immutable content-addressed version,
rendered verbatim to the model. Not a vector database, not a graph store, not
rows the model never sees. Rulings and memory versions interleave in one
hash-chained, append-only ledger, so "who ruled, what they wrote, and what the
agent will now read" is a single verifiable sequence. Editing an entry outside
the ledger is detected and the projection rebuilt from objects. Deletion is a
version, not an erasure. Redaction scrubs content and keeps actor and
timestamps. Writes accept a content-hash precondition so two reviewers cannot
silently overwrite each other. The hash chain makes tampering evident; making
it impossible is a deployment matter (object-storage retention locks,
customer-managed keys, anchored ledger heads).

### 4.4 The interface boundary

A browser review interface, a command-line investigator, and a Model Context
Protocol server share one application service and one write path, so a ruling
recorded from any client lands in the same ledger. The MCP tool that records
a decision is bound by contract: the decision and rationale must originate
from the human the client acts for. An agent can search memory, list
candidates, and run approved investigations freely; it cannot approve. A
contested, unruled measure returns `NEEDS_REVIEW` with the rival definition
ids, so the client shows what has to be decided instead of a bare refusal.

## 5. Evaluation

All evidence is offline and deterministic: DuckDB in memory, no model call,
no network. The harnesses run inside the project's test suite.

### 5.1 Tier 5: rulings outrank frequency

**Method.** Build a corpus where the majority is wrong. Thirteen analyst
queries compute `SUM(ss_net_paid)` by `d_year` over TPC-DS `store_sales`
joined to `date_dim`. Ten sum every line. Three add `ss_quantity > 0`,
excluding voided and giveaway tickets that still carry an amount. A hidden
truth, authored independently of all thirteen, says the three are right: the
realistic case where most analysts copied a stale definition. Six seed rows
make the two definitions give different answers, and one year disappears
entirely under the correct one. Four scenarios run against the real
investigation path, with fixed timestamps so the run is deterministic.

**Results.**

| Scenario | Expected | Result |
|---|---|---|
| No ruling | `NEEDS_REVIEW`, both rival ids exposed | pass |
| Approve minority, reject majority, dated January | answer from minority; result equals hidden truth | pass |
| Same question asked as of December | back to `NEEDS_REVIEW` | pass |
| Reverse the ruling, dated April | majority after April; minority still between; ledger verifies; both minority versions readable | pass |
| Answers given from frequency while a ruling was in force | 0 | 0 |
| Answers given while contested with no ruling | 0 | 0 |

**What building it found.** Before this harness the claim was true by
construction and untested, and it would have failed. The induction stage
grouped a contested measure's queries together and took the *intersection*
of their predicates as the definition. The disputed filter was dropped and
the single surviving definition was, in effect, the majority's. The conflict
detector saw the rivalry, but nothing carried its candidates into the memory
the investigation path reads. There was nothing to approve or reject, and
frequency won by default. The fix promotes each rival as a separate
`CONTESTED` definition sharing a conflict id and withholds the merged one. Two
smaller gaps fell out with it: validity windows existed on the ruling record
and were ignored by the answer path, and only the head ruling was kept so
supersession had no history to read. Applied to the project's own stores,
TPC-H gains one fork with four candidates and TPC-DS ten forks with
twenty-four candidates that were previously invisible.

A further defect was caught only by running the suite from a clean clone: two
rulings recorded within one clock tick carried equal timestamps, and the
resolver returned the earlier one, resurfacing the superseded decision. Ties
now resolve to the later-recorded ruling, with a deterministic test.

### 5.2 Tier 4: conflict precision

**Method.** The classifier's job is to separate a genuine definitional
disagreement from benign scope or grain variation; flooding reviewers with
scopes is how a system like this gets ignored. Three handcrafted TPC-DS pairs
existed. A generator adds 23 scenarios in eight families, each an isolated
corpus so predicate recurrence cannot leak between them. **Labels are
semantic**: does a reviewer see two definitions of the measure (what counts
as a sale) or one definition at different scopes, grains, or wording? Seven
scenarios are labelled against what the classifier's rules are known to do,
and marked as known gaps with the reason, because the harness exists to
measure the classifier rather than to pass. The rules under test: a
predicate is candidate-defining if it recurs across queries, or if its column
has twelve or fewer distinct values (profile evidence from Stage 1b).

**Results with profile evidence, the production configuration.**

| | flagged | not flagged |
|---|---|---|
| definitional (8) | 6 | 2 |
| not definitional (15) | 5 | 10 |

Precision 55%, recall 75%, noise rate 45%. With the three handcrafted
scenarios included: 26 scenarios, precision 58%, recall 78%. Without profile
evidence every differing predicate is candidate-defining: recall 100%,
precision 47%. In both modes every misclassification is a documented known
gap; none is undocumented and none of the documented ones passes
unexpectedly.

| Family | Correct | Note |
|---|---|---|
| recurring definitional filter (`ss_quantity > 0` in two queries) | 6 / 6 | the intended positive case |
| definitional filter seen once, high-cardinality column | 0 / 2 | miss: neither rule fires |
| scope filter seen once, low-cardinality column (`d_weekend = 'Y'`) | 0 / 3 | over-flag: cardinality rule |
| scope filter recurring (`d_year = 2001` in two queries) | 0 / 2 | over-flag: recurrence rule |
| scope filter seen once, high-cardinality column | 4 / 4 | correct only with profiles |
| grain variation, cosmetic rewrites, different measure | 6 / 6 | clean negatives |

**Interpretation.** The design states "precision over recall": a missed
conflict is a wrong number someone eventually catches, a false conflict is a
VP's time, and three of those end a pilot. On this labelled set the
classifier does not meet that goal. It over-flags scopes more often than it
misses definitions. The low-cardinality rule was written for status columns
and fires on calendar and category scopes; the recurrence rule makes any
popular scope a rival definition. Both are structural: they look at the
predicate, not at what it does. A scope filter changes the number because it
changes the population; a definitional filter changes the number for the
same population. Recurrence and cardinality cannot see that distinction.
Execution can, which is what the design already names as the ranking key and
has not built: compile each rival, execute against a sample, and rank by how
materially the results diverge on the questions people ask. Section 7 takes
this up.

### 5.3 Ledger integrity and executable validation

The memory store's verification walks the ledger chain, checks every object
against its hash, and checks every head projection against its version. It
runs in the suite and in Tier 5's fourth scenario, where it verifies four
versions after two rounds of rulings. An approved definition compiles
deterministically to SQL (inner joins from the demonstrated join path,
invariant filters, grouping) and executes; Tier 5 compares the result to the
hidden truth by result-set equality with the same comparator the saved-query
harness uses.

### 5.4 Tier 3: not run, and why

Tier 3 compares a model answering business questions from the raw schema
against the same model answering from the induced layer through a validated
plan that cannot invent joins or filters. The delta measures part B, which
the platforms already ship and this report takes as a premise. It is kept as
calibration for the induction feeder, and it is the only harness that needs a
live model. A key-less dry run records every request a live run would send
and prices it against list rates: ten calls, roughly 9,200 input tokens,
about six cents on the model the runbook names. Cost is not the reason it was
not run. Relevance is.

## 6. Limitations

- **Corpora are synthetic.** TPC-H, TPC-DS at scale factor 0.01, and a
  generated order-to-cash world. Real query history has more noise, more
  authors, and more cosmetic variation than any of these.
- **Labels are one person's judgment.** The Tier 4 labels encode what the
  author believes a reviewer would say. The manifest records a rationale for
  each so a reader can disagree with a specific label rather than the
  method.
- **Small N.** 26 Tier 4 scenarios and one Tier 5 corpus. The confusion
  matrix is pinned in tests as a regression baseline, not offered as a
  population estimate.
- **Single-aggregate definitions.** Metric plans carry one aggregate; ratio
  and composite metrics are future work, and the fulfillment demo's own
  headline metric is a ratio.
- **Two ruling stores.** A conflict-level store with supersession exists
  from the original Stage 4c design, and a per-definition store is what
  answers questions and what Tier 5 tests. Convergence is a refactor with a
  harness to keep it honest, not an open question about the claim.
- **No downstream lift measured.** Whether governed memory improves answer
  correctness on real questions is the number a buyer wants. It needs real
  usage and is named as future work.

## 7. What would change the conclusions

**Materiality ranking.** Replace or supplement the structural rules with
execution: compile each rival signature, run both against a sample, and rank
the fork by relative divergence weighted by reach. The Tier 4 corpus already
contains the cases that would separate scope from definition under execution,
so the same harness measures whether the change helps.

**Rationale-learned rules.** Stage 4c captures rationales with a
`generalizes` flag. A ruling that says "these differ by grain, not
definition" should suppress the next hundred grain forks without a human.
The escalation rate over time, the fraction of conflicts still needing a
person, is the production metric the design proposes and the one a pilot
would plot.

**A real pilot.** Two weeks on one company's query history, measuring the
human-authored fraction, distinct candidates, genuine same-grain conflicts,
and whether one named owner will rule on twenty. Then five to ten users on a
hosted memory, measured by time to a trusted definition and whether rulings
keep accruing unattended. This is the number this report cannot supply.

**Converging the stores.** Rule on the conflict, not on each definition, as
the original design says, with Tier 5 as the regression guard.

**Publishing back.** An approved definition should land in the customer's
Snowflake verified-query repository, Databricks trusted assets, dbt, and the
Apache Ossie interchange format, so the memory sits above the platforms and
feeds them rather than competing with their free induction.

**Conformance checking.** The loop in Section 4 governs agents that read the
ruling before answering. Most agents will write their own SQL. Their queries
land in the same warehouse log the corpus comes from, so the rulings in force
can serve as the normative model and the log as observed behaviour, in the
sense of Rozinat and van der Aalst [SRC-043]: extract each new query's
signature, compare it to the ruling in force at its timestamp, and flag
non-conformance to the definition's owner. The non-conformance rate per
definition over time is the drift re-check that Section 3 finds no vendor
ships, and the whole path needs no model call. It depends on the materiality
work above: with structural comparison at 55% precision, a checker would mark
scope filters as violations. Applying the observed query's extra predicates
to the ruled definition and executing both cancels pure scope and leaves
definitional differences.

**Disclosure accounting.** Nothing in the design is trained; the memory is
lent to a model one question at a time. What is lent is recorded nowhere
today. A disclosure ledger, written by the MCP server per tool response and by
the metered client per outbound call, with entry hashes rather than content,
would let an enterprise answer which models have read a given ruling and
where redacted content had already gone. The design limits and records
disclosure to a hosted model; preventing it is a deployment choice of
inference endpoint.

## 8. Reproducibility

Repository: `https://github.com/joshuawinter/analytical-memory`, Apache-2.0.
Python 3.11 or later. No API key, no download, no network after install.

```powershell
git clone https://github.com/joshuawinter/analytical-memory.git
cd analytical-memory
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q            # 131 passed, 3 skipped on a clean clone
.\.venv\Scripts\python.exe scripts\run_tier5.py    # Section 5.1
.\.venv\Scripts\python.exe scripts\run_tier4.py    # Section 5.2, no-profile mode
.\.venv\Scripts\python.exe scripts\fetch_tpcds.py --scale 0.01 --no-answers
.\.venv\Scripts\python.exe scripts\run_tier4.py    # Section 5.2, with profile evidence; suite then 134 passed
```

The Tier 4 generated corpus is a pure function of `scripts/build_tier4_corpus.py`
and a test asserts the committed files are byte-identical to its output. The
numbers in Section 5 were taken at the commit tagged `paper-v0.1`. The
runbook (`RUNBOOK.md`) lists every command, including the Tier 3 dry run and
the spend ledger that enforces the project's cost ceiling.

## 9. Sources

Source ids resolve in `research/README.md`, which records access dates, URLs,
and DOIs. Those used in this report:

| Id | Source |
|---|---|
| SRC-011 to SRC-034 | Primary vendor documentation for dbt, Google, Microsoft, AWS, Snowflake, Databricks, illumex, Teradata, accessed 2026-10-12 |
| SRC-035 | Sequeda, Allemang, Jacob. *A Benchmark to Understand the Role of Knowledge Graphs on Large Language Model's Accuracy for Question Answering on Enterprise SQL Databases.* arXiv:2311.07509, 2023 |
| SRC-036 | Li et al. *Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs* (BIRD). NeurIPS 2023 |
| SRC-037 | Lei et al. *Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows.* ICLR 2025 |
| SRC-038 | Chen et al. *BEAVER: An Enterprise Benchmark for Text-to-SQL.* arXiv:2409.02038, v3 2026 |
| SRC-039 | Uber Engineering. *The Journey Towards Metric Standardization.* 2021-01-12 |
| SRC-040 | Elmeleegy, Ouzzani, Elmagarmid. *Usage-Based Schema Matching.* ICDE 2008. DOI 10.1109/icde.2008.4497410 |
| SRC-041 | Halevy et al. *Goods: Organizing Google's Datasets.* SIGMOD 2016. DOI 10.1145/2882903.2903730 |
| SRC-042 | Halevy, Norvig, Pereira. *The Unreasonable Effectiveness of Data.* IEEE Intelligent Systems, 2009. DOI 10.1109/mis.2009.36 |
| SRC-043 | Rozinat, van der Aalst. *Conformance checking of processes based on monitoring real behavior.* Information Systems, 2008. DOI 10.1016/j.is.2007.07.001 |
| SRC-044 | Khoussainova, Kwon, Balazinska, Suciu. *SnipSuggest: Context-Aware Autocompletion for SQL.* PVLDB 2010. DOI 10.14778/1880172.1880175 |

Airbnb's Minerva and LinkedIn's Unified Metrics Platform posts, and Gartner's
active-metadata guidance, are referred to in the repository's prior-art notes
but could not be reached from the author's network on 2026-10-21 and are not
cited here.
