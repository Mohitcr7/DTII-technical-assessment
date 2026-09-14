"""Runtime configuration. Everything is env-overridable; nothing is hardcoded
to a single model vendor."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    corpus_dir: Path = ROOT / "corpus"
    audit_path: Path = ROOT / "var" / "audit.jsonl"
    actions_path: Path = ROOT / "var" / "actions.jsonl"

    # Retrieval
    top_k: int = _env_int("FA_TOP_K", 8)
    #: Below this best-score the system answers UNKNOWN rather than guessing.
    min_evidence_score: float = _env_float("FA_MIN_EVIDENCE", 1.2)

    # Routing: task role -> provider preference order.
    role_routing: dict[str, list[str]] = field(default_factory=lambda: {
        "reason": _split(os.environ.get("FA_ROUTE_REASON", "anthropic,openai,deterministic")),
        "extract": _split(os.environ.get("FA_ROUTE_EXTRACT", "anthropic,openai,deterministic")),
        "research": _split(os.environ.get("FA_ROUTE_RESEARCH", "anthropic,openai,deterministic")),
        "redteam": _split(os.environ.get("FA_ROUTE_REDTEAM", "anthropic,openai,deterministic")),
    })

    anthropic_model: str = os.environ.get("FA_ANTHROPIC_MODEL", "claude-haiku-4-5")
    openai_model: str = os.environ.get("FA_OPENAI_MODEL", "gpt-4.1")

    # Human authorization
    action_ttl_seconds: int = _env_int("FA_ACTION_TTL", 900)
    #: Shared secret that the *human* console must present. An agent process
    #: never receives this value; see docs/THREAT_MODEL.md.
    approver_token: str = os.environ.get("FA_APPROVER_TOKEN", "dev-human-console-token")

    # Guards
    max_delegation_depth: int = _env_int("FA_MAX_DEPTH", 2)
    subagent_token_budget: int = _env_int("FA_SUBAGENT_BUDGET", 4000)

    def ensure_dirs(self) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)


def _split(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


settings = Settings()
settings.ensure_dirs()
