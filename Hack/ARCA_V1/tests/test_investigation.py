import boto3

from arca.investigation import InvestigationAgent, InvestigationTools
from arca.investigation.models import OpenAIModelAdapter
from arca.observability import ensure_log_files, read_records


def test_read_only_tools_preserve_evidence_ids_and_utc_timestamps():
    tools = InvestigationTools()
    resource = tools.find_resources(query="starchprod04")["items"][0]
    details = tools.get_resource_details(resource["resource_id"])
    activity = tools.get_activity_logs(resource_id=resource["resource_id"], modifications_only=True)
    assert details["count"] == 1
    assert details["items"][0]["resource_id"] == resource["resource_id"]
    assert activity["count"] >= 1
    assert all(item["event_data_id"].startswith("az-event-") for item in activity["items"])
    assert all(item["event_timestamp"].endswith("Z") for item in activity["items"])


def test_scenario_a_access_troubleshooting_clarifies_identity_and_correlates_evidence():
    agent = InvestigationAgent(model_mode="mock")
    first = agent.ask("I cannot access starchprod04. What changed?", "access")
    assert first["status"] == "clarification"
    assert "Which user or service-principal" in first["response"]
    assert first["context"]["selected_resource"].endswith("starchprod04")
    second = agent.ask("engineer12@example.invalid", "access")
    assert second["status"] == "complete"
    assert "firewall/network ACL modification possibly related" in second["response"]
    assert "not confirmed root causes" in second["response"]
    assert "az-event-0012" in second["evidence_refs"]
    assert second["context"]["selected_identity"] == "engineer12@example.invalid"


def test_scenario_b_undocumented_changes_are_not_called_unauthorized():
    result = InvestigationAgent(model_mode="mock").ask(
        "Show undocumented production changes in the last 24 hours.", "undocumented")
    assert result["tool_results"]["undocumented"]["count"] == 10
    assert "not confirmed unauthorized" in result["response"]
    assert all(item["classification"] == "UNMATCHED_IN_AVAILABLE_RECORDS"
               for item in result["tool_results"]["undocumented"]["items"])


def test_scenario_c_resource_modifications_include_actor_operation_and_time():
    result = InvestigationAgent(model_mode="mock").ask(
        "Who modified starchprod01 during the last week?", "resource")
    records = result["tool_results"]["activity_logs"]["items"]
    assert records
    assert all(item.get("caller") and item.get("operation_name", {}).get("value") and item.get("event_timestamp") for item in records)
    assert "engineer01@example.invalid" in result["response"]
    assert "az-event-0001" in result["evidence_refs"]


def test_scenario_d_pim_contributor_at_subscription_scope():
    result = InvestigationAgent(model_mode="mock").ask(
        "Who requested Contributor access at subscription scope this week?", "pim")
    requests = result["tool_results"]["pim_requests"]["items"]
    assert {request["pim_request_id"] for request in requests} >= {"pim-az-0005", "pim-az-0025"}
    assert requests[0]["scope"].count("/") == 2


def test_scenario_e_multiturn_context_retains_resource_findings_and_approval():
    agent = InvestigationAgent(model_mode="mock")
    first = agent.ask("What changed on starchprod01?", "multi")
    second = agent.ask("Who performed those changes?", "multi")
    third = agent.ask("Were they approved?", "multi")
    assert first["context"]["selected_resource"].endswith("starchprod01")
    assert "engineer01@example.invalid" in second["response"]
    assert "exact matching approved synthetic change" in third["response"]
    assert third["tool_results"]["approval_correlation"]["count"] >= 1


def test_ambiguous_resource_requests_clarification():
    result = InvestigationAgent(model_mode="mock").ask(
        "Who modified this Storage Account during the last 48 hours?", "ambiguous")
    assert result["status"] == "clarification"
    assert "multiple matching synthetic resources" in result["response"]
    assert result["context"]["pending_clarification"] == "resource"


def test_unavailable_and_insufficient_evidence_are_reported():
    agent = InvestigationAgent(model_mode="mock")
    missing = agent.ask("What changed on resource definitely-not-present?", "missing")
    assert missing["status"] == "clarification"
    assert "could not uniquely identify" in missing["response"]
    followup = agent.ask("Who performed those changes?", "fresh-followup")
    assert followup["status"] == "insufficient_evidence"
    assert "do not have prior modification evidence" in followup["response"]


def test_mock_mode_never_initializes_bedrock(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Bedrock/AWS session must not be initialized in mock mode")
    monkeypatch.setattr(boto3, "Session", forbidden)
    result = InvestigationAgent(model_mode="mock").ask(
        "Show undocumented production changes in the last 24 hours.", "no-bedrock")
    assert result["status"] == "complete"
    assert result["response"].startswith("MOCK MODE")


def test_bedrock_unavailability_is_explicit_not_claimed_as_reasoning(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr(boto3, "Session", unavailable)
    result = InvestigationAgent(model_mode="bedrock").ask("What changed on starchprod01?", "bedrock-offline")
    assert result["status"] == "unavailable"
    assert "Bedrock planning is unavailable" in result["response"]
    assert "No model reasoning was used" in result["response"]


def test_malformed_and_unsupported_questions_are_handled():
    agent = InvestigationAgent(model_mode="mock")
    malformed = agent.ask("", "malformed")
    unsupported = agent.ask("Write a poem about cloud governance", "unsupported")
    assert malformed["status"] == "unavailable"
    assert "non-empty investigation question" in malformed["response"]
    assert unsupported["status"] == "unsupported"
    assert "I can investigate" in unsupported["response"]


def test_greeting_is_professional_and_does_not_invoke_openai(monkeypatch, tmp_path):
    monkeypatch.setenv("ARCA_LOG_DIR", str(tmp_path / "logs"))
    ensure_log_files()
    monkeypatch.setattr(OpenAIModelAdapter, "plan", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("planner called")))
    result = InvestigationAgent(model_mode="openai").ask("Hi", "greeting-openai")
    assert result["status"] == "complete"
    assert "Hello! I'm ARCA" in result["response"]
    assert read_records("llm_calls") == []


def test_capabilities_and_known_cloud_explanations_are_deterministic(monkeypatch):
    monkeypatch.setattr(OpenAIModelAdapter, "plan", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("planner called")))
    agent = InvestigationAgent(model_mode="openai")
    capabilities = agent.ask("What can ARCA do?", "capabilities")
    pim = agent.ask("What is Azure PIM?", "known-pim")
    assert "privileged-access requests" in capabilities["response"]
    assert "time-bound" in pim["response"]
    assert "not, by itself, proof" in pim["response"]


def test_unrelated_question_executes_no_cloud_tools(monkeypatch):
    tools = InvestigationTools()
    for name in ("find_resources", "get_resource_details", "get_activity_logs", "get_role_assignments",
                 "get_pim_requests", "get_change_records", "find_undocumented_changes"):
        monkeypatch.setattr(tools, name, lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("tool called")))
    result = InvestigationAgent(tools=tools, model_mode="mock").ask("What is the capital of France?", "unrelated")
    assert result["status"] == "unsupported"
    assert "focuses on cloud security" in result["response"]


def test_genuine_investigation_uses_planner_and_tools(monkeypatch):
    called = {"planner": 0, "tool": 0}
    def plan(self, query, context, evidence_as_of):
        called["planner"] += 1
        return {"intent": "undocumented_changes", "parameters": {"environment": "production"}}
    monkeypatch.setattr(OpenAIModelAdapter, "plan", plan)
    monkeypatch.setattr(OpenAIModelAdapter, "respond", lambda self, baseline, results, context: baseline)
    tools = InvestigationTools()
    original = tools.find_undocumented_changes
    def tracked(*args, **kwargs):
        called["tool"] += 1
        return original(*args, **kwargs)
    monkeypatch.setattr(tools, "find_undocumented_changes", tracked)
    result = InvestigationAgent(tools=tools, model_mode="openai").ask("Find undocumented production changes.", "planned")
    assert result["status"] == "complete"
    assert called == {"planner": 1, "tool": 1}


def test_planner_failure_preserves_sanitized_limitation(monkeypatch):
    monkeypatch.setattr(OpenAIModelAdapter, "plan", lambda *args, **kwargs: {
        "intent": "unavailable", "parameters": {},
        "error": "Configured OpenAI inference is unavailable: APIConnectionError. No model result was used.",
    })
    result = InvestigationAgent(model_mode="openai").ask("Who modified starchprod01 yesterday?", "planner-failure")
    assert result["status"] == "unavailable"
    assert "APIConnectionError" in result["response"]
    assert "No model result was used" in result["response"]
