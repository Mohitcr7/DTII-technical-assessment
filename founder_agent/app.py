"""Assemble the system once and hand out the pieces."""

from __future__ import annotations

from dataclasses import dataclass

from .agents.orchestrator import Orchestrator
from .audit import AuditLog
from .authorization import ActionGateway
from .config import Settings, settings as default_settings
from .classify import Classifier
from .contradictions import ContradictionDetector
from .decisions import DecisionLedger
from .ingest import CorpusLoader
from .knowledge import KnowledgeService
from .llm.registry import ProviderRegistry
from .retrieval import ClaimIndex
from .schemas import Claim, Document
from .tools.external import register_default_tools
from .tools.registry import ToolRegistry


@dataclass
class FounderAgentSystem:
    settings: Settings
    documents: list[Document]
    claims: list[Claim]
    index: ClaimIndex
    ledger: DecisionLedger
    detector: ContradictionDetector
    knowledge: KnowledgeService
    registry: ProviderRegistry
    tools: ToolRegistry
    audit: AuditLog
    gateway: ActionGateway
    orchestrator: Orchestrator


def build_system(settings: Settings | None = None) -> FounderAgentSystem:
    settings = settings or default_settings
    settings.ensure_dirs()

    providers = ProviderRegistry(settings)
    documents = CorpusLoader(settings.corpus_dir, Classifier()).load()
    claims = [c for d in documents for c in d.claims]

    index = ClaimIndex(claims)
    ledger = DecisionLedger(documents)
    detector = ContradictionDetector(claims, {d.doc_id: d for d in documents}, ledger)
    knowledge = KnowledgeService(index, ledger, providers, settings)

    audit = AuditLog(settings.audit_path)
    tools = register_default_tools(ToolRegistry())
    gateway = ActionGateway(tools, audit, settings)

    orchestrator = Orchestrator(index, ledger, knowledge, detector, providers, audit, gateway)
    return FounderAgentSystem(
        settings=settings, documents=documents, claims=claims, index=index, ledger=ledger,
        detector=detector, knowledge=knowledge, registry=providers, tools=tools, audit=audit,
        gateway=gateway, orchestrator=orchestrator,
    )
