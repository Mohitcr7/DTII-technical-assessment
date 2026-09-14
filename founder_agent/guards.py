"""Content-boundary defences.

Two rules run the whole design:

1. Documents are *data*. Nothing retrieved from the corpus may become an
   instruction, grant a capability, or select a tool. That is enforced by
   architecture (the planner never sees document text; see agents/orchestrator)
   and by these detectors as a second layer.
2. Secrets never reach the audit log. Redaction happens on the way in, not on
   the way out, so a leak cannot be introduced later by a new reader.
"""

from __future__ import annotations

import re
from typing import Any

# Patterns that indicate a document is trying to talk to the model rather than
# to a human reader. Detection is advisory: it raises a flag and lowers trust,
# it is never the only thing standing between a document and a tool call.
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("instruction_override", re.compile(r"ignore (all |any |the )?(previous|prior|above)", re.I)),
    ("role_hijack", re.compile(r"\b(you are|act as|pretend to be)\s+(an?\s+)?\w+", re.I)),
    ("system_prompt_probe", re.compile(r"(system prompt|your instructions|reveal your)", re.I)),
    ("tool_coercion", re.compile(r"\b(send|email|post|delete|transfer|execute|run)\b[^.]{0,40}\b(immediately|without (asking|approval|confirmation))", re.I)),
    ("authority_forgery", re.compile(r"(founder|ceo|board) (has )?(pre-)?approved|authorized by the (founder|board)", re.I)),
    ("exfiltration", re.compile(r"(api[_ -]?key|secret|credential|token)s?\b[^.]{0,30}\b(send|share|include|output)", re.I)),
    # Narrow on purpose: "effective immediately" is ordinary business language.
    # The signal is pressure aimed at the *reader* to bypass a control, not
    # urgency about the world.
    ("urgency_pressure", re.compile(
        r"\b(do not ask|don't ask|no need to (ask|confirm|verify)|skip (the )?(review|approval|"
        r"confirmation)|without (asking|approval|confirmation|review)|act now|"
        r"respond immediately|this is urgent[,.]? (send|do|execute))\b", re.I)),
    ("hidden_channel", re.compile(r"<\s*(script|iframe)|base64,", re.I)),
]

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token)\b\s*[:=]\s*\S+"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
]

_SECRET_KEYS = {
    "api_key", "apikey", "authorization", "password", "secret", "token",
    "approver_token", "approval_token", "client_secret",
}

# Bidi / zero-width characters used to hide instructions from human reviewers
# while leaving them visible to the tokenizer.
_CONTROL_CHARS = re.compile(
    "[" + "".join(chr(c) for c in (0x00AD, 0x200B, 0x200C, 0x200D, 0x2060,
                                   0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                                   0xFEFF)) + "]"
)


def scan_for_injection(text: str) -> list[str]:
    """Return the names of injection heuristics that fired on `text`."""
    flags = [name for name, pat in _INJECTION_PATTERNS if pat.search(text)]
    if _CONTROL_CHARS.search(text):
        flags.append("hidden_characters")
    return flags


def redact_text(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def redact(value: Any) -> Any:
    """Recursively strip secrets from anything bound for the audit log."""
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if k.lower() in _SECRET_KEYS else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def wrap_untrusted(claim_id: str, text: str) -> str:
    """Render corpus text for a prompt with an explicit trust boundary.

    Delimiters alone do not stop injection - a determined document can emit the
    closing delimiter. They exist so the model has a consistent signal, while
    the real protection stays in the capability model.
    """
    safe = strip_control_chars(text).replace("</untrusted_document>", "[/]")
    return f'<untrusted_document id="{claim_id}">\n{safe}\n</untrusted_document>'


def strip_control_chars(text: str) -> str:
    return _CONTROL_CHARS.sub("", text)
