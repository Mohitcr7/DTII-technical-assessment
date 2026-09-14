"""Live provider check. Opt in with FA_LIVE=1 and a real ANTHROPIC_API_KEY.

    FA_LIVE=1 .venv/bin/python -m pytest tests/test_live.py -q -s

Skipped by default so the ordinary suite is hermetic and free.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("FA_LIVE") != "1" or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="set FA_LIVE=1 and ANTHROPIC_API_KEY to run against the live API",
)


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    from founder_agent.app import build_system
    from founder_agent.config import ROOT, Settings
    tmp = tmp_path_factory.mktemp("live")
    s = Settings()
    s.corpus_dir = ROOT / "corpus"
    s.audit_path = tmp / "audit.jsonl"
    s.actions_path = tmp / "actions.jsonl"
    s.ensure_dirs()
    return build_system(s)


def test_anthropic_is_the_active_provider(live):
    assert live.registry.active_provider("reason") == "anthropic"


def test_live_answer_is_synthesised_and_grounded(live):
    answer = live.knowledge.answer("How long do we retain signing logs, and why?")
    print("\n", answer.provider, answer.model, answer.tokens_used, "tokens")
    for seg in answer.segments:
        print(f"  [{seg.claim_type.value}] {seg.text} {seg.citations}")
    assert answer.provider == "anthropic"
    assert answer.model.startswith("claude-")
    assert answer.segments, "model produced no citable sentence"
    assert all(s.citations for s in answer.segments)
    assert any("DOC-14#c1" in s.citations for s in answer.segments)
    assert not any("extractively" in c for c in answer.caveats), "fell back to the floor"


def test_live_model_cannot_upgrade_a_hypothesis(live):
    answer = live.knowledge.answer("Why are EU customers seeing higher signing latency?")
    labels = {s.claim_type.value for s in answer.segments}
    print("\n labels:", labels)
    assert "HYPOTHESIS" in labels or "INFERENCE" in labels
    assert "FACT" not in {s.claim_type.value for s in answer.segments
                          if "DOC-03#c1" in s.citations}


def test_live_unknown_stays_unknown(live):
    answer = live.knowledge.answer("What is our Series A valuation?")
    assert answer.verdict == "UNKNOWN"


def test_live_full_pipeline_with_delegation(live):
    response = live.orchestrator.ask("Should we add KeyForge as a second custody provider?")
    print("\n verdict:", response.answer.verdict, "| provider:", response.provider)
    for d in response.delegations:
        print(f"  {d.agent}: {d.provider}/{d.model} {d.tokens_used} tok — {d.summary[:120]}")
    assert response.provider == "anthropic"
    assert response.decision.proposal_conflict.conflicts
    assert all(d.provider == "anthropic" for d in response.delegations)
    record = live.audit.reconstruct(response.trace_id)
    assert record["models_used"][0]["provider"] == "anthropic"
