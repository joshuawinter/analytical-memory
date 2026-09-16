---
name: govern
description: Review induced metric candidates, record human APPROVE/REJECT/CLARIFY rulings with rationale, and run approved investigations against this project's analytical memory via the analytical-memory MCP server. Use when the user wants to review candidates, resolve a conflict, approve or reject a definition, or ask a business question against this project's memory.
---

# Analytical memory governance

This is Stage 4c of the induction pipeline described in `docs/ARCHITECTURE.md`: the
system proposes an evidence-backed interpretation, a human decides, the decision
and rationale become durable corporate memory. You are the interface to that
loop, connected via the `analytical-memory` MCP server (`.mcp.json`). You are
never the human making the ruling.

## The contract (non-negotiable)

- **Never call `record_review_decision` without an explicit decision from the
  user in this conversation.** Reading a candidate's evidence and judging "this
  looks right" is not a substitute for the user actually saying "approve it" or
  "reject it, because...". If asked to "review these," present each candidate
  and its evidence, then wait for a ruling per item.
- **`decided_by` must identify the actual human**, not you. Ask who is ruling if
  it is unclear from context. Never default to a placeholder like "assistant"
  or "claude".
- **`rationale` must be the user's actual reasoning**, not your inference of
  what it probably is. A rationale you invented to fill the field is worse than
  none: it looks authoritative, it is not, and per `docs/ARCHITECTURE.md` it is
  exactly the kind of fabricated ruling that "will generalize, and will
  propagate silently."
- If asked to bulk-approve a batch without the user stating their reasoning per
  item, push back: confirm the same rationale genuinely applies to each one
  rather than approving on their behalf because it is tedious to do one at a
  time. Speed is not the point of this loop.

## Workflow

1. **List candidates**: call `get_review_candidates`. Present measure, grain,
   evidence, and profile notes for each. A candidate with `"structured": false`
   is an AI narration of SQL the flat measure/grain/filter model cannot
   represent faithfully (a CTE, a CASE branch, a nested subquery) -- present it
   clearly as "not a governed definition, needs SQL review," not as an approved
   metric.
2. **Search existing memory before assuming nothing exists**: call
   `search_business_memory` when the user asks whether a concept or alias has
   already been defined.
3. **Record a ruling only after the user states it**: call
   `record_review_decision` with their exact decision and rationale, correctly
   attributed via `decided_by`.
4. **Answer business questions** via `run_approved_investigation`. It uses
   approved definitions only and returns `NEEDS_REVIEW` or `AMBIGUOUS` rather
   than guessing. A `NEEDS_REVIEW` result is the answer -- do not compose SQL
   yourself as a workaround; that is exactly the raw-schema-arm behavior Tier 3
   exists to show underperforms the governed path.
5. **One domain per connection**: `.mcp.json` fixes the connected server to one
   domain (`tpch`, `tpcds`, or `fulfillment`). To switch, tell the user to edit
   `--domain` in `.mcp.json` and reconnect -- do not work around it by invoking
   `scripts/*.py` directly, which would write outside the one audit trail every
   client is supposed to share.

## What this skill does not do

It does not give you a raw SQL tool, on purpose --
`docs/ARCHITECTURE.md` describes MCP as exposing "approved memory and
investigation capabilities... without... adding an unrestricted SQL tool." If a
business question needs a definition that does not exist yet, the answer is to
induce and label it through the normal pipeline (`RUNBOOK.md` sections 12-13),
not to hand-write SQL through this skill.
