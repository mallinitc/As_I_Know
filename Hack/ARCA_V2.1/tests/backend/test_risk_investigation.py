from fastapi.testclient import TestClient
from backend.main import app
from backend.services.risk_investigation import RiskInvestigationService

client=TestClient(app,raise_server_exceptions=False); service=RiskInvestigationService()
def execute(sid): return service.investigate(scenario_id=sid)
def categories(result): return {x["category"] for x in result["findings"]}

def test_provider_and_all_environment_investigations():
    assert execute("RISK-01")["providers_investigated"]==["aws"]
    assert execute("RISK-04")["providers_investigated"]==["azure"]
    assert execute("RISK-07")["providers_investigated"]==["snowflake"]
    assert set(execute("RISK-10")["providers_investigated"])=={"aws","azure","snowflake"}
def test_identity_role_resource_and_time_filters():
    assert all("charlie" in str(x["actor"]).lower() for x in execute("RISK-11")["activity_timeline"])
    assert all("securityadmin" in str(x["role"]).lower() for x in execute("RISK-07")["activity_timeline"])
    assert all("production-admin" in str(x["resource"]).lower() for x in execute("RISK-01")["activity_timeline"])
    result=service.investigate(environment="aws",window_days=1,evaluation_timestamp="2026-10-22T12:00:00Z"); assert all(x["timestamp"]>="2026-10-21T12:00:00Z" for x in result["activity_timeline"])
def test_severity_confidence_duplicates_and_missing_evidence():
    assert all(x["severity"]=="HIGH" for x in execute("RISK-12")["findings"])
    assert execute("RISK-13")["findings"]==[]
    result=execute("RISK-14"); assert "INSUFFICIENT_AUDIT_EVIDENCE" in categories(result) and result["confidence"]=="limited"
    all_result=execute("RISK-15"); keys={(x["provider"],x["evidence_id"]) for x in all_result["activity_timeline"]}; assert len(keys)==len(all_result["activity_timeline"])
def test_all_verified_scenarios_execute_real_service():
    scenarios=service.scenarios(); assert len(scenarios)==15
    for item in scenarios:
        result=execute(item["scenario_id"]); assert set(item["expected_findings"])<=categories(result); assert set(item["expected_providers"])<=set(result["providers_investigated"])
def test_api_contract_and_provider_regressions():
    catalog=client.get("/api/v1/investigations/risk/scenarios"); assert catalog.status_code==200 and catalog.json()["count"]==15
    result=client.post("/api/v1/investigations/risk",json={"environment":"aws","window_days":10,"severity":"all","evaluation_timestamp":"2026-10-22T12:00:00Z","scenario_id":"RISK-01"}); assert result.status_code==200 and {"summary","risk_counts","findings","activity_timeline","evidence_limitations"}<=result.json().keys()
    assert client.get("/api/v1/aws/execution-scenarios").status_code==200; assert client.get("/api/v1/azure/execution-scenarios").status_code==200; assert client.get("/api/v1/snowflake/execution-scenarios").status_code==200
