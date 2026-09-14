"""Category discipline: the labels must not drift, in either direction."""

from founder_agent.schemas import ClaimType


def _claim(system, claim_id):
    return next(c for c in system.claims if c.claim_id == claim_id)


def test_explicit_decision_is_a_decision(system):
    assert _claim(system, "DOC-01#c1").claim_type is ClaimType.DECISION
    assert _claim(system, "DOC-14#c1").claim_type is ClaimType.DECISION


def test_self_labelled_hypothesis_stays_a_hypothesis(system):
    for cid in ("DOC-03#c1", "DOC-13#c1"):
        assert _claim(system, cid).claim_type is ClaimType.HYPOTHESIS


def test_reporting_a_hypothesis_is_not_holding_one(system):
    """DOC-07 cites DOC-03's hypothesis while drawing a conclusion from data."""
    claim = _claim(system, "DOC-07#c3")
    assert claim.claim_type is ClaimType.INFERENCE


def test_recommendation_is_never_promoted_to_decision(system):
    """DOC-06 recommends and explicitly defers; DOC-07 says 'not a decision'."""
    for cid in ("DOC-06#c2", "DOC-06#c3", "DOC-07#c3"):
        assert _claim(system, cid).claim_type is not ClaimType.DECISION


def test_superseded_document_yields_no_governing_decision(system):
    doc17 = [c for c in system.claims if c.doc_id == "DOC-17"]
    assert all(c.claim_type is not ClaimType.DECISION for c in doc17)


def test_every_claim_carries_its_reason(system):
    assert all(c.type_reason for c in system.claims)
