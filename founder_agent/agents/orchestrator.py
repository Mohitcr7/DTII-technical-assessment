"""Parent agent: plan, delegate, compose, and stop at the authorization line.

The orchestrator is the only component that may prepare a consequential action,
and even it cannot execute one. Its planner is fed the user's question and
structural retrieval metadata (document ids, epistemic labels, scores) - never
document text - so no sentence inside the corpus can cause an agent to be
spawned or a tool to be chosen.
"""

from __future__ import annotations

import re

from ..audit import AuditLog, new_trace_id
from ..authorization import ActionGateway, Principal
from ..contradictions import ContradictionDetector
from ..decisions import DecisionLedger
from ..knowledge import KnowledgeService
from ..llm.registry import ProviderRegistry
from ..retrieval import ClaimIndex
from ..schemas import (
    ActionRequest,
    Claim,
    ClaimType,
    DelegationRequest,
    DelegationResult,
    FounderResponse,
    Plan,
    PlanStep,
)
from .base import SubAgent
from .redteam import RedTeamAgent
from .research import ResearchAgent
from .technical import TechnicalAgent

_PROPOSAL = re.compile(
    r"\b(should we|can we|shall we|propose|proposal|switch|migrate|move to|add a|adopt|"
    r"drop|replace|consolidat|wind down|start using|stop using)\b", re.I)
_DECISION_Q = re.compile(
    r"\b(have we decided|did we decide|what.s our (policy|decision)|is there a decision|"
    r"what did we decide|are we allowed|governing|policy on)\b", re.I)
_ACTION_Q = re.compile(
    r"\b(send|email|notify|tell|inform|draft and send|write to)\b.{0,40}"
    r"\b(bank|customer|partner|institution|northbridge|halcyon|regulator)\b", re.I)
_TECHNICAL_TOPICS = {"api", "auth", "oauth", "rate-limit", "signing", "ecdsa", "hsm",
                     "latency", "region", "throughput", "protocol", "logging", "retention"}


class Orchestrator:
    def __init__(
        self,
        index: ClaimIndex,
        ledger: DecisionLedger,
        knowledge: KnowledgeService,
        detector: ContradictionDetector,
        registry: ProviderRegistry,
        audit: AuditLog,
        gateway: ActionGateway,
    ) -> None:
        self.index = index
        self.ledger = ledger
        self.knowledge = knowledge
        self.detector = detector
        self.registry = registry
        self.audit = audit
        self.gateway = gateway
        self.claims: list[Claim] = index.claims
        self.subagents: dict[str, SubAgent] = {
            "research": ResearchAgent(registry, audit, ledger),
            "redteam": RedTeamAgent(registry, audit, ledger),
            "technical": TechnicalAgent(registry, audit, ledger),
        }
        self._clusters = detector.cluster()

    # ------------------------------------------------------------------
    def ask(self, question: str, *, principal: Principal | None = None,
            prepare_action: bool = False) -> FounderResponse:
        principal = principal or Principal(kind="human", id="founder")
        trace_id = new_trace_id()
        self.audit.record("user_request", trace_id=trace_id, actor=principal.id,
                          payload={"question": question, "prepare_action": prepare_action})

        answer = self.knowledge.answer(question, trace_id=trace_id)
        self.audit.record("retrieval", trace_id=trace_id, actor="retrieval", payload={
            "query": question,
            "claim_ids": [e.claim_id for e in answer.evidence],
            "scores": [e.score for e in answer.evidence],
            "types": [e.claim_type.value for e in answer.evidence],
        })

        self.audit.record("model_call", trace_id=trace_id, actor="knowledge_service", payload={
            "role": "reason",
            "provider": answer.provider,
            "model": answer.model,
            "tokens_used": answer.tokens_used,
            "degraded": answer.provider == "deterministic",
            "purpose": "answer synthesis",
        })

        plan = self._plan(question, answer, prepare_action)
        self.audit.record("plan", trace_id=trace_id, actor="orchestrator",
                          payload=plan.model_dump())

        decision = None
        if plan.intent in {"decision_check", "proposal_review", "action_request"}:
            decision = self.ledger.lookup(
                question, [e.doc_id for e in answer.evidence])
            decision.trace_id = trace_id

        delegations: list[DelegationResult] = []
        for step in plan.steps:
            agent = self.subagents.get(step.agent)
            if agent is None:
                continue
            result = agent.run(
                DelegationRequest(
                    parent_trace_id=trace_id,
                    agent=step.agent,
                    task=question,
                    context_claim_ids=step.context_claim_ids,
                    budget_tokens=900,
                    granted_tools=["corpus.search"],
                ),
                self.claims,
            )
            delegations.append(result)

        clusters = self._relevant_clusters(answer)
        action = None
        if prepare_action or plan.intent == "action_request":
            action = self._prepare_consequential_action(question, answer, trace_id, principal)

        provider = self.registry.active_provider("reason")
        response = FounderResponse(
            question=question, trace_id=trace_id, plan=plan, answer=answer,
            decision=decision, contradictions=clusters, delegations=delegations,
            pending_action=action, provider=provider, degraded=(provider == "deterministic"),
        )
        self.audit.record("response", trace_id=trace_id, actor="orchestrator", payload={
            "verdict": answer.verdict,
            "citations": [c for s in answer.segments for c in s.citations],
            "governing_decision": decision.governing.doc_id if decision and decision.governing else None,
            "contradiction_clusters": [c.cluster_id for c in clusters],
            "delegated_to": [d.agent for d in delegations],
            "pending_action": action.action_id if action else None,
            "provider": provider,
        })
        return response

    # ------------------------------------------------------------------
    def _plan(self, question: str, answer, prepare_action: bool) -> Plan:
        # Structural metadata only. Note that nothing below reads claim text.
        doc_ids = {e.doc_id for e in answer.evidence}
        topics = {t for e in answer.evidence
                  for c in self.claims if c.claim_id == e.claim_id for t in c.topics}
        has_decision_evidence = any(e.claim_type is ClaimType.DECISION for e in answer.evidence)
        evidence_ids = [e.claim_id for e in answer.evidence]

        if prepare_action or _ACTION_Q.search(question):
            intent = "action_request"
        elif _PROPOSAL.search(question):
            intent = "proposal_review"
        elif _DECISION_Q.search(question) or has_decision_evidence:
            intent = "decision_check"
        else:
            intent = "lookup"

        steps: list[PlanStep] = []
        if intent in {"proposal_review", "action_request"}:
            steps.append(PlanStep(
                agent="redteam",
                reason="A proposal must be attacked before it is reported as viable.",
                context_claim_ids=evidence_ids))
        if len(doc_ids) >= 3 or intent in {"decision_check", "proposal_review"}:
            steps.append(PlanStep(
                agent="research",
                reason=f"Evidence spans {len(doc_ids)} documents; organise it by epistemic type.",
                context_claim_ids=evidence_ids))
        if topics & _TECHNICAL_TOPICS:
            steps.append(PlanStep(
                agent="technical",
                reason=f"Retrieved material carries technical topics "
                       f"({sorted(topics & _TECHNICAL_TOPICS)[:4]}).",
                context_claim_ids=evidence_ids))

        return Plan(
            intent=intent, steps=steps,
            rationale=(f"Intent '{intent}' from the user's own wording and retrieval structure "
                       f"({len(evidence_ids)} claims across {len(doc_ids)} documents, "
                       f"decision-grade evidence: {has_decision_evidence}). "
                       f"Document text was not consulted for routing."),
        )

    def _relevant_clusters(self, answer):
        touched = {e.doc_id for e in answer.evidence}
        return [c for c in self._clusters if touched & set(c.documents)]

    # ------------------------------------------------------------------
    def _prepare_consequential_action(
        self, question: str, answer, trace_id: str, principal: Principal
    ) -> ActionRequest | None:
        """Compose the outbound message and stop. Execution needs a human."""
        governing = self.ledger.lookup(question, [e.doc_id for e in answer.evidence])
        citations = [e.claim_id for e in answer.evidence[:5]]

        body_lines = [
            "Dear Northbridge Bank compliance team,",
            "",
            "Per our pilot agreement, this note summarises the current position of record at "
            "Veritas Chain Technologies:",
            "",
        ]
        body_lines += [f"  - {e.text}  [source: {e.doc_id}]" for e in answer.evidence[:4]]
        body_lines += ["", "Regards,", "Veritas Chain Technologies"]

        warnings: list[str] = []
        if governing.governing and governing.governing.contested_by:
            warnings.append(
                f"The governing decision {governing.governing.doc_id} is contested by "
                f"{', '.join(governing.governing.contested_by)}; the statement below may not "
                f"reflect production reality.")
        stale = [e.claim_id for e in answer.evidence[:4] if e.caveat]
        if stale:
            warnings.append(f"Draft cites material with caveats: {', '.join(stale)}.")
        if answer.verdict != "ANSWERED":
            warnings.append(f"Underlying answer is {answer.verdict}; the draft may overstate.")

        payload = {
            "to": "compliance@northbridge.example",
            "subject": "Veritas Chain - position of record",
            "body": "\n".join(body_lines),
            "requested_for": question,
        }
        return self.gateway.prepare(
            principal=Principal(kind="agent", id="founder_agent.orchestrator"),
            tool="external_email.send",
            intent=(f"Send an external email to compliance@northbridge.example summarising the "
                    f"position of record in response to: \"{question}\". Irreversible once sent."),
            payload=payload,
            trace_id=trace_id,
            supporting_claim_ids=citations,
            warnings=warnings,
            role="orchestrator",
        )
