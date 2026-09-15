# Semantic Induction POC Runbook

Run these commands from the repository root:

```powershell
Set-Location C:\Users\jwp\semantic-induction-poc
```

## 1. Check the local environment

```powershell
Test-Path .\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import duckdb, sqlglot; print('dependencies ok')"
```

Expected output includes `dependencies ok`.

If the virtual environment is missing, create it and install the project:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 2. Run the offline test suite

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected result currently:

```text
70 passed
```

This path makes no network requests and does not require an API key.

## 3. Generate a persistent TPC-H database

This creates a small, reproducible TPC-H database and matching reference CSVs:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_tpch.py `
  --scale 0.01 `
  --database data\tpch\tpch.duckdb
```

The generator is idempotent: rerunning it replaces the existing TPC-H tables
before generating them, so it does not append duplicate rows to an existing
database file.

Verify it:

```powershell
.\.venv\Scripts\python.exe -c "import duckdb; con=duckdb.connect('data/tpch/tpch.duckdb', read_only=True); print(con.sql('SHOW TABLES').fetchall()); print(con.sql('SELECT COUNT(*) FROM lineitem').fetchone())"
```

## 4. Run the saved-query validation

```powershell
.\.venv\Scripts\python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from semantic_induction.validate import validate_corpus; results=validate_corpus(Path('data/tpch/tpch.duckdb'), Path('data/tpch/queries'), Path('data/tpch/answers')); print(f'total={len(results)} matched={sum(r.match for r in results)} failed={sum(not r.match for r in results)}'); print([(r.query_id, r.error) for r in results if not r.match])"
```

Expected result:

```text
total=22 matched=22 failed=0
[]
```

## 5. Run an individual SQL query manually

```powershell
.\.venv\Scripts\python.exe -c "import duckdb; from pathlib import Path; con=duckdb.connect('data/tpch/tpch.duckdb', read_only=True); con.sql(Path('data/tpch/queries/q01.sql').read_text()).show()"
```

## 6. Inspect the induced semantic layer

```powershell
.\.venv\Scripts\python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from semantic_induction.aggregate import aggregate; from semantic_induction.extract import extract_corpus; from semantic_induction.induce import induce; from semantic_induction.ingest import ingest; root=Path('data/tpch'); catalog, queries=ingest(root/'ddl.sql', root/'queries'); facts=extract_corpus(queries, catalog); layer=induce(aggregate(facts), catalog, facts, min_support=2); print('entities=', len(layer.entities)); print('measures=', len(layer.measures)); print('dimensions=', len(layer.dimensions)); print('metrics=', len(layer.metrics)); print(layer.entities)"
```

## 7. Test the local mock naming provider

```powershell
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); from semantic_induction.models import Entity, SemanticLayer; from semantic_induction.naming import name_layer; layer=name_layer(SemanticLayer(entities={'orders': Entity('orders', 'FACT')})); print(layer.names['orders'])"
```

## 8. Optional: install and test Claude naming

The API key must be set in the same PowerShell terminal where the test runs. Do not put it in a SQL file, source file, `.env.example`, or chat.

Install the optional client:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[anthropic]"
```

Set a replacement key directly in the current terminal:

```powershell
$env:SEMANTIC_INDUCTION_API_KEY = "YOUR_REPLACEMENT_KEY"
$env:SEMANTIC_INDUCTION_MODEL = "claude-sonnet-4-5"
```

Check only that the variable is present, without printing its value:

```powershell
if ($env:SEMANTIC_INDUCTION_API_KEY) { 'API key is set' } else { 'API key is missing' }
```

Run the minimal live smoke test:

```powershell
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); from semantic_induction.models import Entity; from semantic_induction.naming import AnthropicNamingProvider; result=AnthropicNamingProvider().name('smoke_test_entity', Entity('smoke_test_entity', 'DIM')); print('SMOKE_TEST_OK'); print(result.name); print(result.source)"
```

If the key is missing, the provider raises an explicit environment-variable error. If the optional package is missing, install `.[anthropic]` and retry.

## 9. Generate the TPC-DS smoke corpus

Generate all 99 query templates and the 24-table schema without executing answer workloads:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_tpcds.py --scale 0.01 --no-answers
```

Validate extraction and aggregation:

```powershell
.\.venv\Scripts\python.exe -c "import sys; from pathlib import Path; sys.path.insert(0, 'src'); from semantic_induction.aggregate import aggregate; from semantic_induction.extract import extract_corpus; from semantic_induction.ingest import ingest; root=Path('data/tpcds'); catalog, queries=ingest(root/'ddl.sql', root/'queries'); facts=extract_corpus(queries, catalog); stats=aggregate(facts); print(f'tables={len(catalog)} queries={len(queries)} edges={len(stats.edge_freq)} grains={len(stats.grain_freq)}')"
```

Expected output includes:

```text
tables=24 queries=99
```

## 10. Tier 3 - the actual demonstration

Everything above proves the pipeline runs. Tier 3 is the experiment that
proves the premise: it compares match rate for an LLM answering business
questions from the raw schema alone against an LLM answering from the
induced layer only, via a validated `MetricPlan` that can never invent a
join path or filter the corpus didn't demonstrate.

The offline test suite (`pytest`, section 2) already proves the harness
mechanics work end to end against the real induced TPC-H layer, using
deterministic mock composers instead of a live model. To get the actual
number the thesis depends on, run it against Claude:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[anthropic]"
$env:SEMANTIC_INDUCTION_API_KEY = "YOUR_REPLACEMENT_KEY"
$env:SEMANTIC_INDUCTION_MODEL = "claude-sonnet-4-5"
.\.venv\Scripts\python.exe scripts\run_tier3.py --database data\tpch\tpch.duckdb
```

This prints a MATCH/MISMATCH line per question per arm (plus the composed
SQL for each), then the raw-schema match rate, the induced-layer match
rate, and the delta between them -- the number described in
`docs/ARCHITECTURE.md`'s Tier 3 section.

Before induction, the script profiles the database and excludes induced metric
paths that would fan out rows relative to their grain. This is deterministic
and adds no API calls.

Two caveats the printed numbers do not carry on their own, documented at
the top of `scripts/run_tier3.py`:

- `MetricPlan` currently supports one `(aggregation, column)` measure per
  plan, so the bundled question is deliberately scoped to a single
  aggregate. A question needing several aggregates in one row (e.g. a
  full multi-column report) cannot be matched by the induced-layer arm
  yet -- that is a coverage gap, not evidence of bad induction.
- Reference answers are computed from independently-authored SQL, not
  reused from `data/tpch/answers/`. Do not reuse a famous, widely
  published benchmark query's exact wording as a business question: a
  frontier model has likely memorized it, so a high raw-schema match
  rate there may reflect recall rather than schema-driven reasoning.

If the key is missing, the script prints which environment variable is
missing and exits without making a request. If the database is missing, it
prints the exact `fetch_tpch.py` command to generate it.

## 11. Safety and cleanup

The API key previously pasted into chat or a file should be revoked in the Anthropic Console. Create a replacement key before running the live smoke test.

Local generated databases are ignored by Git:

```powershell
git check-ignore -v data\tpch\tpch.duckdb
```

Review staged files before committing:

```powershell
git status --short
git diff --cached --stat
git grep --cached -n -I -E 'sk-ant-|ANTHROPIC_API_KEY|SEMANTIC_INDUCTION_API_KEY=[^r]' -- .
```

The final command should produce no real key matches.

## 12. Label induced metric definitions

Run the local review interface across any domain (`tpch`, `tpcds`, or `fulfillment`):

```powershell
# For TPC-H (22 queries, 8 tables, 19 induced metrics):
.\.venv\Scripts\python.exe scripts\labeling_app.py --domain tpch

# For TPC-DS (99 queries, 24 tables, 285 induced metrics):
.\.venv\Scripts\python.exe scripts\labeling_app.py --domain tpcds

# For the Order-to-Cash Fulfillment Demo:
.\.venv\Scripts\python.exe scripts\labeling_app.py --domain fulfillment
```

Open `http://127.0.0.1:8765/` in a browser. Review each candidate's measure,
grain, joins, filters, evidence, and confidence, then choose `APPROVE`,
`REJECT`, or `CLARIFY` and provide a rationale.

The goal is low-friction expert feedback that improves the agent. The current
card interface is an implementation choice; no particular gesture or review
metaphor is a product requirement.

By default the candidate's business name and definition come from a
deterministic, zero-cost heuristic (no API key, no network call). To use
Stage 5's LLM naming pass instead -- which sees the full evidence a reviewer
sees (join path, invariant filters, and profile evidence such as observed
values and ranges), not just the bare column name -- set both credentials in
the same terminal and add `--naming-provider anthropic`:

```powershell
$env:SEMANTIC_INDUCTION_API_KEY = "YOUR_REPLACEMENT_KEY"
$env:SEMANTIC_INDUCTION_MODEL = "claude-sonnet-4-5"
.\.venv\Scripts\python.exe scripts\labeling_app.py --domain tpch --naming-provider anthropic
```

This makes one API call per induced candidate at server startup (19 calls for
TPC-H, 285 for TPC-DS -- mind the cost target in section 14 before choosing
`tpcds`). If the credentials are missing, the server refuses to start with a
clear error rather than silently falling back to the heuristic path.

The same page also includes an investigation panel. Enter a business question
to retrieve an approved definition, compile it to SQL, execute it locally, and
display the definition, evidence, SQL, and result rows. Questions with no
approved match show `NEEDS_REVIEW`; the interface never guesses a definition.

The interface is the first human-review slice. It covers semantic metric
labeling while the pipeline handles mechanical checks automatically, including
catalog validity, join structure, fanout risk, compilation, execution, and
result validation. The planned review stages are:

1. metric meaning and concept identity;
2. grain, time basis, and filter semantics;
3. evidence relevance and conflicting definitions;
4. finding plausibility, actionability, and causal claims.

Do not manually review checks that deterministic code can establish. Human
review is reserved for business meaning, ambiguity, and normative decisions.

## 13. Run an approved investigation

After approving at least one metric definition in the labeling interface, ask a
local question without an API call:

```powershell
.\.venv\Scripts\python.exe scripts\investigate.py `
  "What is the total quantity by line status and return flag?"
```

The command retrieves only approved definitions. If none or multiple approved
definitions match, it returns `NEEDS_REVIEW` or `AMBIGUOUS` instead of
guessing. For an answer it prints the inferred definition, evidence, compiled
SQL, and result rows.

## 14. MVP cost and compute discipline

The first meaningful experiment is local-first. Data generation, profiling,
DuckDB execution, labeling, SQL validation, and investigation execution should
use no API credits. Target API spend is `$5–$15`, with a preferred ceiling of
`$25`; pause and review before expanding beyond `$100`.

Use local CUDA/GPU only for embeddings, reranking, batch language generation,
small-model inference, or synthetic-data generation when it reduces external
cost or materially improves evaluation. Keep deterministic SQL and profiling
workloads on the CPU and cache all external prompts and responses.

The focused enterprise-like MVP domain is order-to-cash and fulfillment. Its
first investigation is:

```text
Why did on-time-in-full fulfillment decline this month?
```

The synthetic or sanitized model should include orders, order lines, inventory,
shipments, and operational events, with hidden truth for evaluation.

Launch the same review interface against the fulfillment domain:

```powershell
.\.venv\Scripts\python.exe scripts\labeling_app.py `
  --domain fulfillment `
  --database data\fulfillment_demo\fulfillment.duckdb `
  --labels data\fulfillment_demo\labels.json `
  --port 8766
```

Open `http://127.0.0.1:8766/`. Review and approve the OTIF definition, then
ask:

```text
Why did on-time-in-full fulfillment decline this month?
```

The browser will execute the reviewed SQL realization and show the result,
evidence, and metric definition. The hidden `truth.json` file is not used by
the review or investigation path.

The browser and CLI share the same `InvestigationService`; MCP will be added as
another client adapter over that service. This keeps approval gates,
provenance, and deterministic execution identical across interfaces.

## 15. Build the fulfillment demo

Generate the first enterprise-like order-to-cash world without an API call:

```powershell
.\.venv\Scripts\python.exe scripts\build_fulfillment_demo.py
```

Open the generated report in a browser:

```text
data/fulfillment_demo/report.html
```

The report shows January versus February fulfillment and the warehouse driver.
The hidden evaluation truth is stored separately in `truth.json`; the future
agent workflow must recover that cause from the event and inventory evidence,
not receive it as prompt context.

Run the deterministic investigation:

```powershell
.\.venv\Scripts\python.exe scripts\investigate_fulfillment_demo.py
```

Then open:

```text
data/fulfillment_demo/investigation.html
```

This second report is the visual baseline for the future agent. It derives the
monthly decline and warehouse driver from the database, states the metric
definition and evidence used, and does not read `truth.json`.

The structured investigation record is written to:

```text
data/fulfillment_demo/investigation.json
```

Evaluate the derived finding against the hidden truth:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_fulfillment_demo.py
```

The evaluator checks driver identification, finding agreement, evidence
presence, and that the investigation did not read the hidden truth.

## 16. Run the Model Context Protocol (MCP) Server

Expose analytical memory and approval-gated investigations over standard MCP stdio:

```powershell
.\.venv\Scripts\python.exe scripts\mcp_server.py --domain fulfillment
```

To configure in an MCP client (such as Claude Desktop or Cursor), add to `claude_desktop_config.json` / client config:

```json
{
  "mcpServers": {
    "analytical-memory": {
      "command": "C:\\Users\\jwp\\semantic-induction-poc\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\jwp\\semantic-induction-poc\\scripts\\mcp_server.py",
        "--domain",
        "fulfillment"
      ]
    }
  }
}
```

The server provides:
- **Tools:** `search_business_memory`, `get_review_candidates`, `run_approved_investigation`
- **Resources:** `memory://concepts`, `memory://metric_definitions`, `memory://evidence`, `memory://resolutions`
- Strict approval enforcement: unapproved questions return `NEEDS_REVIEW`. No raw SQL execution is permitted.

## 17. Export Induced Model to Apache Ossie Format

Export an auto-induced semantic layer into vendor-neutral Apache Ossie YAML format (consumable by Cube, dbt Semantic Layer, or AtScale):

```powershell
.\.venv\Scripts\python.exe scripts\export_ossie.py `
  --domain tpcds `
  --out data\tpcds\induced_ossie_model.yaml
```

This induces all 24 datasets, measures, and relationships from the 99 raw TPC-DS SQL queries and serializes them into valid Apache Ossie spec YAML in seconds with zero API calls.

## 18. Run the Tier 4 conflict-precision harness

Offline and deterministic -- no API key, no live model. Measures whether
Stage 4b's conflict detection correctly separates a genuine definitional
disagreement from benign grain variation, against a small set of
hand-authored TPC-DS query pairs with known ground truth (see
`docs/ARCHITECTURE.md`'s Tier 4 section):

```powershell
.\.venv\Scripts\python.exe scripts\run_tier4.py
```

Prints PASS/FAIL per scenario plus precision, recall, and noise rate. Exits
non-zero if any scenario is misclassified. Defaults to
`data\tpcds\tpcds.duckdb` for profile evidence (sharpens the low-cardinality
check) if that file exists, and runs without it otherwise; pass
`--database` to point at a different one.

The same scenarios run in the offline test suite (`pytest`, section 2) as
`test_tier4.py`, so a regression here is caught before it reaches this
script.
