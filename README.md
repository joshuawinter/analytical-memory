# analytical-memory

A self-hosted, append-only memory of how an enterprise defines its numbers,
with the human rulings that settle disagreements, built so that agents and
people read the same record.

Why now: when analysts worked in SQL, a definition sat in a `WHERE` clause a
colleague could read and question. In chat and agent interfaces nobody sees
the SQL, so that informal review is gone, and one wrong definition repeats in
every answer. Better models write better SQL; they cannot know which of two
valid definitions the company chose. That is a decision, and it has to be
recorded where agents read it.

Warehouse vendors now induce semantic layers from query history. Snowflake,
Databricks, and Google ship it. What they ship stops at accept-or-reject per
item: no record of why, no comparison of two definitions of the same
measure, no re-check against later usage. This repository is the loop they
leave out, as a reference implementation with offline, deterministic
evidence behind each claim:

| Claim | Harness | Result (2026-10-21) |
|---|---|---|
| Rival definitions of one measure are surfaced as a fork, not merged by frequency | Tier 5, `scripts/run_tier5.py` | 4 of 4 scenarios; 0 answers from frequency; 0 answers while contested |
| A dated human ruling with rationale is what the agent gets, at the right point in time, and is supersedable with history intact | Tier 5 | same run |
| The classifier separates a definitional disagreement from scope or grain variation | Tier 4, `scripts/run_tier4.py` | 26 semantically labelled scenarios: precision 55%, recall 75% with profile evidence. Not yet at its own goal; every miss documented |
| Every ruling and memory entry is a content-addressed, immutable version chained into one hash-chained ledger a text editor can audit | `MemoryStore.verify()` | runs in the suite |
| An approved definition compiles back to SQL and executes; result equality against independently authored truth | Tiers 3 and 5 | Tier 5 matches truth; Tier 3 is optional live calibration |

Induction from SQL is a feeder here, not the product. What is defended is
conflict detection, ledgered rulings that outrank frequency, and executable
validation. Read `docs/ARCHITECTURE.md` for the design and the pivot that
set this scope, `RUNBOOK.md` for every command, and `docs/PAPER_PROGRESS.md`
for where the write-up stands.

## Run it from a clean clone

Python 3.11 or later. No API key, no database download, no network after
`pip`.

```powershell
git clone https://github.com/joshuawinter/analytical-memory.git
cd analytical-memory
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Everything the claims above rest on runs in that suite. Two things are
optional and need a generated database first (RUNBOOK sections 3 and 9;
DuckDB generates TPC-H and TPC-DS locally in seconds, nothing is
downloaded): the Tier 4 profile-evidence tests, which skip until
`data/tpcds/tpcds.duckdb` exists, and the browser review interface.

```powershell
.\.venv\Scripts\python.exe scripts\run_tier5.py          # rulings outrank frequency
.\.venv\Scripts\python.exe scripts\run_tier4.py          # conflict precision, both scenario sets
.\.venv\Scripts\python.exe scripts\fetch_tpcds.py --scale 0.01 --no-answers
.\.venv\Scripts\python.exe scripts\labeling_app.py --domain tpcds   # then open http://127.0.0.1:8765/
```

Live model calls exist only in Tier 3 (induction calibration) and the
optional Stage 5 naming pass. Both go through a spend ledger and response
cache with an enforced ceiling, and both have a key-less `--dry-run` that
prices the run first. See RUNBOOK sections 10 and 14.

## What is in the repository

```
src/semantic_induction/   ingest -> extract -> aggregate -> induce -> conflicts (4b)
                          -> memory / labeling / store (4c, the ledger) -> investigate
                          plan / compile / validate   deterministic SQL round trip
                          tier3 / tier4 / tier5       evaluation harnesses
                          spend                        ledger, cache, dry runs
                          mcp_server                   governed MCP interface
scripts/                  one entry point per RUNBOOK section
data/tpch, data/tpcds     DDL, query corpora, Tier 4 and Tier 5 fixtures (databases are generated, not committed)
data/fulfillment_demo     order-to-cash demo world with hidden truth
docs/ARCHITECTURE.md      design, decisions, tier definitions and results
docs/PAPER_PROGRESS.md    research-paper track status
research/                 verified sources (SRC ids) and the prior-art audit
tests/                    offline suite; see RUNBOOK section 2 for the expected count
```

## Interfaces

Three clients share one `InvestigationService` and one write path, so a
ruling recorded from any of them lands in the same ledger: the browser
review interface, the `scripts/investigate.py` CLI, and an MCP server
(`scripts/mcp_server.py`) that exposes memory search, review candidates,
approval-gated investigation, and decision recording. The MCP tool contract
refuses to approve anything the human did not decide; see "Agent interface
boundary" in the architecture doc before wiring it to an autonomous client.

## Status and caveats

- Research prototype. Single-aggregate metric plans; composite and ratio
  metrics are future work.
- Evidence is on TPC-H, TPC-DS, and a synthetic fulfillment world. No
  downstream lift in answer correctness has been measured on real usage;
  that needs a pilot and is named as future work.
- Two ruling stores exist in the code (conflict-level and per-definition);
  the per-definition path is what answers questions and what Tier 5 tests.
  Convergence is a planned refactor.
- The classifier over-flags scope filters on this corpus (Tier 4). The
  architecture names execution-backed materiality as the fix.

## License

Apache License 2.0. See `LICENSE`. Third-party data: TPC-H and TPC-DS are
generated locally by DuckDB's extensions under their own terms; the SOMA
dbt project is fetched fresh by `scripts/fetch_soma.py` and never committed
because it ships no license file.
