"""HTTP surface, including the human-only routes."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from founder_agent import api
    return TestClient(api.app)


def test_health_reports_corpus_and_providers(client):
    body = client.get("/api/health").json()
    assert body["documents"] == 18
    assert body["claims"] > 30
    assert "deterministic" in body["providers"]
    assert body["audit_chain"]["ok"] is True


def test_ask_returns_cited_segments(client):
    body = client.post("/api/ask", json={"question": "What is the signing API rate limit?"}).json()
    assert body["answer"]["verdict"] in {"ANSWERED", "PARTIAL"}
    assert all(s["citations"] for s in body["answer"]["segments"])
    assert body["trace_id"]


def test_ask_unknown_question(client):
    body = client.post("/api/ask", json={"question": "What is our Series A valuation?"}).json()
    assert body["answer"]["verdict"] == "UNKNOWN"


def test_contradictions_endpoint(client):
    body = client.get("/api/contradictions?detail=true").json()
    assert body["cluster_count"] >= 3
    assert all(c["primary"]["why"] for c in body["clusters"])


def test_action_requires_valid_human_token(client):
    prepared = client.post("/api/ask", json={
        "question": "Send Northbridge Bank the position of record",
        "prepare_action": True}).json()
    action_id = prepared["pending_action"]["action_id"]

    # No credential at all.
    assert client.post(f"/api/actions/{action_id}/approve").status_code == 403
    # Wrong credential.
    assert client.post(f"/api/actions/{action_id}/approve",
                       headers={"X-Approver-Token": "nope"}).status_code == 403
    # Execution before approval.
    assert client.post(f"/api/actions/{action_id}/execute").status_code == 403

    ok = client.post(f"/api/actions/{action_id}/approve",
                     headers={"X-Approver-Token": "dev-human-console-token"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "APPROVED"

    done = client.post(f"/api/actions/{action_id}/execute").json()
    assert done["status"] == "EXECUTED"
    assert done["execution_result"]["simulated"] is True


def test_audit_trace_is_retrievable(client):
    body = client.post("/api/ask", json={"question": "custody provider policy"}).json()
    trace = client.get(f"/api/audit/trace/{body['trace_id']}").json()
    assert trace["event_count"] >= 3
    assert trace["user_request"]["question"] == "custody provider policy"


def test_security_selftest_all_controls_pass(client):
    body = client.post("/api/security/selftest").json()
    failed = [c for c in body["checks"] if not c["passed"]]
    assert not failed, failed
    assert body["all_passed"] is True


def test_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "FOUNDER INTELLIGENCE AGENT" in r.text
