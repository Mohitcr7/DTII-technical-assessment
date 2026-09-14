"""Append-only, hash-chained audit log.

Each record commits to its predecessor, so silently rewriting history requires
rewriting every later line - the tamper becomes detectable with `verify()`
rather than invisible. This is the control that answers "historical-record
alteration" in the threat model; the log is written before the action it
describes is allowed to proceed.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .guards import redact

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # -- writing ---------------------------------------------------------
    def record(
        self,
        event: str,
        *,
        trace_id: str,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            prev_hash, seq = self._tail()
            entry = {
                "seq": seq + 1,
                "ts": datetime.now(timezone.utc).isoformat(),
                "trace_id": trace_id,
                "actor": actor,
                "event": event,
                "payload": redact(payload or {}),
                "prev_hash": prev_hash,
            }
            entry["hash"] = self._hash(entry)
            line = json.dumps(entry, sort_keys=True, default=str)
            # Durability matters here: an action must not be able to execute
            # because its audit write was still sitting in a buffer.
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return entry

    @staticmethod
    def _hash(entry: dict[str, Any]) -> str:
        material = {k: v for k, v in entry.items() if k != "hash"}
        blob = json.dumps(material, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _tail(self) -> tuple[str, int]:
        if not self.path.exists():
            return GENESIS, 0
        last = None
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if last is None:
            return GENESIS, 0
        rec = json.loads(last)
        return rec["hash"], int(rec["seq"])

    # -- reading ---------------------------------------------------------
    def entries(self, trace_id: str | None = None) -> list[dict[str, Any]]:
        return [e for e in self._iter() if trace_id is None or e.get("trace_id") == trace_id]

    def _iter(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return iter(())
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)

    def verify(self) -> dict[str, Any]:
        """Recompute the chain. Returns the first break, if any."""
        prev = GENESIS
        count = 0
        for entry in self._iter():
            count += 1
            if entry.get("prev_hash") != prev:
                return {"ok": False, "broken_at": entry.get("seq"), "reason": "prev_hash mismatch",
                        "records": count}
            if self._hash(entry) != entry.get("hash"):
                return {"ok": False, "broken_at": entry.get("seq"), "reason": "content hash mismatch",
                        "records": count}
            prev = entry["hash"]
        return {"ok": True, "records": count, "head": prev}

    def reconstruct(self, trace_id: str) -> dict[str, Any]:
        """Everything needed to replay one interaction (assessment 2.7)."""
        events = self.entries(trace_id)
        by = lambda name: [e for e in events if e["event"] == name]  # noqa: E731
        return {
            "trace_id": trace_id,
            "event_count": len(events),
            "user_request": next((e["payload"] for e in by("user_request")), None),
            "retrieved_context": [e["payload"] for e in by("retrieval")],
            "models_used": [e["payload"] for e in by("model_call")],
            "delegations": [e["payload"] for e in by("delegation")],
            "tools_requested": [e["payload"] for e in by("action_prepared")],
            "human_decisions": [e["payload"] for e in by("action_approved") + by("action_denied")],
            "resulting_actions": [e["payload"] for e in by("action_executed")],
            "outputs": [e["payload"] for e in by("response")],
            "timeline": events,
        }


def new_trace_id() -> str:
    return f"tr_{uuid.uuid4().hex[:16]}"
