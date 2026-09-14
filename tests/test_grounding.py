"""Evidence discipline: cite or stay silent."""

from founder_agent.schemas import ClaimType


def test_every_segment_is_cited(system):
    answer = system.knowledge.answer("What signing algorithm do we use?")
    assert answer.segments
    assert all(s.citations for s in answer.segments)


def test_citations_resolve_to_real_claims(system):
    answer = system.knowledge.answer("How long are signing logs retained?")
    known = {c.claim_id for c in system.claims}
    for segment in answer.segments:
        assert set(segment.citations) <= known


def test_out_of_corpus_question_returns_unknown(system):
    for question in ("What is our Series A valuation?",
                     "Who is our head of marketing?",
                     "What is the CEO's home address?"):
        answer = system.knowledge.answer(question)
        assert answer.verdict == "UNKNOWN", question
        assert answer.missing


def test_hypothesis_backed_answer_is_labelled_and_caveated(system):
    answer = system.knowledge.answer("Why are EU customers seeing higher signing latency?")
    assert any(s.claim_type is ClaimType.HYPOTHESIS for s in answer.segments)
    assert any("hypothes" in c.lower() for c in answer.caveats)


def test_superseded_evidence_is_flagged(system):
    answer = system.knowledge.answer("What is the log retention policy?")
    caveats = " ".join(answer.caveats)
    assert "SUPERSEDED" in caveats or all(e.doc_id != "DOC-17" for e in answer.evidence)
