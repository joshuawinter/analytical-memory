"""Fetch SOMA's B2B SaaS metrics definitions as an independent ground truth
for cross-checking induced/narrated definitions against a real, formally
governed spec -- see ARCHITECTURE.md's "Corpus expansion" section on why a
second, differently-produced ground truth (beyond TPC-DS's published
descriptions) matters for testing whether induction generalizes.

SOMA (github.com/Levers-Labs/SOMA-B2B-SaaS) ships no LICENSE file, so its
content is not redistributed into this repository: data/soma/ is fetched
fresh here and gitignored, the same way generated .duckdb files are. Only
this script and any code that reads its output belong in git history.

Usage:
    .venv/Scripts/python.exe scripts/fetch_soma.py
    .venv/Scripts/python.exe scripts/fetch_soma.py --force
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "soma"
SOURCE_DIR = OUT_DIR / "_source"
REPO_URL = "https://github.com/Levers-Labs/SOMA-B2B-SaaS.git"


def _clone(force: bool) -> Path:
    if SOURCE_DIR.exists():
        if not force:
            print(f"using existing clone at {SOURCE_DIR} (--force to re-clone)")
            return SOURCE_DIR
        shutil.rmtree(SOURCE_DIR)
    SOURCE_DIR.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, str(SOURCE_DIR)],
        check=True,
    )
    return SOURCE_DIR


def _load_ground_truth(source: Path) -> list[dict]:
    """Parse definitions/metrics/*.json into a flat, comparison-ready record per metric.

    SOMA's own field names are preserved as values (not renamed to this
    project's vocabulary) so a later diff against induced definitions is
    comparing SOMA's actual words, not a paraphrase of them.
    """
    metrics_dir = source / "definitions" / "metrics"
    records = []
    for path in sorted(metrics_dir.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        records.append(
            {
                "metric_ref": spec.get("Metric Ref", path.stem),
                "label": spec.get("Metric Label", ""),
                "definition": spec.get("Definition", ""),
                "expression": spec.get("Metric Expression", ""),
                "components": spec.get("Components", ""),
                "complexity": spec.get("Complexity", ""),
                "owning_team": spec.get("Owning Team(s)", ""),
                "watching_team": spec.get("Watching Team(s)", ""),
                "source_systems": spec.get("Source System(s)", ""),
                "theme": spec.get("Theme", ""),
            }
        )
    return records


def fetch(force: bool = False) -> None:
    source = _clone(force)
    records = _load_ground_truth(source)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "ground_truth.json"
    out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"wrote {len(records)} governed metric definitions -> {out_path}")

    model_count = len(list((source / "models").rglob("*.sql")))
    print(f"found {model_count} dbt model files under {source / 'models'} (not yet compiled)")

    with_expression = sum(1 for r in records if r["expression"])
    composite = sum(1 for r in records if r["complexity"].lower() == "composite")
    print(f"{with_expression} of {len(records)} specs carry an explicit Metric Expression")
    print(
        f"{composite} are marked Composite -- reference other metrics, not raw data; "
        "see the metric-to-metric lineage note in ARCHITECTURE.md before Phase 3"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-clone even if a local copy exists")
    args = parser.parse_args()
    fetch(force=args.force)
