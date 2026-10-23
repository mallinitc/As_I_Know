import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app, raise_server_exceptions=False)


def change_scenario(scenario_id: str, change_id: str):
    return client.post("/api/v1/azure/execution-assurance/change", json={
        "change_id": change_id, "scenario_id": scenario_id,
        "evaluation_timestamp": "2026-10-27T00:00:00Z",
    })


def categories(response):
    return {item["category"] for item in response.json()["findings"]}


def test_execution_scenarios_are_verified_against_existing_evidence():
    response = client.get("/api/v1/azure/execution-scenarios")
    body = response.json()
    assert response.status_code == 200
    assert body["provider"] == "azure" and body["synthetic"] is True
    assert body["count"] == 35
    assert len({item["scenario_id"] for item in body["items"]}) == 35
    restored = [item for item in body["items"] if item["source"] == "v1"]
    assert [item["scenario_name"] for item in restored] == [
        "Azure execution potential match",
        "Execution timing deviation",
        "Unexpected engineer deviation",
        "Unexpected resource modification",
        "Approved future change without execution evidence",
    ]


def test_all_azure_execution_scenarios_execute_with_exact_evidence_ids():
    scenarios = client.get("/api/v1/azure/execution-scenarios").json()["items"]
    for scenario in scenarios:
        common = {"scenario_id": scenario["scenario_id"], "evaluation_timestamp": scenario["evaluation_timestamp"]}
        if scenario["mode"] == "change":
            response = client.post("/api/v1/azure/execution-assurance/change", json={**common, "change_id": scenario["change_id"]})
        else:
            response = client.post("/api/v1/azure/execution-assurance/user", json={
                **common, "user_identity": scenario["user_identity"], "window_days": scenario["window_days"],
            })
        assert response.status_code == 200, (scenario["scenario_id"], response.text)
        assert response.json()["event_ids"] == scenario["event_data_ids"]
        assert set(scenario["expected_findings"]) == {item["category"] for item in response.json()["findings"]}


@pytest.mark.parametrize("scenario_id,change_id,status,event_ids,reasons", [
    ("S3-MATCH", "CHG-AZ-2001", "POTENTIAL_MATCH", ["az-event-0001"], []),
    ("S3-TIMING", "CHG-AZ-2007", "DEVIATION_DETECTED", ["az-event-0007"], ["UNEXPECTED_OPERATION_OR_RESOURCE"]),
    ("S3-UNEXPECTED-ACTOR", "CHG-AZ-2008", "DEVIATION_DETECTED", ["az-event-0008"], ["OUTSIDE_WINDOW"]),
    ("S3-UNEXPECTED-RESOURCE", "CHG-AZ-2009", "DEVIATION_DETECTED", ["az-event-0009"], ["ACTOR_MISMATCH"]),
    ("S3-NO-EVIDENCE", "CHG-AZ-2021", "EVIDENCE_INCOMPLETE", [], []),
])
def test_original_v1_stage3_status_events_and_reasons_are_preserved(scenario_id, change_id, status, event_ids, reasons):
    response = change_scenario(scenario_id, change_id)
    body = response.json()
    assert response.status_code == 200
    assert body["overall_status"] == status
    assert body["event_ids"] == event_ids
    assert body["v1_assessment"]["status"] == status
    assert [item["event_id"] for item in body["v1_assessment"]["events"]] == event_ids
    if event_ids:
        assert body["v1_assessment"]["events"][0]["reasons"] == reasons
    else:
        assert len(body["v1_assessment"]["missing_expected"]) == 3


def test_change_number_investigation_correlates_activity_and_pim_rbac():
    response = change_scenario("AZ-EXEC-01", "CHG-AZ-2001")
    body = response.json()
    assert response.status_code == 200
    assert body["overall_status"] == "COMPLIANT"
    assert categories(response) == {"COMPLIANT_EXECUTION"}
    assert body["timeline"][0]["change_match"] == "MATCHED"
    assert body["timeline"][0]["event_data_id"] == "az-event-0001"


@pytest.mark.parametrize("identity", ["engineer05@example.invalid", "20000000-0000-0000-0000-000000000005"])
def test_user_resolution_supports_email_and_principal_id(identity):
    response = client.post("/api/v1/azure/execution-assurance/user", json={
        "user_identity": identity, "window_days": 1,
        "evaluation_timestamp": "2026-10-26T00:00:00Z", "scenario_id": "AZ-USER-01",
    })
    assert response.status_code == 200
    assert response.json()["user"]["principal_id"] == "20000000-0000-0000-0000-000000000005"


@pytest.mark.parametrize("days", [10, 15])
def test_user_investigation_periods_are_explicit_utc(days):
    response = client.post("/api/v1/azure/execution-assurance/user", json={
        "user_identity": "engineer05@example.invalid", "window_days": days,
        "evaluation_timestamp": "2026-10-27T00:00:00Z",
    })
    body = response.json()
    assert response.status_code == 200
    assert body["period_start"] == f"2026-10-{27-days:02d}T00:00:00Z"
    assert body["period_end"] == "2026-10-27T00:00:00Z"


def test_window_implementer_resource_operation_and_failure_deviations():
    cases = [
        ("AZ-EXEC-08", "CHG-AZ-2008", "EXECUTED_OUTSIDE_WINDOW"),
        ("AZ-EXEC-09", "CHG-AZ-2009", "UNAUTHORIZED_IMPLEMENTER"),
        ("AZ-EXEC-07", "CHG-AZ-2007", "WRONG_TARGET_RESOURCE"),
        ("AZ-EXEC-24", "CHG-AZ-2024", "UNAPPROVED_OPERATION"),
        ("AZ-EXEC-22", "CHG-AZ-2022", "FAILED_EXECUTION"),
    ]
    for scenario_id, change_id, category in cases:
        response = change_scenario(scenario_id, change_id)
        assert category in categories(response), scenario_id


def test_missing_operation_unexpected_activity_and_incomplete_authorization():
    partial = change_scenario("AZ-EXEC-23", "CHG-AZ-2023")
    extra = change_scenario("AZ-EXEC-24", "CHG-AZ-2024")
    incomplete = change_scenario("AZ-EXEC-25", "CHG-AZ-2025")
    assert "EXPECTED_OPERATION_MISSING" in categories(partial)
    assert "UNEXPECTED_ADDITIONAL_OPERATION" in categories(extra)
    assert "INSUFFICIENT_AUDIT_EVIDENCE" in categories(incomplete)
    assert incomplete.json()["confidence"] == "limited"


def test_access_mismatch_is_evidence_backed_not_inferred_from_role_name():
    response = change_scenario("AZ-EXEC-04", "CHG-AZ-2004")
    assert "ROLE_OR_SCOPE_MISMATCH" in categories(response)
    assert "az-event-0004" in response.json()["event_ids"]


def test_unmatched_administrative_activity_is_possible_not_confirmed_unauthorized():
    response = client.post("/api/v1/azure/execution-assurance/user", json={
        "user_identity": "engineer05@example.invalid", "window_days": 1,
        "evaluation_timestamp": "2026-10-26T00:00:00Z", "scenario_id": "AZ-USER-01",
    })
    finding = response.json()["findings"][0]
    assert finding["category"] == "POSSIBLE_UNAPPROVED_ACTIVITY"
    assert finding["confidence"] == "possible"
    assert response.json()["timeline"][0]["change_match"] == "UNMATCHED"


def test_unknown_identity_change_invalid_period_and_scenario_are_sanitized():
    unknown_user = client.post("/api/v1/azure/execution-assurance/user", json={"user_identity": "missing@example.invalid"})
    unknown_change = client.post("/api/v1/azure/execution-assurance/change", json={"change_id": "CHG-AZ-9999"})
    invalid_period = client.post("/api/v1/azure/execution-assurance/user", json={"user_identity": "engineer01@example.invalid", "window_days": 2})
    wrong_scenario = client.post("/api/v1/azure/execution-assurance/change", json={"change_id": "CHG-AZ-2001", "scenario_id": "AZ-USER-01"})
    assert unknown_user.status_code == unknown_change.status_code == wrong_scenario.status_code == 404
    assert invalid_period.status_code == 422
    assert all("traceback" not in item.text.lower() for item in (unknown_user, unknown_change, wrong_scenario))


def test_azure_timeline_uses_event_ids_not_snowflake_query_ids():
    body = change_scenario("AZ-EXEC-01", "CHG-AZ-2001").json()
    assert body["event_ids"] == ["az-event-0001"]
    assert "query_ids" not in body
    assert {"correlation_id", "caller", "operation", "resource_id", "change_match", "deviations"} <= body["timeline"][0].keys()
