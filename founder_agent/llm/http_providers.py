"""Hosted providers over plain HTTP (no vendor SDK, so no dependency drift).

Both classes implement the same `LLMProvider` protocol as the offline
provider. Credentials are read from the environment at call time and never
logged, never placed in a prompt, and never returned to a caller.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .base import LLMRequest, LLMResponse

_TIMEOUT = httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0)


def _schema_instruction(schema: dict[str, Any] | None) -> str:
    if not schema:
        return ""
    return (
        "\n\nReturn ONLY a JSON object matching this schema, no prose, no code fence:\n"
        + json.dumps(schema)
    )


#: Models that accept `output_config.effort`. Haiku 4.5 and older models return
#: 400 on it, so the knob is only sent where the model understands it.
_EFFORT_CAPABLE = ("claude-opus-5", "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8",
                   "claude-sonnet-5", "claude-sonnet-4-6", "claude-fable-")


def _supports_effort(model: str) -> bool:
    return model.startswith(_EFFORT_CAPABLE)


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


class AnthropicProvider:
    """Messages API over plain HTTP.

    Request shape follows the current API: no sampling parameters (rejected by
    Claude Opus 5 / Sonnet 5), thinking left at the model's adaptive default,
    depth steered through `output_config.effort`. A `refusal` stop reason is
    surfaced as an error so the router can fail over rather than hand an
    empty answer to the caller.
    """

    name = "anthropic"

    def __init__(self, model: str = "claude-haiku-4-5") -> None:
        self.model = model

    def available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, request: LLMRequest) -> LLMResponse:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return LLMResponse("", self.name, self.model, error="missing ANTHROPIC_API_KEY")
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": request.system + _schema_instruction(request.json_schema),
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.effort and _supports_effort(self.model):
            body["output_config"] = {"effort": request.effort}
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:  # noqa: BLE001 - surfaced to the router as a failure
            return LLMResponse("", self.name, self.model, error=f"{type(exc).__name__}: {exc}")

        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        stop = data.get("stop_reason", "end_turn")
        if stop == "refusal":
            details = data.get("stop_details") or {}
            return LLMResponse("", self.name, data.get("model", self.model),
                               stop_reason=stop,
                               error=f"model refused ({details.get('category')})")
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model", self.model),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            stop_reason=stop,
            structured=_extract_json(text) if request.json_schema else None,
        )


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str = "gpt-4.1") -> None:
        self.model = model

    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def complete(self, request: LLMRequest) -> LLMResponse:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            return LLMResponse("", self.name, self.model, error="missing OPENAI_API_KEY")
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "system", "content": request.system + _schema_instruction(request.json_schema)}]
            + [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.json_schema:
            body["response_format"] = {"type": "json_object"}
        try:
            r = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
                json=body,
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            return LLMResponse("", self.name, self.model, error=f"{type(exc).__name__}: {exc}")

        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content", "") or ""
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model", self.model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=choice.get("finish_reason", "stop"),
            structured=_extract_json(text) if request.json_schema else None,
        )
