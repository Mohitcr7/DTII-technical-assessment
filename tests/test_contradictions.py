"""Contradictions: find the real ones, explain them, and skip the false ones."""


def test_finds_the_custody_contradiction(system):
    clusters = system.detector.cluster()
    custody = next(c for c in clusters if c.axis == "custody_vendor_cardinality")
    assert custody.severity == "high"
    assert {"DOC-01", "DOC-02", "DOC-10"} <= set(custody.documents)


def test_explanation_is_semantic_not_lexical(system):
    custody = next(c for c in system.detector.cluster()
                   if c.axis == "custody_vendor_cardinality")
    why = custody.primary.why.lower()
    assert "cardinality" in why or "exclusiv" in why
    assert "cannot both" in why
    # It must not merely observe that the wording differs.
    assert "different words" not in why.replace("not different words for one arrangement", "")


def test_governance_gap_is_its_own_finding(system):
    kinds = {c.primary.kind for c in system.detector.cluster()}
    assert "unratified_change" in kinds


def test_commitment_slip_detected(system):
    cluster = next(c for c in system.detector.cluster()
                   if c.primary.kind == "commitment_breach")
    assert {"DOC-15", "DOC-16"} == set(cluster.documents)


def test_fulfilled_commitment_is_not_a_contradiction(system):
    """DOC-05 promised attestation; DOC-11 delivered it on time."""
    pairs = {(c.claim_a.doc_id, c.claim_b.doc_id)
             for cl in system.detector.cluster()
             for c in [cl.primary, *cl.supporting]}
    assert ("DOC-05", "DOC-11") not in pairs
    assert ("DOC-11", "DOC-05") not in pairs


def test_hypothesis_does_not_contradict_a_decision(system):
    """DOC-03 is speculation; it must not be reported as conflicting with policy."""
    for cluster in system.detector.cluster():
        for c in [cluster.primary, *cluster.supporting]:
            types = {c.claim_a.claim_type.value, c.claim_b.claim_type.value}
            assert not (types & {"HYPOTHESIS"}), f"{c.contradiction_id} uses a hypothesis"


def test_every_cluster_states_what_governs_today(system):
    for cluster in system.detector.cluster():
        assert cluster.current_position
