from copy import deepcopy

from fastapi.testclient import TestClient

from backend.main import app
from backend.repositories.azure import AzureRepository
from backend.services.azure_validation import AzureValidationService, _permission_allows, validate_change_quality


client = TestClient(app, raise_server_exceptions=False)


def test_azure_changes_and_scenarios_load_existing_evidence():
    changes = client.get("/api/v1/azure/changes")
    scenarios = client.get("/api/v1/azure/demo-scenarios")
    assert changes.status_code == scenarios.status_code == 200
    assert changes.json()["count"] == 25
    assert scenarios.json()["count"] == 50
    assert {item["stage"] for item in scenarios.json()["items"]} == {"change", "access"}
    assert len({item["scenario_id"] for item in scenarios.json()["items"]}) == 50


def test_every_azure_demo_scenario_executes_its_declared_stage():
    scenarios = client.get("/api/v1/azure/demo-scenarios").json()["items"]
    for scenario in scenarios:
        endpoint = "/api/v1/azure/validate/change" if scenario["stage"] == "change" else "/api/v1/azure/validate/access"
        response = client.post(endpoint, json={"change_id": scenario["change_id"]})
        assert response.status_code == 200, scenario["scenario_id"]
        assert response.json()["stage"] == scenario["stage"]


def test_stage1_valid_and_incomplete_change_quality():
    valid = client.post("/api/v1/azure/validate/change", json={"change_id": "CHG-AZ-2001"})
    incomplete = client.post("/api/v1/azure/validate/change", json={"change_id": "CHG-AZ-2002"})
    assert valid.status_code == incomplete.status_code == 200
    assert valid.json()["overall_status"] == "VALID"
    assert incomplete.json()["overall_status"] == "INCOMPLETE"
    finding = incomplete.json()["findings"][0]
    assert finding["field"] == "description"
    assert {"actual", "expected", "recommendation"} <= finding.keys()


def test_stage1_invalid_timestamp_and_window_are_deterministic():
    repository = AzureRepository()
    change = deepcopy(repository.changes()[0])
    change["start"] = "2026-10-20T11:00:00Z"
    change["end"] = "2026-10-20T10:00:00Z"
    result = validate_change_quality(change, repository.resources())
    assert result["overall_status"] == "INCONSISTENT"
    assert "INVALID_CHANGE_WINDOW" in {item["category"] for item in result["findings"]}
    change["start"] = "not-a-timestamp"
    result = validate_change_quality(change, repository.resources())
    assert "INVALID_TIMESTAMP" in {item["category"] for item in result["findings"]}


def test_stage2_valid_pim_correlation_and_least_privilege():
    response = client.post("/api/v1/azure/validate/access", json={"change_id": "CHG-AZ-2001"})
    body = response.json()
    assert response.status_code == 200
    assert body["overall_status"] == "APPROVE_RECOMMENDED"
    assert body["missing_operations"] == []
    assert body["pim_assessments"][0]["pim_request_id"] == "pim-az-0001"


def test_stage2_detects_overprivilege_scope_duration_and_insufficient_access():
    cases = {
        "CHG-AZ-2003": ("OVERPRIVILEGED", "OVERPRIVILEGED_ROLE"),
        "CHG-AZ-2004": ("INSUFFICIENT_ACCESS", "INSUFFICIENT_PRIVILEGES"),
        "CHG-AZ-2005": ("MANUAL_REVIEW_REQUIRED", "EXCESSIVE_SCOPE"),
        "CHG-AZ-2006": ("MANUAL_REVIEW_REQUIRED", "EXCESSIVE_ACCESS_DURATION"),
    }
    for change_id, (status, category) in cases.items():
        body = client.post("/api/v1/azure/validate/access", json={"change_id": change_id}).json()
        assert body["overall_status"] == status
        assert category in {item["category"] for item in body["findings"]}


def test_stage2_aggregates_multiple_requests_without_combining_principals_incorrectly():
    three_roles = client.post("/api/v1/azure/validate/access", json={"change_id": "CHG-AZ-2021"}).json()
    two_people = client.post("/api/v1/azure/validate/access", json={"change_id": "CHG-AZ-2024"}).json()
    assert three_roles["overall_status"] == "APPROVE_RECOMMENDED"
    assert len(three_roles["pim_assessments"]) == 3
    assert len(three_roles["covered_operations"]) == 3
    assert two_people["overall_status"] == "APPROVE_RECOMMENDED"
    assert len(two_people["pim_assessments"]) == 2


def test_missing_pim_and_unknown_role_return_need_more_info(monkeypatch):
    service = AzureValidationService()
    monkeypatch.setattr(service.repository, "pim_requests", lambda: [])
    missing = service.validate_access("CHG-AZ-2001")
    assert missing["overall_status"] == "NEED_MORE_INFO"
    assert "MISSING_PIM_REQUEST" in {item["category"] for item in missing["findings"]}

    service = AzureValidationService()
    monkeypatch.setattr(service.repository, "role_definitions", lambda: [])
    unknown = service.validate_access("CHG-AZ-2001")
    assert unknown["overall_status"] == "NEED_MORE_INFO"
    assert "UNKNOWN_ROLE_DEFINITION" in {item["category"] for item in unknown["findings"]}


def test_role_semantics_apply_not_actions_and_data_actions():
    denied = {"permissions": [{"actions": ["Microsoft.Storage/*"], "not_actions": ["Microsoft.Storage/storageAccounts/delete"], "data_actions": [], "not_data_actions": []}]}
    data = {"permissions": [{"actions": [], "not_actions": [], "data_actions": ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"], "not_data_actions": []}]}
    assert _permission_allows(denied, "Microsoft.Storage/storageAccounts/write") == (True, "management")
    assert _permission_allows(denied, "Microsoft.Storage/storageAccounts/delete") == (False, None)
    assert _permission_allows(data, "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read") == (True, "data")


def test_wrong_justification_and_unknown_change_are_sanitized():
    contradiction = client.post("/api/v1/azure/validate/access", json={"change_id": "CHG-AZ-2025"})
    missing = client.post("/api/v1/azure/validate/change", json={"change_id": "CHG-AZ-9999"})
    assert "JUSTIFICATION_CONTRADICTION" in {item["category"] for item in contradiction.json()["findings"]}
    assert missing.status_code == 404
    assert "traceback" not in missing.text.lower()


def test_invalid_request_shape_returns_422():
    response = client.post("/api/v1/azure/validate/access", json={"change_id": "../../secret"})
    assert response.status_code == 422
