"""Stage 4c - durable, versioned conflict rulings."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from semantic_induction.models import Conflict, Ruling


def conflict_id(conflict: Conflict) -> str:
    """Return a stable identifier for a conflict's measure and candidates."""
    candidate_ids = sorted(
        f"{candidate.measure}:{sorted(candidate.grain)}:{candidate.seen_in}"
        for candidate in conflict.candidates
    )
    return f"{conflict.kind}|{conflict.measure}|{sorted(conflict.grain)}|{candidate_ids}"


class ResolutionStore:
    """Small JSON resolution store suitable for the POC and easy to replace."""

    def __init__(self, path: Path):
        self.path = path
        self._rulings: list[Ruling] = []
        if path.exists():
            self._rulings = [self._decode(item) for item in json.loads(path.read_text())]

    @staticmethod
    def _decode(item: dict[str, object]) -> Ruling:
        return Ruling(
            conflict_id=str(item["conflict_id"]),
            chosen=item.get("chosen") if isinstance(item.get("chosen"), str) else None,
            rationale=str(item["rationale"]),
            generalizes=bool(item["generalizes"]),
            ruled_by=str(item["ruled_by"]),
            ruled_at=datetime.fromisoformat(str(item["ruled_at"])),
            valid_from=datetime.fromisoformat(str(item["valid_from"])),
            supersedes=item.get("supersedes") if isinstance(item.get("supersedes"), str) else None,
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(ruling) | {
                "ruled_at": ruling.ruled_at.isoformat(),
                "valid_from": ruling.valid_from.isoformat(),
            } for ruling in self._rulings], indent=2) + "\n"
        )

    def add(self, ruling: Ruling) -> None:
        if not ruling.rationale.strip():
            raise ValueError("rationale is required")
        self._rulings.append(ruling)
        self.save()

    def resolve(self, conflict: Conflict, as_of: datetime | None = None) -> Ruling | None:
        timestamp = as_of or datetime.now(timezone.utc)
        matches = [
            ruling for ruling in self._rulings
            if ruling.conflict_id == conflict_id(conflict)
            and ruling.valid_from <= timestamp
        ]
        return max(matches, key=lambda ruling: ruling.valid_from, default=None)