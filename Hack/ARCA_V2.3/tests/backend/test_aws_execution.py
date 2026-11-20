from fastapi.testclient import TestClient
from backend.main import app
from backend.services.aws_execution import AwsExecutionService

client=TestClient(app,raise_server_exceptions=False); service=AwsExecutionService()
def cats(result): return {x["category"] for x in result["findings"]}
def scenario(number): return next(x for x in service.scenarios() if x["scenario_id"]==f"AWS-EXEC-{number:02d}")
def run(item): return service.assess_change(item["change_id"],item["evaluation_timestamp"],item["scenario_id"]) if item["mode"]=="change" else service.assess_user(item["user_identity"],item["window_days"],item["evaluation_timestamp"],item["scenario_id"])

def test_change_correlation_and_compliance():
    result=run(scenario(1)); assert result["overall_status"]=="COMPLIANT"; assert result["timeline"][0]["change_match"]=="MATCHED"
def test_identity_and_assumed_role_resolution():
    result=run(scenario(12)); assert "COMPLIANT_EXECUTION" in cats(result); assert result["user"]["issuer_arn"].endswith("OperationsRole")
def test_deviation_controls():
    expected={2:"EXECUTED_OUTSIDE_WINDOW",3:"UNAUTHORIZED_IMPLEMENTER",4:"WRONG_TARGET_RESOURCE",5:"UNAPPROVED_OPERATION",6:"FAILED_EXECUTION",7:"EXPECTED_OPERATION_MISSING",8:"UNEXPECTED_ADDITIONAL_OPERATION",13:"ROLE_OR_PRINCIPAL_MISMATCH",14:"WRONG_TARGET_RESOURCE",18:"INSUFFICIENT_AUDIT_EVIDENCE"}
    for number,category in expected.items(): assert category in cats(run(scenario(number)))
def test_duplicate_events_do_not_create_missing_operation():
    result=run(scenario(16)); assert "COMPLIANT_EXECUTION" in cats(result); assert "EXPECTED_OPERATION_MISSING" not in cats(result)
def test_ten_and_fifteen_day_principal_windows():
    ten,fifteen=run(scenario(19)),run(scenario(20)); assert ten["period_start"]=="2026-10-12T12:00:00Z"; assert fifteen["period_start"]=="2026-10-07T12:00:00Z"; assert len(fifteen["event_ids"])>len(ten["event_ids"])
def test_all_scenarios_match_verified_findings():
    assert len(service.scenarios())==20
    for item in service.scenarios(): assert set(item["expected_findings"])<=cats(run(item))
def test_execution_api_contract_and_errors():
    catalog=client.get("/api/v1/aws/execution-scenarios"); assert catalog.status_code==200 and catalog.json()["count"]==20
    result=client.post("/api/v1/aws/execution-assurance/change",json={"change_id":"CHG1002","evaluation_timestamp":"2026-10-22T12:00:00Z","scenario_id":"AWS-EXEC-01"}); assert result.status_code==200 and result.json()["provider"]=="aws"
    assert client.post("/api/v1/aws/execution-assurance/user",json={"user_identity":"missing","window_days":10}).status_code==404
def test_existing_provider_smoke_routes():
    assert client.get("/api/v1/azure/execution-scenarios").status_code==200; assert client.get("/api/v1/snowflake/execution-scenarios").status_code==200
