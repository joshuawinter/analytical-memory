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
| Tier 3 preparation (not execution) | not started | key-less dry run, ledger hard stop, cache |

## Findings worth carrying into the paper

- **The fork never reached memory.** Induction merged rival signatures by
  predicate intersection, so the only definition in memory was the
  majority's with the disputed filter dropped. Stage 4b detected the
  rivalry; nothing carried it forward. This is the mechanism by which
  frequency wins silently, and the paper should lead with it. Fixed:
  `memory_from_layer(conflicts=...)`.
- Rulings now have validity windows and history; questions can be asked
  `as_of` a moment. Supersession is tested.

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
