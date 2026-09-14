"""Provider-neutral model interface.

The rest of the system asks for a *role* ("reason", "extract", "research",
"redteam"), never for a vendor. Swapping Anthropic for OpenAI, or adding a
local model, means registering one class here - no call site changes. See
docs/ARCHITECTURE.md section 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Message:
    role: str            # "user" | "assistant"
    content: str


@dataclass
class LLMRequest:
    system: str
    messages: list[Message]
    max_tokens: int = 1024
    temperature: float = 0.0
    #: When set, the provider must return JSON conforming to this shape.
    json_schema: dict[str, Any] | None = None
    #: Tool names the caller is permitted to use. Providers must not invent
    #: tools outside this list; the executor rejects anything else regardless.
    allowed_tools: list[str] = field(default_factory=list)


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "end_turn"
    structured: dict[str, Any] | None = None
    degraded: bool = False        # True when a fallback provider served this
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool:
        """Cheap, non-network check: is this provider usable right now?"""

    def complete(self, request: LLMRequest) -> LLMResponse:
        ...


class ProviderError(RuntimeError):
    pass
