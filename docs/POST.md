# The majority of your SQL is wrong about something, and your warehouse just made it official

*How induced semantic layers hand the win to whichever definition is most common, and what it takes to let a human ruling outrank the count.*

In January 2021, Uber's data platform team explained why they had built a metrics platform. One business metric, "Shopping Session," read 6.53 million in one tool and 6.20 million in another, for the same city and the same time range. One tool was carrying outdated filters. Their diagnosis, in their own words: "multiple versions of metrics defined or generated in different channels for the same business logic." Their fix was a certified store where each metric has exactly one definition. ([The Journey Towards Metric Standardization](https://www.uber.com/blog/umetric/))

That fix is authored. Someone writes the definition down and the platform enforces it. Airbnb and LinkedIn published the same story in the same years. None of them published the step before: discovering, from the queries people were already running, that two definitions were in circulation, and recording who settled it and why.

Five years later the warehouses have taken over the writing-down. Snowflake's Semantic View Autopilot will "surface historical SQL queries as suggestions to the semantic view." Databricks Genie "automatically searches for relevant popular workspace queries" and turns author feedback into suggested measures, filters, and joins. Google's Knowledge Catalog, in preview, mines "structured schemas, query logs, and BI semantic models." Inducing a semantic layer from query history is now a checkbox.

Here is what each of them produces: a proposal you accept or reject, one item at a time. Snowflake's verified queries carry a `verified_by` name and no reason field. Databricks tells authors to "review and resolve any inconsistencies" by hand, and its metric views have no version history. Google has named "resolving conflicting definitions" as a pillar and described no mechanism. Microsoft's Fabric IQ ontology comes closest, with proposal-first review and named versions, and still records no rationale per ruling. (I verified each of these against the vendors' own documentation in October 2026; the table with page links is in the repository's [prior-art audit](https://github.com/joshuawinter/analytical-memory/blob/main/research/prior-art.md).)

So the Uber failure is still possible inside every one of these platforms. Two teams' queries disagree. The induced layer absorbs whichever is more common. A reviewer clicks accept. The reason the other team had is gone.

I built the loop that closes that gap, and then I built the tests that would embarrass it. This post is about what those tests found.

## What I am claiming, and what I am not

Induction from query history works and the platforms ship it. I am not competing with that. I take "a usable induced layer exists" as given and make three claims about what happens next:

1. When two definitions of one measure are in use, both reach a human as a fork with the evidence for each, and nothing is answered from the more popular one while the fork is open.
2. A dated ruling with a rationale is what the agent gets, at the right point in time, and a later ruling supersedes it without erasing it.
3. Every ruling and every memory entry is an immutable, content-addressed version in a hash-chained ledger you can audit with a text editor, and an approved definition compiles back to SQL and runs.

I am not claiming a measured improvement in answer correctness on real company data. That needs a pilot I have not run. And the conflict classifier does not yet meet the precision target I set for it. More on that below.

## Why the layer matters at all

The text-to-SQL benchmarks make the case better than I can. Sequeda, Allemang, and Jacob ran GPT-4 zero-shot against an insurance schema: 16% accuracy on the raw database, 54% when the same questions were asked over a knowledge graph with an ontology and mappings ([arXiv:2311.07509](https://arxiv.org/abs/2311.07509)). BIRD names "external knowledge between NL questions and database contents" as a required input and reports its best model at 40% against a human 93% ([NeurIPS 2023](https://arxiv.org/abs/2305.03111)). Spider 2.0 moves to real enterprise workflows and reports 21% solved against 91% on the original Spider ([ICLR 2025](https://arxiv.org/abs/2411.07763)). BEAVER, built from private data warehouses, reports 10.8% for agentic frameworks on a frontier model, rising to 30% only when the domain-knowledge sub-answers are handed over ([arXiv:2409.02038](https://arxiv.org/abs/2409.02038)).

The gap is domain knowledge, and in every one of these the knowledge is supplied by hand. Nobody has published the step where it is recovered from usage, disputed, ruled on, and kept.

## The design in one diagram

```text
usage (SQL corpus, or the warehouse's own induced drafts)
  -> induce candidate definitions
  -> detect same-grain filter disagreement          the fork
  -> promote rivals into memory as CONTESTED
  -> human rules: decision, rationale, effective date
  -> answer only from the ruling in force at the moment asked
  -> compile to SQL, execute, compare to truth
  -> publish approved definitions back to the platforms
```

A definition is in one of three states. Uncontested: one signature, use it. Contested and unresolved: refuse, and show the fork. Contested and resolved: the ruling is durable and overrides frequency.

The memory itself is deliberately boring. A directory of small markdown files with flat front matter, each change an immutable content-addressed version, rendered verbatim to the model. Not a vector store, not a graph database, not rows the model never sees. Rulings and memory versions interleave in one append-only, hash-chained ledger, so "who ruled, what they wrote, and what the agent will now read" is one verifiable sequence. Deleting is a version. Redaction scrubs content and keeps the actor and timestamp. The chain makes tampering evident; making it impossible is a deployment question about where the files live.

## Test one: make the majority wrong

The claim that a ruling outranks frequency was, for months, true by construction and never tested. So I built a corpus to break it.

Thirteen analyst queries compute revenue by year over the TPC-DS store sales table. Ten of them sum every line. Three add `WHERE ss_quantity > 0`, excluding voided and giveaway tickets that still carry an amount. A hidden truth, written independently of all thirteen, says the three are right. That is the realistic case: most analysts copied a stale dashboard query.

Four scenarios run against the real question-answering path, with fixed dates so the run is reproducible:

| Scenario | Expected | Result |
|---|---|---|
| No ruling yet | Refuse, expose both rival definitions | pass |
| Approve the minority, reject the majority, dated January | Answer from the minority; result equals hidden truth | pass |
| Same question, asked "as of" December | Back to refusal | pass |
| Reverse the ruling, dated April | Majority after April; minority still answers for February; ledger verifies; both versions of the ruling readable | pass |
| Answers given from frequency while a ruling was in force | 0 | 0 |
| Answers given while contested with no ruling | 0 | 0 |

It passes now. It would not have passed when I started writing it, and the reason is the most useful thing in this post.

**The fork never reached memory.** The induction stage grouped a contested measure's queries together and took the *intersection* of their filters as the definition. The disputed filter was dropped, and the one surviving definition was, in effect, the majority's. The conflict detector saw the rivalry. Nothing carried its two candidates into the memory the answer path reads. There was nothing to approve or reject, and frequency won silently, by default, with no one choosing it.

That is a bug in my code. It is also, I think, a fair description of what accept-or-reject induction does by design. If the proposal you are shown is already the merged majority view, the review step cannot recover the minority. Once fixed, the project's own TPC-DS store showed ten forks across twenty-four candidate definitions that had been invisible.

Two smaller gaps fell out of the same test. The ruling record had an effective-date field that the answer path ignored. And only the latest ruling per definition was kept, so a reversal had no history to point back to. Both fixed. A fourth defect appeared only when I cloned the repo fresh and ran the suite on a fast machine: two rulings recorded within one clock tick tied on timestamp, and the resolver returned the earlier one, resurrecting the superseded decision.

## Test two: can it tell a disagreement from a filter?

The classifier's job is to separate a real definitional split from someone narrowing a question. Flood reviewers with "this analyst filtered to 2021" and the system is ignored inside a month. The design states the goal plainly: precision over recall. A missed conflict is a wrong number someone eventually catches. A false conflict is a VP's time, and three of those end a pilot.

I generated 23 scenarios in eight families and labelled them by meaning, not by what the classifier's rules would do. Does a reviewer see two definitions of the measure, or one definition at a different scope, grain, or wording? Seven of the labels are set against the classifier on purpose, with the reason recorded, because the point is to measure it.

Result, with the data-profile evidence the production configuration uses:

| | flagged | not flagged |
|---|---|---|
| definitional (8) | 6 | 2 |
| not definitional (15) | 5 | 10 |

Precision 55%. Recall 75%. The classifier does not meet its own goal. It over-flags scope more than it misses definitions.

The pattern is specific. The rule "a filter on a column with few distinct values is probably definitional" was written for status columns. On this data it fires on `d_weekend = 'Y'` and `i_category = 'Books'`. The rule "a filter that recurs across queries is probably definitional" turns every popular year filter into a rival definition. Both rules look at the shape of the predicate. Neither looks at what it does.

What it does is the distinction. A scope filter changes the number because it changes the population. A definitional filter changes the number for the same population. Recurrence and cardinality cannot see that. Execution can: compile both rivals, run both against a sample, and rank the fork by how far the results diverge on the questions people actually ask. That is the next thing to build, and the labelled corpus already contains the cases that would prove it.

I am publishing the 55% because a paper that only reported Tier 5 would be the accept-or-reject pattern applied to my own results.

## What this does not show

Everything above runs on TPC-H, TPC-DS, and a synthetic order-to-cash world. Real query history is noisier and has more authors. The labels are one person's judgment, with a rationale attached to each so you can disagree with a specific one. Twenty-six scenarios is a regression baseline, not a population estimate. Metric definitions carry a single aggregate; ratios are future work. And the number a buyer wants, whether governed memory improves answers on real questions, needs two weeks on a real company's query history and a few named owners willing to rule on twenty conflicts. I have not run that.

## Run it yourself

The repository is Apache-2.0 and runs from a clean clone with no API key and nothing downloaded. Everything in this post is reproducible from the commit tagged `paper-v0.1`.

```
git clone https://github.com/joshuawinter/analytical-memory.git
cd analytical-memory
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\run_tier5.py
.\.venv\Scripts\python.exe scripts\run_tier4.py
```

The full technical report, with the design in detail, the vendor-by-vendor table, and every source, is at [docs/PAPER.md](https://github.com/joshuawinter/analytical-memory/blob/main/docs/PAPER.md). If you run a data platform and recognize the Uber number from your own shop, I would like to hear what your two definitions were.

---

*Josh Parsons builds marine fabrication tooling and data software. This is independent work; no employer or vendor was involved.*
