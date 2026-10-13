"""Append-only, content-addressed storage for shared analytical memory.

Design, recorded in ARCHITECTURE.md under "Memory storage format":

* Every memory entry is a small text document (markdown with a YAML-style
  front matter block) addressed by a path. This is the shape Claude's own
  memory surfaces use -- per-topic text entries rendered verbatim into
  context -- and the shape Anthropic's Managed Agents memory stores expose
  (path-addressed text files, each mutation an immutable version carrying
  an operation, an actor, and a ``content_sha256``).
* Nothing is updated in place. A write produces an immutable, content-
  addressed object plus a ledger event chained into the customer-owned
  ``AuditLedger``. The head file under ``entries/`` is a projection that can
  be rebuilt from the ledger and objects at any time.
* Redaction scrubs an object's content but keeps the version event, so the
  audit trail survives a leaked secret or a deletion request.
* This module is dependency-free on purpose: the format has to be readable
  by a person with a text editor long after any particular service is gone.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from semantic_induction.audit import AuditIntegrityError, AuditLedger

MEMORY_VERSION_EVENT = "MEMORY_VERSION"
MEMORY_REDACTION_EVENT = "MEMORY_REDACTION"
OPERATIONS = ("created", "modified", "deleted")
REDACTED_MARKER = "[redacted]\n"
MAX_ENTRY_BYTES = 100_000


class MemoryStoreError(ValueError):
    """Raised when a write cannot be applied."""


class MemoryConflictError(MemoryStoreError):
    """Raised when an optimistic-concurrency precondition fails."""


@dataclass(frozen=True)
class MemoryVersion:
    version_id: str
    path: str
    operation: str
    content_sha256: str | None
    actor: str
    recorded_at: str
    redacted: bool = False


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def safe_segment(value: str) -> str:
    """Turn an identifier such as ``metric:3:sum`` into a filesystem-safe name."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return cleaned or "entry"


def render_entry(metadata: Mapping[str, Any], body: str) -> str:
    """Render a memory entry as front matter plus markdown body.

    The front matter is deliberately flat (scalars and lists of scalars) so it
    stays readable without a YAML parser and diffable line by line.
    """
    lines = ["---"]
    for key, value in metadata.items():
        if value is None or value == "" or (isinstance(value, (list, tuple)) and not value):
            continue
        if isinstance(value, (list, tuple)):
            lines.append(f"{key}:")
            lines.extend(f"  - {_scalar(item)}" for item in value)
        else:
            lines.append(f"{key}: {_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.strip() + "\n"


def parse_front_matter(content: str) -> dict[str, Any]:
    """Read back the flat front matter written by :func:`render_entry`."""
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---", 4)
    if end < 0:
        return {}
    result: dict[str, Any] = {}
    current_list: str | None = None
    for line in content[4:end].splitlines():
        if line.startswith("  - ") and current_list is not None:
            result[current_list].append(_unscalar(line[4:]))
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if not key:
            continue
        if value.strip() == "":
            result[key] = []
            current_list = key
        else:
            result[key] = _unscalar(value.strip())
            current_list = None
    return result


def _scalar(value: Any) -> str:
    text = str(value)
    if text == "" or any(ch in text for ch in ":#\n\"'") or text != text.strip():
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return text


def _unscalar(text: str) -> Any:
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1].replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    return text


class MemoryStore:
    """Append-only, content-addressed memory entries chained into an audit ledger."""

    def __init__(self, root: Path, ledger: AuditLedger | None = None):
        self.root = Path(root)
        self.ledger = ledger or AuditLedger(self.root / "ledger.jsonl")

    @property
    def entries_dir(self) -> Path:
        return self.root / "entries"

    @property
    def objects_dir(self) -> Path:
        return self.root / "objects"

    def _entry_path(self, path: str) -> Path:
        return self.entries_dir / self._normalize(path)

    def _object_path(self, sha256: str) -> Path:
        return self.objects_dir / f"{sha256}.md"

    @staticmethod
    def _normalize(path: str) -> str:
        parts = [segment for segment in path.replace("\\", "/").split("/") if segment and segment != "."]
        if not parts or any(segment == ".." for segment in parts):
            raise MemoryStoreError(f"invalid memory path: {path!r}")
        normalized = "/".join(parts)
        return normalized if normalized.endswith(".md") else normalized + ".md"

    # -- reads -----------------------------------------------------------------

    def versions(self) -> list[MemoryVersion]:
        redacted = {
            event["payload"]["version_id"]
            for event in self.ledger.events()
            if event["event_type"] == MEMORY_REDACTION_EVENT
        }
        return [
            MemoryVersion(
                version_id=event["event_id"],
                path=event["payload"]["path"],
                operation=event["payload"]["operation"],
                content_sha256=event["payload"].get("content_sha256"),
                actor=event["actor"],
                recorded_at=event["recorded_at"],
                redacted=event["event_id"] in redacted,
            )
            for event in self.ledger.events()
            if event["event_type"] == MEMORY_VERSION_EVENT
        ]

    def history(self, path: str) -> list[MemoryVersion]:
        normalized = self._normalize(path)
        return [version for version in self.versions() if version.path == normalized]

    def head(self, path: str) -> MemoryVersion | None:
        history = self.history(path)
        return history[-1] if history else None

    def read(self, path: str) -> str | None:
        version = self.head(path)
        if version is None or version.operation == "deleted" or version.redacted:
            return None
        return self._read_object(version.content_sha256)

    def read_version(self, version_id: str) -> str | None:
        for version in self.versions():
            if version.version_id == version_id:
                if version.redacted or version.content_sha256 is None:
                    return None
                return self._read_object(version.content_sha256)
        raise MemoryStoreError(f"unknown memory version: {version_id!r}")

    def paths(self) -> list[str]:
        live: dict[str, bool] = {}
        for version in self.versions():
            live[version.path] = version.operation != "deleted"
        return sorted(path for path, alive in live.items() if alive)

    def _read_object(self, sha256: str | None) -> str | None:
        if sha256 is None:
            return None
        object_path = self._object_path(sha256)
        if not object_path.exists():
            raise AuditIntegrityError(f"memory object {sha256} is missing")
        return object_path.read_text(encoding="utf-8")

    # -- writes ----------------------------------------------------------------

    def write(
        self,
        path: str,
        content: str,
        actor: str,
        expected_sha256: str | None = None,
    ) -> MemoryVersion:
        if not actor.strip():
            raise MemoryStoreError("actor is required")
        if len(content.encode("utf-8")) > MAX_ENTRY_BYTES:
            raise MemoryStoreError("memory entries must stay small; split the entry")
        normalized = self._normalize(path)
        previous = self.head(normalized)
        previous_sha = previous.content_sha256 if previous and previous.operation != "deleted" else None
        if expected_sha256 is not None and expected_sha256 != previous_sha:
            raise MemoryConflictError(f"{normalized} has changed; expected {expected_sha256}, found {previous_sha}")
        sha256 = content_sha256(content)
        operation = "created" if previous_sha is None else "modified"
        self._store_object(sha256, content)
        event = self.ledger.append(
            MEMORY_VERSION_EVENT,
            actor.strip(),
            {
                "path": normalized,
                "operation": operation,
                "content_sha256": sha256,
                "previous_sha256": previous_sha,
            },
        )
        entry_path = self._entry_path(normalized)
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text(content, encoding="utf-8")
        return MemoryVersion(event["event_id"], normalized, operation, sha256, event["actor"], event["recorded_at"])

    def delete(self, path: str, actor: str) -> MemoryVersion:
        normalized = self._normalize(path)
        previous = self.head(normalized)
        if previous is None or previous.operation == "deleted":
            raise MemoryStoreError(f"nothing to delete at {normalized}")
        event = self.ledger.append(
            MEMORY_VERSION_EVENT,
            actor.strip(),
            {"path": normalized, "operation": "deleted", "content_sha256": None, "previous_sha256": previous.content_sha256},
        )
        entry_path = self._entry_path(normalized)
        if entry_path.exists():
            entry_path.unlink()
        return MemoryVersion(event["event_id"], normalized, "deleted", None, event["actor"], event["recorded_at"])

    def redact(self, version_id: str, actor: str, reason: str) -> None:
        """Scrub a version's content while keeping who wrote what, and when."""
        if not reason.strip():
            raise MemoryStoreError("a redaction reason is required")
        target = next((version for version in self.versions() if version.version_id == version_id), None)
        if target is None:
            raise MemoryStoreError(f"unknown memory version: {version_id!r}")
        if target.redacted:
            return
        self.ledger.append(
            MEMORY_REDACTION_EVENT,
            actor.strip(),
            {"version_id": version_id, "path": target.path, "reason": reason.strip()},
        )
        if target.content_sha256 is not None:
            still_referenced = any(
                version.content_sha256 == target.content_sha256
                and version.version_id != version_id
                and not version.redacted
                for version in self.versions()
            )
            if not still_referenced:
                self._object_path(target.content_sha256).write_text(REDACTED_MARKER, encoding="utf-8")
        head = self.head(target.path)
        if head is not None and head.version_id == version_id:
            entry_path = self._entry_path(target.path)
            if entry_path.exists():
                entry_path.unlink()

    def _store_object(self, sha256: str, content: str) -> None:
        object_path = self._object_path(sha256)
        if object_path.exists():
            existing = object_path.read_text(encoding="utf-8")
            if existing != content and existing != REDACTED_MARKER:
                raise AuditIntegrityError(f"memory object {sha256} does not match its hash")
            return
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_text(content, encoding="utf-8")

    # -- integrity -------------------------------------------------------------

    def verify(self) -> int:
        """Verify the ledger chain, every object hash, and every head projection.

        Returns the number of versions checked. Raises ``AuditIntegrityError``
        on the first inconsistency.
        """
        self.ledger.verify()
        versions = self.versions()
        heads: dict[str, MemoryVersion] = {}
        for version in versions:
            heads[version.path] = version
            if version.operation == "deleted" or version.redacted or version.content_sha256 is None:
                continue
            content = self._read_object(version.content_sha256)
            if content_sha256(content or "") != version.content_sha256:
                raise AuditIntegrityError(f"memory object {version.content_sha256} does not match its hash")
        for path, version in heads.items():
            entry_path = self._entry_path(path)
            if version.operation == "deleted" or version.redacted:
                if entry_path.exists():
                    raise AuditIntegrityError(f"{path} should not have a head projection")
                continue
            if not entry_path.exists():
                raise AuditIntegrityError(f"{path} head projection is missing")
            if content_sha256(entry_path.read_text(encoding="utf-8")) != version.content_sha256:
                raise AuditIntegrityError(f"{path} head projection was edited outside the ledger")
        return len(versions)

    def rebuild_projection(self) -> int:
        """Recreate ``entries/`` from the ledger and objects. Returns paths written."""
        if self.entries_dir.exists():
            for file in sorted(self.entries_dir.rglob("*.md"), reverse=True):
                file.unlink()
        written = 0
        for path in self.paths():
            content = self.read(path)
            if content is None:
                continue
            entry_path = self._entry_path(path)
            entry_path.parent.mkdir(parents=True, exist_ok=True)
            entry_path.write_text(content, encoding="utf-8")
            written += 1
        return written
