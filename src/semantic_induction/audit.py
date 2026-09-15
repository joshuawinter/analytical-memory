"""Customer-controlled, tamper-evident audit ledger for knowledge decisions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditIntegrityError(ValueError):
    """Raised when an append-only ledger has been changed or is malformed."""


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _event_hash(event: dict[str, Any]) -> str:
    payload = {key: value for key, value in event.items() if key != "event_hash"}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class AuditLedger:
    """Append-only, hash-chained event ledger stored in customer-owned storage."""

    def __init__(self, path: Path | None = None):
        self.path = path

    def events(self) -> list[dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def verify(self) -> str | None:
        previous_hash: str | None = None
        for index, event in enumerate(self.events(), start=1):
            if event.get("previous_hash") != previous_hash:
                raise AuditIntegrityError(f"event {index} has an invalid previous_hash")
            if event.get("event_hash") != _event_hash(event):
                raise AuditIntegrityError(f"event {index} hash does not match its contents")
            previous_hash = event["event_hash"]
        return previous_hash

    def append(self, event_type: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not event_type.strip() or not actor.strip():
            raise ValueError("event_type and actor are required")
        previous_hash = self.verify()
        event = {
            "event_id": hashlib.sha256(
                f"{datetime.now(timezone.utc).isoformat()}:{event_type}:{actor}".encode("utf-8")
            ).hexdigest()[:24],
            "event_type": event_type,
            "actor": actor,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "previous_hash": previous_hash,
            "payload": payload,
        }
        event["event_hash"] = _event_hash(event)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as output:
                output.write(_canonical_json(event) + "\n")
        return event
