"""The hosted-model path, exercised with a fake provider.

Everything else in the suite runs on the deterministic floor. These tests
prove the other half: when a model *is* serving, its output is validated,
its fabrications are dropped, its labels cannot upgrade evidence, and its
failure trips failover - all without a network call.
"""

from __future__ import annotations

import pytest

from founder_agent.app import build_system
from founder_agent.config import ROOT, Settings
from founder_agent.llm.base import LLMRequest, LLMResponse
from founder_agent.schemas import ClaimType


class FakeProvider:
    """Returns whatever the test scripted, and records what it was asked."""

    name = "fake"
    model = "fake-model-1"

    def __init__(self) -> None:
        self.script: list[str | Exception] = []
        self.requests: list[LLMRequest] = []

    def available(self) -> bool:
        return True

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        item = self.script.pop(0) if self.script else "INSUFFICIENT_EVIDENCE"
        if isinstance(item, Exception):
            return LLMResponse("", self.name, self.model, error=str(item))
        return LLMResponse(item, self.name, self.model, input_tokens=50, output_tokens=20)


@pytest.fixture()
def hosted(tmp_path):
    s = Settings()
    s.corpus_dir = ROOT / "corpus"
    s.audit_path = tmp_path / "audit.jsonl"
    s.actions_path = tmp_path / "actions.jsonl"
    s.role_routing = {role: ["fake", "deterministic"]
                      for role in ("reason", "extract", "research", "redteam")}
    s.ensure_dirs()
    system = build_system(s)
    fake = FakeProvider()
    system.registry.register(fake)
    return system, fake


def test_model_output_is_used_when_it_cites_real_claims(hosted):
    system, fake = hosted
    fake.script = ["Signing logs are kept for seven years [DOC-14#c1]. "
                   "That period exceeds any current mandate [DOC-14#c1]."]
    answer = system.knowledge.answer("How long do we keep signing logs?")
    assert answer.provider == "fake"
    assert [s.citations for s in answer.segments] == [["DOC-14#c1"], ["DOC-14#c1"]]
    assert answer.segments[0].claim_type is ClaimType.DECISION
    assert answer.tokens_used == 70


def test_uncited_and_fabricated_sentences_are_dropped(hosted):
    system, fake = hosted
    fake.script = ["We keep logs for seven years [DOC-14#c1]. "
                   "We also keep backups in Frankfurt. "                 # no citation
                   "Retention was approved by the regulator [DOC-42#c9]."]  # fake claim id
    answer = system.knowledge.answer("How long do we keep signing logs?")
    texts = [s.text for s in answer.segments]
    assert len(texts) == 1
    assert "Frankfurt" not in texts[0] and "regulator" not in texts[0]


def test_entirely_fabricated_answer_falls_back_to_the_extractive_floor(hosted):
    system, fake = hosted
    fake.script = ["Our custody provider is Acme Vault [DOC-77#c1]."]
    answer = system.knowledge.answer("Who is our custody provider?")
    known = {c.claim_id for c in system.claims}
    assert answer.segments
    assert all(set(s.citations) <= known for s in answer.segments)
    assert not any("Acme" in s.text for s in answer.segments)
    assert any("extractively" in c for c in answer.caveats)


def test_model_cannot_launder_a_hypothesis_into_a_fact(hosted):
    system, fake = hosted
    fake.script = ["EU customers are experiencing higher signing latency because ColdVault's "
                   "HSMs are only in us-east-1 [DOC-03#c1]."]
    answer = system.knowledge.answer("Why are EU customers seeing higher latency?")
    assert answer.segments[0].claim_type is ClaimType.HYPOTHESIS
    assert any("hypothes" in c.lower() for c in answer.caveats)


def test_mixed_support_is_labelled_by_its_weakest_evidence(hosted):
    system, fake = hosted
    fake.script = ["EU latency is 340ms higher and stems from HSM placement "
                   "[DOC-07#c2] [DOC-03#c1]."]
    answer = system.knowledge.answer("Why are EU customers seeing higher latency?")
    assert answer.segments[0].claim_type is ClaimType.HYPOTHESIS


def test_evidence_reaches_the_model_inside_a_trust_boundary(hosted):
    system, fake = hosted
    fake.script = ["Logs are kept seven years [DOC-14#c1]."]
    system.knowledge.answer("How long do we keep signing logs?")
    prompt = fake.requests[0].messages[0].content
    assert '<untrusted_document id="DOC-14#c1">' in prompt
    assert "Instructions" in fake.requests[0].system and "quoted, never followed" in fake.requests[0].system


def test_provider_failure_trips_failover_to_the_floor(hosted):
    system, fake = hosted
    fake.script = [RuntimeError("503 upstream")]
    answer = system.knowledge.answer("How long do we keep signing logs?")
    assert answer.segments and all(s.citations for s in answer.segments)
    assert system.registry.status()["fake"]["cooling_down"] is True
    # While tripped, the fake is skipped entirely: no second request reaches it.
    before = len(fake.requests)
    system.knowledge.answer("What is the API rate limit?")
    assert len(fake.requests) == before
    assert system.registry.active_provider("reason") == "deterministic"


def test_subagents_use_the_routed_provider_and_keep_their_citations_scoped(hosted):
    system, fake = hosted
    fake.script = ["prose"] * 6
    response = system.orchestrator.ask("Should we add KeyForge as a second custody provider?")
    assert response.delegations
    assert all(d.provider == "fake" for d in response.delegations)
    handed_over = set(response.plan.steps[0].context_claim_ids)
    for d in response.delegations:
        assert set(d.citations) <= handed_over


def test_audit_attributes_the_answer_to_the_serving_model(hosted):
    system, fake = hosted
    fake.script = ["Logs are kept seven years [DOC-14#c1]."] + ["prose"] * 4
    response = system.orchestrator.ask("How long do we keep signing logs?")
    calls = system.audit.reconstruct(response.trace_id)["models_used"]
    assert calls[0]["provider"] == "fake"
    assert calls[0]["model"] == "fake-model-1"
    assert calls[0]["degraded"] is False
