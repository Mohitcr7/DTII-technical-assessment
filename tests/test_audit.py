"""Auditability: reconstructable, tamper-evident, and free of secrets."""

import json

from founder_agent.audit import AuditLog


def test_interaction_is_fully_reconstructable(system):
    response = system.orchestrator.ask("Should we add KeyForge as a second custody provider?")
    record = system.audit.reconstruct(response.trace_id)

    assert record["user_request"]["question"]
    assert record["retrieved_context"][0]["claim_ids"]
    assert record["delegations"]
    assert record["outputs"][0]["verdict"] == response.answer.verdict
    events = {e["event"] for e in record["timeline"]}
    assert {"user_request", "retrieval", "plan", "delegation", "response"} <= events


def test_action_lifecycle_is_in_the_log(system):
    from founder_agent.authorization import Principal
    response = system.orchestrator.ask("Send Northbridge Bank the position of record",
                                       prepare_action=True)
    action = response.pending_action
    system.gateway.approve(action.action_id,
                           Principal(kind="human", id="founder",
                                     token=system.settings.approver_token))
    system.gateway.execute(action.action_id, Principal(kind="human", id="founder"))
    events = [e["event"] for e in system.audit.entries(response.trace_id)]
    assert "action_prepared" in events
    assert "action_approved" in events
    assert "action_executed" in events


def test_answer_records_which_model_produced_it(system):
    """§2.7 requires the agent/model used, including on the local floor."""
    response = system.orchestrator.ask("What is our log retention policy?")
    record = system.audit.reconstruct(response.trace_id)
    assert record["models_used"], "no model_call event recorded"
    call = record["models_used"][0]
    assert call["provider"] and call["model"]
    assert call["purpose"] == "answer synthesis"


def test_reconstruct_covers_every_field_the_spec_asks_for(system):
    from founder_agent.authorization import Principal
    response = system.orchestrator.ask(
        "Send Northbridge Bank the position of record", prepare_action=True)
    action = response.pending_action
    system.gateway.approve(action.action_id,
                           Principal(kind="human", id="founder",
                                     token=system.settings.approver_token))
    system.gateway.execute(action.action_id, Principal(kind="human", id="founder"))

    record = system.audit.reconstruct(response.trace_id)
    assert record["user_request"]          # user request
    assert record["retrieved_context"]     # relevant retrieved context
    assert record["models_used"]           # agent / model used
    assert record["delegations"]           # subordinate agents
    assert record["tools_requested"]       # tool / action requested
    assert record["outputs"]               # output
    assert record["human_decisions"]       # human approval
    assert record["resulting_actions"]     # resulting action


def test_model_and_agent_are_attributed(system):
    response = system.orchestrator.ask("Should we consolidate onto one custody provider?")
    delegations = system.audit.reconstruct(response.trace_id)["delegations"]
    assert delegations
    assert all("provider" in d and "model" in d for d in delegations)


def test_secrets_are_redacted_before_the_write(system):
    system.audit.record("test", trace_id="redaction", actor="test", payload={
        "api_key": "sk-ant-should-never-appear-here-000",
        "note": "Authorization: Bearer abcdefghijklmnopqrstuvwx",
    })
    blob = json.dumps(system.audit.entries("redaction")[-1])
    assert "should-never-appear" not in blob
    assert "abcdefghijklmnopqrstuvwx" not in blob


def test_chain_verifies(system):
    assert system.audit.verify()["ok"] is True


def test_tampering_is_detected(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    for i in range(4):
        log.record("event", trace_id="t", actor="x", payload={"i": i})
    assert log.verify()["ok"]

    lines = log.path.read_text().splitlines()
    rewritten = json.loads(lines[1])
    rewritten["payload"] = {"i": 999}          # silently alter history
    lines[1] = json.dumps(rewritten, sort_keys=True)
    log.path.write_text("\n".join(lines) + "\n")

    result = log.verify()
    assert result["ok"] is False
    assert result["broken_at"] == 2
