from fastapi.testclient import TestClient

from backend.main import app


client=TestClient(app,raise_server_exceptions=False)
ANALYST={"X-ARCA-Demo-Role":"arca_analyst"}
MANAGER={"X-ARCA-Demo-Role":"arca_manager"}


def test_analyst_can_use_stage1_and_basic_agent5():
    stage1=client.get("/api/v1/agents/change-quality/stage1/demo-scenarios?provider=azure",headers=ANALYST)
    greeting=client.post("/api/v1/agents/ask-arca",headers=ANALYST,json={"question":"Hello","mode":"deterministic"})
    assert stage1.status_code==200
    assert greeting.status_code==200


def test_analyst_is_denied_manager_capabilities():
    assert client.get("/api/v1/agents/access-intelligence/stage2/demo-scenarios",headers=ANALYST).status_code==403
    assert client.get("/api/v1/azure/execution-scenarios",headers=ANALYST).status_code==403
    assert client.get("/api/v1/investigations/risk/scenarios",headers=ANALYST).status_code==403
    assert client.get("/api/v1/analytics/overview",headers=ANALYST).status_code==403
    assert client.get("/api/v1/analytics/observability",headers=ANALYST).status_code==403


def test_manager_access_and_stage1_denial():
    assert client.get("/api/v1/agents/access-intelligence/stage2/demo-scenarios",headers=MANAGER).status_code==200
    assert client.get("/api/v1/azure/execution-scenarios",headers=MANAGER).status_code==200
    assert client.get("/api/v1/investigations/risk/scenarios",headers=MANAGER).status_code==200
    assert client.post("/api/v1/agents/ask-arca",headers=MANAGER,json={"question":"Hello","mode":"deterministic"}).status_code==200
    assert client.get("/api/v1/analytics/overview",headers=MANAGER).status_code==200
    assert client.get("/api/v1/analytics/observability",headers=MANAGER).status_code==200
    assert client.get("/api/v1/agents/change-quality/stage1/demo-scenarios?provider=azure",headers=MANAGER).status_code==403


def test_missing_and_unknown_roles_are_unauthenticated(monkeypatch):
    monkeypatch.setenv("ARCA_TEST_AUTO_ROLE","0")
    assert client.get("/api/v1/environments").status_code==401
    assert client.get("/api/v1/environments",headers={"X-ARCA-Demo-Role":"unknown"}).status_code==401


def test_demo_persona_disabled_requires_production_identity(monkeypatch):
    monkeypatch.setenv("ARCA_DEMO_PERSONA_MODE","false")
    assert client.get("/api/v1/environments",headers=MANAGER).status_code==401


def test_agent5_analyst_cannot_invoke_manager_evidence_tools():
    response=client.post("/api/v1/agents/ask-arca",headers=ANALYST,json={"question":"Show undocumented production changes in the last 24 hours.","mode":"deterministic"})
    assert response.status_code==403


def test_feedback_is_stage_authorized_and_server_attributed(tmp_path,monkeypatch):
    monkeypatch.setenv("ARCA_LOG_DIR",str(tmp_path/"logs"))
    payload={"submission_id":"persona-feedback-001","assessment_id":"a1:test","stage":"A1","provider":"azure","original_decision":"VALID","feedback_decision":"Correct","feedback_reason":""}
    analyst=client.post("/api/v1/analytics/feedback",headers=ANALYST,json=payload)
    manager=client.post("/api/v1/analytics/feedback",headers=MANAGER,json={**payload,"submission_id":"persona-feedback-002"})
    assert analyst.status_code==200
    assert analyst.json()["user_identity"]=="demo:arca_analyst"
    assert analyst.json()["user_role"]=="arca_analyst"
    assert manager.status_code==403


def test_manager_feedback_and_exports_are_authorized(tmp_path,monkeypatch):
    monkeypatch.setenv("ARCA_LOG_DIR",str(tmp_path/"logs"))
    payload={"submission_id":"persona-feedback-003","assessment_id":"a4:test","stage":"A4","provider":"azure","original_decision":"FINDINGS_IDENTIFIED","feedback_decision":"Needs Review","feedback_reason":"Review evidence"}
    assert client.post("/api/v1/analytics/feedback",headers=MANAGER,json=payload).status_code==200
    assert client.get("/api/v1/analytics/feedback/latest?assessment_id=a4:test&stage=A4",headers=MANAGER).status_code==200
    assert client.get("/api/v1/analytics/observability/export/feedback",headers=MANAGER).status_code==200
    assert client.get("/api/v1/analytics/observability/export/feedback",headers=ANALYST).status_code==403


def test_shared_provider_routes_require_explicit_authorized_capability():
    assert client.get("/api/v1/azure/changes",headers=ANALYST).status_code==403
    assert client.get("/api/v1/azure/changes",headers={**ANALYST,"X-ARCA-Capability":"stage1"}).status_code==200
    assert client.get("/api/v1/azure/changes",headers={**MANAGER,"X-ARCA-Capability":"stage2"}).status_code==200
    assert client.get("/api/v1/azure/changes",headers={**ANALYST,"X-ARCA-Capability":"stage2"}).status_code==403
    assert client.get("/api/v1/snowflake/demo-scenarios",headers={**ANALYST,"X-ARCA-Capability":"stage1"}).status_code==403
    assert client.post("/api/v1/snowflake/validate",headers={**ANALYST,"X-ARCA-Capability":"stage1"},json={"change_id":"CHG-SF-1007"}).status_code==403


def test_feedback_lookup_cannot_cross_persona_stage():
    assert client.get("/api/v1/analytics/feedback/latest?assessment_id=a4:test&stage=A4",headers=ANALYST).status_code==403
