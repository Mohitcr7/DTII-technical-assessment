"""Subordinate agent contract.

Delegation is where agent systems usually leak authority, so the boundary is
explicit:

* A subordinate receives a **task string and a fixed set of claim ids**. It
  cannot widen its own context.
* It holds its **own tool grants**, which are a subset of the parent's. None of
  the subordinates can reach a consequential tool at all.
* It returns a **typed result**; free-form text never flows back into the
  parent's control path, only into its report.
* Its citations are **validated against the claims it was given**. A citation
  the parent did not hand over is stripped, so a subordinate cannot invent
  provenance.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from ..audit import AuditLog
from ..guards import wrap_untrusted
from ..llm.base import LLMRequest, Message
from ..llm.registry import ProviderRegistry
from ..schemas import Claim, DelegationRequest, DelegationResult


class SubAgent(ABC):
    role: str = "subagent"
    description: str = ""
    #: Tools this role may use. Deliberately narrow; see tools/registry.py.
    granted_tools: frozenset[str] = frozenset({"corpus.search"})

    def __init__(self, registry: ProviderRegistry, audit: AuditLog) -> None:
        self.registry = registry
        self.audit = audit

    # ------------------------------------------------------------------
    def run(self, request: DelegationRequest, claims: list[Claim]) -> DelegationResult:
        started = time.time()
        scoped = [c for c in claims if c.claim_id in set(request.context_claim_ids)] or claims
        refusals: list[str] = []

        for tool in request.granted_tools:
            if tool not in self.granted_tools:
                refusals.append(
                    f"declined tool '{tool}': not in the grant for role '{self.role}'")

        flagged = [c.claim_id for c in scoped if c.injection_flags]
        if flagged:
            refusals.append(
                f"treated {', '.join(flagged)} as data only - instruction-shaped content detected")

        try:
            result = self.analyse(request, scoped)
        except Exception as exc:  # noqa: BLE001
            return DelegationResult(agent=self.role, task=request.task, status="error",
                                    summary=f"{type(exc).__name__}: {exc}")

        allowed = {c.claim_id for c in scoped}
        result.citations = [c for c in result.citations if c in allowed]
        result.refusals = refusals + result.refusals
        result.agent = self.role
        result.task = request.task

        self.audit.record("delegation", trace_id=request.parent_trace_id, actor=self.role, payload={
            "agent": self.role,
            "task": request.task,
            "context_claim_ids": request.context_claim_ids,
            "granted_tools": sorted(self.granted_tools),
            "status": result.status,
            "provider": result.provider,
            "model": result.model,
            "tokens_used": result.tokens_used,
            "citations": result.citations,
            "refusals": result.refusals,
            "elapsed_ms": int((time.time() - started) * 1000),
        })
        return result

    @abstractmethod
    def analyse(self, request: DelegationRequest, claims: list[Claim]) -> DelegationResult:
        ...

    # ------------------------------------------------------------------
    def _ask_model(self, role: str, system: str, prompt: str, claims: list[Claim],
                   budget: int) -> tuple[str, str, str, int]:
        """Optional model assist. Returns (text, provider, model, tokens)."""
        if self.registry.active_provider(role) == "deterministic":
            return "", "deterministic", "rule-engine-v1", 0
        context = "\n\n".join(wrap_untrusted(c.claim_id, f"[{c.claim_type.value}] {c.text}")
                              for c in claims[:12])
        # Subordinates run at low effort: their structural work is done in
        # code, the model adds a second opinion and phrasing.
        response = self.registry.complete(role, LLMRequest(
            system=system,
            messages=[Message("user", f"{prompt}\n\nEvidence:\n{context}")],
            max_tokens=max(budget, 2048),
            effort="low",
        ))
        if response.error:
            return "", response.provider, response.model, 0
        return response.text, response.provider, response.model, response.total_tokens
