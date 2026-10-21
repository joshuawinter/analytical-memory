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
| 2. Tier 4 expansion to a reportable set | **done** | 23 generated + 3 handcrafted; precision 55%, recall 75% with profiles |
| 3. Verify cited prior-art rows | **done** | 10 sources verified (SRC-035 to SRC-044); Airbnb, LinkedIn, Gartner unreachable, dropped from citations |
| 4. License + README, clean-clone runnable | **done** | Apache-2.0; verified by a fresh clone from GitHub: 131 passed, 3 skipped; Tier 4 and 5 pass |
| 5. Draft technical report | **draft v0.1** | `docs/PAPER.md`; needs Josh's read, author line, and a decision on venue |
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
- **Tier 4 does not meet its own goal yet.** On 23 semantically labelled
  scenarios the conflict classifier scores 55% precision, 75% recall with
  profiles. It over-flags scope filters that recur or sit on low-cardinality
  columns (5 of 15 negatives) and misses a definitional filter seen once (2
  of 8 positives). "Precision over recall" is stated in the architecture
  and not achieved by structural heuristics. The paper should report this
  and argue for execution-backed materiality: a scope filter changes the
  population, a definitional filter changes the number for the same
  population, and only execution can tell them apart.

## Decisions pending from Josh

- **Copyright name.** LICENSE says "Copyright 2026 Josh Parsons", taken from
  the git author. Correct it if the legal name or an entity should appear.
- **Venue and length.** The draft is a practitioner-facing technical report
  of about 3,800 words. Trim for a blog post, or expand Sections 3 and 5 for
  a workshop submission.
- **Investor deck.** Still tracked in the repo and now public with the
  license. Keep, move, or delete.
- **Tier 3.** Prepared, priced at cents, not run. Say so if an appendix run
  is wanted.

Defaults in use: Apache-2.0 license; investor deck untouched; live-run model
stays the RUNBOOK's setting.

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
- 2026-10-21: Tier 4 expanded to 26 scenarios with semantic labels. Result
  is an honest 55%/75%, all misses documented and pinned in tests. Next:
  prior-art verification for cited rows.
- 2026-10-21: Prior art for the paper verified. Sequeda's 16% to 54% is
  exact. BIRD, Spider 2.0, BEAVER verified with their headline numbers.
  Uber's uMetric post gives the concrete "6.53M vs 6.20M" case. SnipSuggest
  corrected to 2010. Airbnb Minerva (Medium 403), LinkedIn UMP (404), and
  Gartner (paywall) could not be reached and are not cited. Next: license
  and README.
- 2026-10-21: License, README, pyproject metadata. A fresh clone from GitHub
  exposed two defects (ruling tie-break on equal timestamps; Tier 4 exit code
  without a database), both fixed with tests. Re-clone: 131 passed, 3
  skipped, Tier 4 and 5 pass, ledger $0.
- 2026-10-21: `docs/PAPER.md` draft v0.1 written, about 3,800 words,
  citing only verified sources (SRC-011 to SRC-044). All five steps of the
  track have a first version. Remaining work is Josh's: read, decide venue,
  confirm the copyright line, decide the deck's fate.
