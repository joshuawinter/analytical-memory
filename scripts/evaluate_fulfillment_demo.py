"""Compare the generated investigation record with hidden evaluation truth."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "fulfillment_demo"


def main() -> int:
    truth = json.loads((DATA / "truth.json").read_text(encoding="utf-8"))
    investigation = json.loads((DATA / "investigation.json").read_text(encoding="utf-8"))
    expected = truth["expected_driver"]
    actual = investigation["drivers"][0]["warehouse"]
    finding_match = expected in investigation["finding"]
    checks = {
        "driver_identified": actual == expected,
        "finding_matches_truth": finding_match,
        "did_not_read_hidden_truth": investigation["hidden_truth_used"] is False,
        "evidence_present": bool(investigation["evidence"]),
    }
    print(json.dumps({"checks": checks, "score": sum(checks.values()), "total": len(checks)}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())