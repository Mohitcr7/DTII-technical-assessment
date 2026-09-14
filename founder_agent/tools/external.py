"""Simulated outbound integrations.

Nothing here touches a real network. The point of the exercise is the control
path around a consequential action, so the executor records exactly what would
have been sent and to whom.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .registry import ToolRegistry, ToolSpec


def _send_external_email(payload: dict[str, Any]) -> dict[str, Any]:
    # Reached only after ActionGateway has verified human approval and that the
    # payload still hashes to the value the human saw.
    return {
        "simulated": True,
        "transport": "smtp-relay (simulated)",
        "to": payload.get("to"),
        "subject": payload.get("subject"),
        "body_chars": len(payload.get("body", "")),
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "message_id": f"<sim-{abs(hash(str(payload))) % 10**12}@veritaschain.invalid>",
    }


def _draft_document(payload: dict[str, Any]) -> dict[str, Any]:
    return {"simulated": True, "kind": payload.get("kind"), "chars": len(payload.get("body", ""))}


def _search_corpus_stub(payload: dict[str, Any]) -> dict[str, Any]:
    # Real implementation is injected by the orchestrator, which owns the index.
    return {"error": "corpus search is bound at runtime"}


def register_default_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(ToolSpec(
        name="corpus.search",
        description="Search the internal document corpus. Read-only.",
        risk="low",
        side_effecting=False,
        requires_human_approval=False,
        handler=_search_corpus_stub,
        allowed_roles=frozenset({"orchestrator", "research", "technical", "redteam"}),
    ))
    registry.register(ToolSpec(
        name="document.draft",
        description="Compose a document for human review. Produces text only.",
        risk="low",
        side_effecting=False,
        requires_human_approval=False,
        handler=_draft_document,
        allowed_roles=frozenset({"orchestrator"}),
    ))
    registry.register(ToolSpec(
        name="external_email.send",
        description="Send an email to an external institution. Consequential and irreversible.",
        risk="consequential",
        side_effecting=True,
        requires_human_approval=True,
        handler=_send_external_email,
        # Only the orchestrator may *prepare* it. No subordinate agent can.
        allowed_roles=frozenset({"orchestrator"}),
    ))
    return registry
