"""Role-based routing with failover.

Call sites ask for a capability, not a vendor:

    response = registry.complete("reason", request)

Routing order per role comes from config (env-overridable). A provider that
errors is tripped out for a cool-down window and the next one in the chain
serves the request; `deterministic` anchors every chain so the system degrades
instead of failing. Provider + model land in the audit record, so every answer
is attributable to what produced it.
"""

from __future__ import annotations

import time

from ..config import Settings, settings as default_settings
from .base import LLMProvider, LLMRequest, LLMResponse
from .deterministic import DeterministicProvider
from .http_providers import AnthropicProvider, OpenAIProvider

_COOLDOWN_SECONDS = 60


class ProviderRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self._providers: dict[str, LLMProvider] = {
            "anthropic": AnthropicProvider(self.settings.anthropic_model),
            "openai": OpenAIProvider(self.settings.openai_model),
            "deterministic": DeterministicProvider(),
        }
        self._tripped: dict[str, float] = {}

    def register(self, provider: LLMProvider) -> None:
        """Add a provider (local model, proxy, research service) at runtime."""
        self._providers[provider.name] = provider

    def chain(self, role: str) -> list[str]:
        order = list(self.settings.role_routing.get(role, ["deterministic"]))
        if "deterministic" not in order:
            order.append("deterministic")   # the floor is never removed
        return order

    def active_provider(self, role: str) -> str:
        for name in self.chain(role):
            p = self._providers.get(name)
            if p and p.available() and not self._is_tripped(name):
                return name
        return "deterministic"

    def complete(self, role: str, request: LLMRequest) -> LLMResponse:
        attempted: list[str] = []
        for name in self.chain(role):
            provider = self._providers.get(name)
            if provider is None or not provider.available() or self._is_tripped(name):
                continue
            attempted.append(name)
            response = provider.complete(request)
            if response.error is None:
                response.degraded = response.degraded or len(attempted) > 1
                return response
            self._trip(name)
        fallback = self._providers["deterministic"].complete(request)
        fallback.degraded = True
        fallback.error = f"all providers failed or unavailable; attempted={attempted}"
        return fallback

    def status(self) -> dict[str, dict]:
        return {
            name: {
                "available": p.available(),
                "model": getattr(p, "model", ""),
                "cooling_down": self._is_tripped(name),
            }
            for name, p in self._providers.items()
        }

    def _trip(self, name: str) -> None:
        self._tripped[name] = time.time() + _COOLDOWN_SECONDS

    def _is_tripped(self, name: str) -> bool:
        until = self._tripped.get(name)
        if until is None:
            return False
        if time.time() >= until:
            del self._tripped[name]
            return False
        return True
