# Paper progress

Running log for the research-paper track. Updated in every commit on this
track. Read this first if you have one minute.

Direction, decided 2026-10-21: practitioner-facing technical report. The
repo is the open-source artifact. Evidence is offline and deterministic;
Tier 3 is optional calibration, prepared but not run.

## Status

| Step | State | Notes |
|---|---|---|
| 1. Tier 5 harness (rulings outrank frequency) | **done** | 4/4 scenarios pass, both counters zero; `scripts/run_tier5.py` |
| 2. Tier 4 expansion to a reportable set | not started | 3 scenarios today |
| 3. Verify cited prior-art rows | not started | only rows the paper cites |
| 4. License + README, clean-clone runnable | not started | default Apache-2.0 |
| 5. Draft technical report | not started | `docs/PAPER.md` |
| Tier 3 preparation (not execution) | **done** | `--dry-run` on both scripts; client installed (anthropic 2.0.0); ~$0.06 typical for the full TPC-H run on sonnet-4-5 |

## Findings worth carrying into the paper

- **The fork never reached memory.** Induction merged rival signatures by
  predicate intersection, so the only definition in memory was the
  majority's with the disputed filter dropped. Stage 4b detected the
  rivalry; nothing carried it forward. This is the mechanism by which
  frequency wins silently, and the paper should lead with it. Fixed:
  `memory_from_layer(conflicts=...)`.
- Rulings now have validity windows and history; questions can be asked
  `as_of` a moment. Supersession is tested.
- **Tier 3 is cheap.** A dry run prices the full TPC-H three-arm run at
  cents on every current model. If Josh wants it in an appendix, cost is
  not the objection; the objection remains that it measures part B.

## Decisions pending from Josh

None blocking. Defaults in use: Apache-2.0 license; investor deck untouched;
live-run model stays the RUNBOOK's setting.

## Spend

API ledger: $0.00 (no live call has ever been made). Check with
`scripts/spend_report.py`. Session cost: `/cost` in Claude Code.

## Log

- 2026-10-21: track opened. Tier 5 build started.
- 2026-10-21: Tier 5 built and passing. Three code gaps fixed (fork not in
  memory; validity windows ignored; only head ruling kept). Suite at 124
  tests.
- 2026-10-21: Tier 3 prepared. Dry-run mode records and prices every call
  without a key; exact counts available via count_tokens when a key is set.
  Suite at 129 tests. Next: Tier 4 expansion.
