"""Offline provider: always available, never calls the network.

Its job is not to be smart. It is the floor under the system - the prototype
must answer, cite, classify, detect contradictions and refuse unsafe actions
with no API key and no connectivity, because all of that logic lives in code
rather than in a prompt. When a hosted provider is configured it produces
better prose; it does not produce different governance.
"""

from __future__ import annotations

import json
import re

from .base import LLMRequest, LLMResponse


class DeterministicProvider:
    name = "deterministic"
    model = "rule-engine-v1"

    def available(self) -> bool:
        return True

    def complete(self, request: LLMRequest) -> LLMResponse:
        payload = request.messages[-1].content if request.messages else ""
        text = self._respond(request.system, payload)
        structured = None
        if request.json_schema is not None:
            structured = self._structured(request.system, payload)
            text = json.dumps(structured)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=len(payload.split()),
            output_tokens=len(text.split()),
            structured=structured,
            degraded=True,
        )

    # The deterministic provider only ever *summarises* material it was given.
    # It cannot introduce a claim that was not in its input, which is exactly
    # the property we want from the no-key path.
    def _respond(self, system: str, payload: str) -> str:
        quoted = re.findall(r"<untrusted_document id=\"([^\"]+)\">\n(.*?)\n</untrusted_document>",
                            payload, re.DOTALL)
        if not quoted:
            return "No supporting material was supplied, so no answer can be grounded."
        lines = [f"{text.strip()} [{cid}]" for cid, text in quoted[:4]]
        return " ".join(lines)

    def _structured(self, system: str, payload: str) -> dict:
        return {
            "summary": self._respond(system, payload),
            "findings": [],
            "confidence": 0.4,
            "note": "deterministic fallback - structural analysis performed in code, not by a model",
        }
