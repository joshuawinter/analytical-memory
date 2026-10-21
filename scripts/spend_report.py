"""Print the project's estimated live-model spend from the append-only ledger.

Offline. Reads data/spend/ledger.jsonl (or SEMANTIC_INDUCTION_SPEND_DIR) and
prints totals against the RUNBOOK section 14 ceiling and hard stop. Exit code
is 0 under the ceiling, 1 at or past the ceiling, 2 at or past the hard stop,
so it can gate a script.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from semantic_induction.spend import open_ledger  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the summary as JSON instead of text")
    parser.add_argument("--entries", action="store_true", help="also list every ledger line")
    args = parser.parse_args()

    ledger = open_ledger()
    summary = ledger.summary()

    if args.json:
        payload = asdict(summary)
        if args.entries:
            payload["entries"] = [asdict(entry) for entry in ledger.entries()]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"ledger: {ledger.path}")
        print(summary.render())
        if args.entries:
            print()
            for entry in ledger.entries():
                served = "cache" if entry.cache_hit else "live"
                cost = "n/a" if entry.cost_usd is None else f"${entry.cost_usd:.4f}"
                print(
                    f"{entry.recorded_at}  {served:5}  {entry.model:22}  {entry.purpose:10}  "
                    f"in={entry.usage.input_tokens} out={entry.usage.output_tokens}  {cost}"
                )

    if summary.total_usd >= summary.hard_stop_usd:
        return 2
    if summary.total_usd >= summary.ceiling_usd:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
