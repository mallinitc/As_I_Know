from fastapi.testclient import TestClient

from backend.main import app
from backend.services.aws_validation import AwsValidationService


client = TestClient(app, raise_server_exceptions=False)
service = AwsValidationService()


def test_aws_catalogs_are_synthetic_and_have_twenty_scenarios():
    changes = client.get("/api/v1/aws/changes")
    scenarios = client.get("/api/v1/aws/demo-scenarios")
    assert changes.status_code == scenarios.status_code == 200
    assert changes.json()["synthetic"] is scenarios.json()["synthetic"] is True
    assert changes.json()["count"] >= 20
    assert scenarios.json()["count"] >= 20


def test_change_quality_valid_missing_and_inconsistent():
    assert service.validate_change("CHG1002")["overall_status"] == "VALID"
    assert service.validate_change("CHG1003")["overall_status"] == "INCOMPLETE"
    invalid = service.validate_change("CHG1005")
    assert invalid["overall_status"] == "INCONSISTENT"
    assert "INVALID_CHANGE_WINDOW" in {item["category"] for item in invalid["findings"]}


def test_iam_matching_explicit_deny_and_wildcards():
    assert service.validate_access("CHG1007")["overall_status"] == "APPROPRIATE_WITH_LIMITATIONS"
    denied = service.validate_access("CHG1010")
    assert denied["overall_status"] == "EXPLICITLY_DENIED"
    assert "EXPLICIT_DENY" in {item["category"] for item in denied["findings"]}
    broad = service.validate_access("CHG1001")
    assert broad["overall_status"] == "OVERPRIVILEGED"
    assert "ACTION_WILDCARD" in {item["category"] for item in broad["findings"]}


def test_iam_missing_conditions_excess_and_insufficient():
    assert service.validate_access("CHG1013")["overall_status"] == "NEED_MORE_INFO"
    assert service.validate_access("CHG1019")["overall_status"] == "MANUAL_REVIEW_REQUIRED"
    assert service.validate_access("CHG1009")["overall_status"] == "OVERPRIVILEGED"
    assert service.validate_access("CHG1008")["overall_status"] == "INSUFFICIENT_ACCESS"
    assert service.validate_access("CHG1020")["overall_status"] == "INSUFFICIENT_ACCESS"


def test_all_aws_demo_scenarios_execute_deterministically():
    scenarios = service.list_demo_scenarios()
    for scenario in scenarios:
        result = service.validate_change(scenario["change_id"]) if scenario["stage"] == "change" else service.validate_access(scenario["change_id"])
        assert result["provider"] == "aws"
        assert result["change_id"] == scenario["change_id"]
        assert result["overall_status"] == scenario["expected_status"]
        categories = {item["category"] for item in result["findings"]}
        assert set(scenario["expected_findings"]) <= categories


def test_aws_api_contract_and_unknown_change():
    response = client.post("/api/v1/aws/validate/access", json={"change_id": "CHG1010"})
    assert response.status_code == 200
    assert {"permission_evaluations", "findings", "evidence", "limitations"} <= response.json().keys()
    unknown = client.post("/api/v1/aws/validate/change", json={"change_id": "CHG9999"})
    assert unknown.status_code == 404
    assert "traceback" not in unknown.text.lower()


def test_azure_and_snowflake_smoke_routes_remain_available():
    assert client.get("/api/v1/azure/changes").status_code == 200
    assert client.get("/api/v1/snowflake/changes").status_code == 200
