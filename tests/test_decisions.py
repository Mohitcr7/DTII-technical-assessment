"""Decision retrieval: what governs, what it replaced, what it rules out."""

from founder_agent.schemas import DecisionStatus


def test_board_decision_governs_custody(system):
    answer = system.knowledge.answer("custody provider vendor strategy")
    lookup = system.ledger.lookup("What is our custody vendor strategy?",
                                  [e.doc_id for e in answer.evidence])
    assert lookup.found
    assert lookup.governing.doc_id == "DOC-10"
    assert lookup.governing.status is DecisionStatus.ACTIVE
    assert lookup.governing.authority.value == "board"


def test_explicit_supersession_is_honoured(system):
    assert system.ledger.entries["DOC-17"].status is DecisionStatus.SUPERSEDED
    assert system.ledger.entries["DOC-17"].superseded_by == "DOC-14"
    assert system.ledger.entries["DOC-14"].status is DecisionStatus.ACTIVE


def test_informal_change_is_recorded_and_then_reversed(system):
    entry = system.ledger.entries["DOC-02"]
    assert entry.status is DecisionStatus.SUPERSEDED
    assert entry.superseded_by == "DOC-10"


def test_original_decision_notes_the_deviation(system):
    notes = " ".join(system.ledger.entries["DOC-01"].notes)
    assert "DOC-02" in notes and "DOC-10" in notes


def test_proposal_conflicting_with_the_record_is_flagged(system):
    response = system.orchestrator.ask("Should we add KeyForge as a second custody provider?")
    conflict = response.decision.proposal_conflict
    assert conflict.conflicts
    assert conflict.severity == "high"
    assert "DOC-10" in conflict.explanation


def test_unrelated_question_does_not_manufacture_a_conflict(system):
    response = system.orchestrator.ask("What is our API rate limit?")
    assert response.decision is None or not response.decision.proposal_conflict.conflicts


def test_every_active_decision_exposes_its_rationale(system):
    """§2.2 asks for the rationale. DOC-10 and DOC-14 carry theirs inline."""
    for doc_id in ("DOC-01", "DOC-10", "DOC-14"):
        assert system.ledger.entries[doc_id].rationale, doc_id
    assert "cost discipline" in system.ledger.entries["DOC-10"].rationale
    assert "regulatory" in system.ledger.entries["DOC-14"].rationale
    assert "SOC 2" in system.ledger.entries["DOC-01"].rationale
