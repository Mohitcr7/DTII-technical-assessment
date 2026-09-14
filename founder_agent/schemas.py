"""Typed contracts shared by every layer.

Design note: the epistemic label (`ClaimType`) is carried as *data* from
ingestion through retrieval, answering and rendering.  Nothing in the pipeline
is allowed to upgrade a HYPOTHESIS into a FACT, because no component ever gets
the raw string without its label attached.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date as Date, datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Epistemic classification (assessment §2.4)
# --------------------------------------------------------------------------
class ClaimType(str, Enum):
    FACT = "FACT"              # verifiable state of the world, asserted plainly
    INFERENCE = "INFERENCE"    # conclusion drawn from evidence, hedged/derived
    HYPOTHESIS = "HYPOTHESIS"  # explicitly unvalidated / suspected
    DECISION = "DECISION"      # an institutional choice that governs behaviour
    UNKNOWN = "UNKNOWN"        # not determinable from supplied material


#: A FACT-grade assertion may only rest on these. Enforced in `grounding.py`.
FACTUAL_SUPPORT = {ClaimType.FACT, ClaimType.DECISION}


class DecisionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CONTESTED = "CONTESTED"          # a later doc conflicts, resolution unclear
    INFORMAL = "INFORMAL"            # change enacted without a decision record
    PROPOSED = "PROPOSED"            # recommended, explicitly not yet decided


class Authority(str, Enum):
    BOARD = "board"
    FOUNDER = "founder"
    ENGINEERING = "engineering"
    FINANCE = "finance"
    COMPLIANCE = "compliance"
    EXTERNAL = "external"


#: Who outranks whom when two records conflict and both are current.
AUTHORITY_RANK: dict[str, int] = {
    Authority.BOARD: 100,
    Authority.FOUNDER: 80,
    Authority.COMPLIANCE: 60,
    Authority.FINANCE: 50,
    Authority.ENGINEERING: 40,
    Authority.EXTERNAL: 10,
}


# --------------------------------------------------------------------------
# Corpus primitives
# --------------------------------------------------------------------------
class Claim(BaseModel):
    """The atomic unit of retrieval and citation."""

    claim_id: str                      # e.g. "DOC-02#c1"
    doc_id: str
    ordinal: int
    text: str
    claim_type: ClaimType
    type_reason: str                   # why the classifier landed here
    type_confidence: float = 0.5
    topics: list[str] = Field(default_factory=list)
    date: Date | None = None
    authority: Authority = Authority.ENGINEERING
    doc_title: str = ""
    doc_source: str = ""
    #: Set when ingestion detects instruction-shaped text inside a document.
    injection_flags: list[str] = Field(default_factory=list)


class Document(BaseModel):
    doc_id: str
    title: str
    doc_type: str
    source: str
    date: Date | None
    authority: Authority
    topics: list[str]
    declared_status: str | None = None
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    body: str
    claims: list[Claim] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Retrieval / answering
# --------------------------------------------------------------------------
class Evidence(BaseModel):
    claim_id: str
    doc_id: str
    doc_title: str
    source: str
    date: Date | None
    claim_type: ClaimType
    text: str
    score: float
    #: Present when this evidence is known to be outranked by something newer.
    caveat: str | None = None
    #: Injection heuristics that fired on the source claim. Non-empty means the
    #: text is quarantined: reported to the user, never used as support.
    flags: list[str] = Field(default_factory=list)

    def cite(self) -> str:
        return f"[{self.claim_id}]"


class AnswerSegment(BaseModel):
    """One assertion plus the evidence it rests on. No naked prose."""

    text: str
    claim_type: ClaimType
    citations: list[str]


class Answer(BaseModel):
    question: str
    verdict: Literal["ANSWERED", "PARTIAL", "UNKNOWN"]
    segments: list[AnswerSegment]
    evidence: list[Evidence]
    caveats: list[str] = Field(default_factory=list)
    #: Populated when verdict != ANSWERED so the user knows what is missing.
    missing: list[str] = Field(default_factory=list)
    trace_id: str = ""
    #: Which model actually produced this answer. Recorded so a past answer can
    #: be attributed to what generated it, including the local floor.
    provider: str = ""
    model: str = ""
    tokens_used: int = 0

    def as_text(self) -> str:
        if not self.segments:
            return "UNKNOWN — the supplied material does not support an answer."
        return "\n".join(
            f"[{s.claim_type.value}] {s.text} {' '.join('[' + c + ']' for c in s.citations)}"
            for s in self.segments
        )


# --------------------------------------------------------------------------
# Decision retrieval (§2.2)
# --------------------------------------------------------------------------
class ConflictAssessment(BaseModel):
    conflicts: bool
    severity: Literal["none", "low", "medium", "high"] = "none"
    explanation: str = ""
    governing_claim_ids: list[str] = Field(default_factory=list)


class GoverningDecision(BaseModel):
    doc_id: str
    title: str
    status: DecisionStatus
    source: str
    date: Date | None
    authority: Authority
    decision_text: str
    rationale: str | None
    claim_ids: list[str]
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    #: Other records that pull against this one while it is still in force.
    contested_by: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DecisionLookup(BaseModel):
    question: str
    found: bool
    governing: GoverningDecision | None = None
    history: list[GoverningDecision] = Field(default_factory=list)
    proposal_conflict: ConflictAssessment | None = None
    trace_id: str = ""


# --------------------------------------------------------------------------
# Contradiction detection (§2.3)
# --------------------------------------------------------------------------
class Contradiction(BaseModel):
    contradiction_id: str
    kind: Literal[
        "mutual_exclusivity",
        "numeric_divergence",
        "unratified_change",
        "commitment_breach",
        "explicit_supersession",
        "external_divergence",
    ]
    severity: Literal["low", "medium", "high"]
    confidence: float
    claim_a: Evidence
    claim_b: Evidence
    #: *Why* the two cannot both hold — semantics, not wording.
    why: str
    resolution: str
    detector: str


# --------------------------------------------------------------------------
# Delegation (§2.5)
# --------------------------------------------------------------------------
class DelegationRequest(BaseModel):
    parent_trace_id: str
    agent: str
    task: str
    context_claim_ids: list[str] = Field(default_factory=list)
    budget_tokens: int = 4000
    granted_tools: list[str] = Field(default_factory=list)


class DelegationResult(BaseModel):
    agent: str
    task: str
    status: Literal["ok", "refused", "error", "budget_exceeded"]
    summary: str
    findings: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    provider: str = ""
    model: str = ""
    tokens_used: int = 0
    #: Anything the subordinate agent refused to do, and why.
    refusals: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Human authorization (§2.6)
# --------------------------------------------------------------------------
class ActionStatus(str, Enum):
    PENDING = "PENDING_HUMAN_AUTHORIZATION"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class ActionRequest(BaseModel):
    action_id: str
    trace_id: str
    tool: str
    risk: Literal["low", "medium", "high", "consequential"]
    #: Human-readable statement of exactly what will happen on approval.
    intent: str
    payload: dict[str, Any]
    payload_hash: str
    status: ActionStatus = ActionStatus.PENDING
    created_at: datetime
    expires_at: datetime
    requested_by: str = "founder_agent"
    #: Set only by the human-authorization endpoint, never by an agent.
    approved_by: str | None = None
    approved_at: datetime | None = None
    denial_reason: str | None = None
    execution_result: dict[str, Any] | None = None
    #: Evidence the agent used to build the action, so a human can check it.
    supporting_claim_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def canonical_hash(payload: dict[str, Any]) -> str:
    """Stable hash of an action payload. Approval is bound to this value."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContradictionCluster(BaseModel):
    """Several conflicting pairs that are really one institutional question."""

    cluster_id: str
    axis: str
    title: str
    severity: Literal["low", "medium", "high"]
    documents: list[str]
    primary: "Contradiction"
    supporting: list["Contradiction"] = Field(default_factory=list)
    #: What actually governs today, so the reader is not left holding a conflict.
    current_position: str = ""


class PlanStep(BaseModel):
    agent: str
    reason: str
    context_claim_ids: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    """What the orchestrator decided to do, and why.

    Built from the user's question and *structural* retrieval metadata only -
    document text never reaches the planner, so a document cannot cause an
    agent to be spawned or a tool to be selected.
    """

    intent: Literal["lookup", "decision_check", "proposal_review", "action_request"]
    steps: list[PlanStep] = Field(default_factory=list)
    rationale: str = ""


class FounderResponse(BaseModel):
    question: str
    trace_id: str
    plan: Plan
    answer: Answer
    decision: DecisionLookup | None = None
    contradictions: list[ContradictionCluster] = Field(default_factory=list)
    delegations: list[DelegationResult] = Field(default_factory=list)
    pending_action: ActionRequest | None = None
    provider: str = ""
    degraded: bool = False
