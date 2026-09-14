"""Capability-scoped tool registry.

Every tool declares its blast radius up front. Two rules follow from that and
are enforced here rather than in prompts:

* A caller may only invoke tools its role was granted. A subordinate agent that
  was never granted `external_email.send` cannot call it however it is
  persuaded to behave.
* A tool marked `requires_human_approval` has no code path that executes it
  directly. It can only be *prepared*; execution runs through
  `authorization.ActionGateway`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk: Literal["low", "medium", "high", "consequential"]
    side_effecting: bool
    requires_human_approval: bool
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    #: Roles permitted to request this tool at all.
    allowed_roles: frozenset[str] = field(default_factory=frozenset)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names_for(self, role: str) -> list[str]:
        return sorted(n for n, t in self._tools.items() if role in t.allowed_roles)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def authorize_call(self, role: str, name: str) -> tuple[bool, str]:
        """Can `role` even ask for this tool? Checked before anything runs."""
        spec = self._tools.get(name)
        if spec is None:
            return False, f"unknown tool '{name}'"
        if role not in spec.allowed_roles:
            return False, (f"role '{role}' is not granted '{name}' "
                           f"(granted: {sorted(spec.allowed_roles)})")
        return True, "ok"


class ToolPermissionError(PermissionError):
    pass
