import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.ask_arca import AgentConfigurationError,AskArcaService
from backend.api.routes.ask_arca import service as api_service

client=TestClient(app,raise_server_exceptions=False); service=AskArcaService()
def test_intent_entity_and_provider_parsing():
 result=service.parse("Was CHG-SF-1007 implemented correctly in the last 15 days?"); assert result["provider"]=="snowflake" and result["change_id"]=="CHG-SF-1007" and result["time_period_days"]==15 and result["investigation_type"]=="change_execution"
 user=service.parse("Show Azure activities performed by engineer12@example.invalid in the last 7 days."); assert user["provider"]=="azure" and user["user_identifier"]=="engineer12@example.invalid" and user["time_period_days"]==7
def test_change_user_role_and_cross_environment_execution():
 assert service.ask("Investigate AWS change CHG1002.",evaluation_timestamp="2026-10-22T12:00:00Z")["providers_investigated"]==["aws"]
 assert service.ask("Show Snowflake activities performed by SFSECURITY01 in the last 15 days.",evaluation_timestamp="2026-11-24T00:00:00Z")["resolved_intent"]["investigation_type"]=="user_investigation"
 role=service.ask("Investigate activities using ACCOUNTADMIN in Snowflake in the last 30 days.",evaluation_timestamp="2026-11-24T00:00:00Z"); assert role["resolved_intent"]["role"]=="ACCOUNTADMIN"
 cross=service.ask("Show high-risk findings across all environments in the last 30 days.",evaluation_timestamp="2026-11-07T12:00:00Z"); assert set(cross["providers_investigated"])=={"aws","azure","snowflake"}
def test_agent4_reuse_tool_registry_evidence_and_trace():
 result=service.ask("Find unauthorized AWS IAM modifications.",evaluation_timestamp="2026-10-22T12:00:00Z"); assert "find_potentially_unapproved_activity" in {x["tool_name"] for x in result["tool_execution_trace"]}; assert result["evidence_references"]
 assert {x["name"] for x in service.capabilities()["tools"]}>={"get_change_details","validate_change_and_access","verify_change_execution","investigate_user_activity","find_potentially_unapproved_activity","investigate_role_or_privilege_changes","retrieve_supporting_evidence","run_cross_environment_risk_investigation"}
 assert all(x["end_time"]>=x["start_time"] and x["duration"]>=0 for x in result["tool_execution_trace"])
def test_clarification_and_mock_mode_labels():
 result=service.ask("What administrative changes did the user perform?",evaluation_timestamp="2026-11-07T12:00:00Z"); assert result["clarification_request"] and result["execution_mode"]=="mock" and result["resolved_intent"]["parser"]=="deterministic_mock"
def test_ai_mode_requires_configuration(monkeypatch):
 monkeypatch.setattr(service.gateway,"capability",lambda:{"available":False,"provider":None,"model_identifier":None,"status":"disabled"})
 with pytest.raises(AgentConfigurationError): service.ask("Show AWS risks",mode="ai")
def test_all_verified_scenarios_execute_computed_tools():
 scenarios=service.scenarios(); assert len(scenarios)==21
 for item in scenarios:
  result=service.ask(item["question"],scenario_id=item["scenario_id"]); assert result["resolved_intent"]["investigation_type"]==item["expected_intent"]; assert set(result["providers_investigated"])==set(item["expected_providers"]); assert result["investigation_id"].startswith("ASK-")
def test_api_contract_and_regression_smoke(monkeypatch):
 assert client.get("/api/v1/agents/ask-arca/capabilities").status_code==200; assert client.get("/api/v1/agents/ask-arca/scenarios").json()["count"]==21
 response=client.post("/api/v1/agents/ask-arca",json={"question":"Find unauthorized AWS IAM modifications.","evaluation_timestamp":"2026-10-22T12:00:00Z"}); assert response.status_code==200 and {"resolved_intent","findings","evidence_references","tool_execution_trace"}<=response.json().keys()
 monkeypatch.setattr(api_service.gateway,"capability",lambda:{"available":False,"provider":None,"model_identifier":None,"status":"disabled"})
 assert client.post("/api/v1/agents/ask-arca",json={"question":"Show AWS risks","mode":"ai"}).status_code==503
 assert client.get("/api/v1/investigations/risk/scenarios").status_code==200; assert client.get("/api/v1/aws/changes").status_code==200; assert client.get("/api/v1/azure/changes").status_code==200; assert client.get("/api/v1/snowflake/changes").status_code==200

def test_overlong_agent5_synthesis_is_rejected_without_changing_findings():
 from backend.llm.providers import LlmGatewayError
 with pytest.raises(LlmGatewayError,match="concise answer limit"):
  service._validate_synthesis_claims("word "*101,{"overall_status":"POTENTIAL_RISK","findings":[]})
