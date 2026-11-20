import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.repositories.azure import AzureRepository
from backend.services.stage2 import Stage2Service, activation_state, parse_records


client = TestClient(create_app(), raise_server_exceptions=False)
service = Stage2Service()


def test_all_original_v1_stage2_scenarios_are_exposed():
    items = service.scenarios()
    assert len(items) == 15
    assert {item["mode"] for item in items} == {"change", "user", "paste"}
    assert items[0]["scenario_id"] == "S2C-APPROPRIATE"


def test_all_change_scenarios_retain_v1_outcomes():
    for scenario in [item for item in service.scenarios() if item["mode"] == "change"]:
        result = service.assess("change", change_id=scenario["change_id"])
        assert result["overall_assessment"] == scenario["expected_outcome"], scenario["scenario_id"]


def test_every_original_user_and_paste_scenario_retains_v1_outcome():
    for scenario in [item for item in service.scenarios() if item["mode"] != "change"]:
        if scenario["mode"] == "user":
            result = service.assess("user", change_id=scenario["change_id"], user_identity=scenario["user_identity"], access_state=scenario["access_state"])
        else:
            result = service.assess("paste", change_id=scenario["change_id"], records_text=service.scenario_records(scenario["pim_request_ids"]))
        assert result["overall_assessment"] == scenario["expected_outcome"], scenario["scenario_id"]


def test_user_lookup_by_upn_and_object_id_and_filter():
    at = datetime(2026, 10, 21, 10, 30, tzinfo=timezone.utc)
    by_upn = service.assess("user", user_identity="ENGINEER01@EXAMPLE.INVALID", evaluation_timestamp=at)
    by_id = service.assess("user", user_identity="20000000-0000-0000-0000-000000000001", evaluation_timestamp=at)
    assert {x["pim_request_id"] for x in by_upn["records"]} == {x["pim_request_id"] for x in by_id["records"]}
    active = service.assess("user", user_identity="engineer01@example.invalid", access_state="Active", evaluation_timestamp=at)
    assert all(item["activation_status"] == "Active" for item in active["records"])


def test_approval_is_not_treated_as_activation():
    repository = AzureRepository()
    request = repository.pim_requests()[0]
    at = datetime(2026, 10, 20, 10, 30, tzinfo=timezone.utc)
    assert activation_state(request, repository.rbac_assignments(), at) == "Active"
    assert activation_state(request, [], at) == "Inactive"


def test_json_and_human_readable_paste_preserve_explicit_values():
    source = AzureRepository().pim_requests()[0]
    assert parse_records(json.dumps(source))[0]["pim_request_id"] == "pim-az-0001"
    record = parse_records("Principal: engineer@example.invalid\nRole: Contributor\nScope: /subscriptions/demo\nChange ID: CHG-AZ-2001")
    assert record[0]["principal_name"] == "engineer@example.invalid"
    assert record[0]["role_name"] == "Contributor"


def test_multiple_pasted_records_and_conflicting_reference():
    repo = AzureRepository()
    payload = json.dumps(repo.pim_requests()[20:23])
    result = service.assess("paste", records_text=payload)
    assert len(result["records"]) == 3
    assert result["overall_assessment"] == "APPROVE_RECOMMENDED"
    conflict = service.assess("change", change_id="CHG-AZ-2025")
    assert conflict["overall_assessment"] == "MANUAL_REVIEW_REQUIRED"


def test_stage2_api_validation_and_missing_evidence():
    response = client.get("/api/v1/agents/access-intelligence/stage2/demo-scenarios")
    assert response.status_code == 200 and response.json()["count"] == 15
    valid = client.post("/api/v1/agents/access-intelligence/stage2/assess", json={"mode":"change","change_id":"CHG-AZ-2021"})
    assert valid.status_code == 200 and valid.json()["overall_assessment"] == "APPROVE_RECOMMENDED"
    missing = client.post("/api/v1/agents/access-intelligence/stage2/assess", json={"mode":"change","change_id":"CHG-AZ-9999"})
    assert missing.status_code == 200 and missing.json()["overall_assessment"] == "NEED_MORE_INFO"
    malformed = client.post("/api/v1/agents/access-intelligence/stage2/assess", json={"mode":"paste","records_text":"not a record"})
    assert malformed.status_code == 422
