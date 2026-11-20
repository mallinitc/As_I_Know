import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app, raise_server_exceptions=False)


def test_execution_scenarios_are_native_verified_catalog():
    response = client.get("/api/v1/snowflake/execution-scenarios")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "snowflake"
    assert body["synthetic"] is True
    assert body["count"] == 20 == len(body["items"])


def test_every_demo_scenario_returns_its_expected_finding_categories():
    scenarios = client.get("/api/v1/snowflake/execution-scenarios").json()["items"]
    for scenario in scenarios:
        common = {
            "evaluation_timestamp": scenario["evaluation_timestamp"],
            "scenario_id": scenario["scenario_id"],
        }
        if scenario["investigation_mode"] == "change":
            response = client.post("/api/v1/snowflake/execution-assurance/change", json={
                **common, "change_id": scenario["change_id"],
            })
        else:
            response = client.post("/api/v1/snowflake/execution-assurance/user", json={
                **common, "user_identity": scenario["user_identity"],
                "window_days": scenario["window_days"] if scenario["window_days"] in {1, 7, 10, 15, 30} else 30,
            })
        assert response.status_code == 200, (scenario["scenario_id"], response.text)
        categories = {item["category"] for item in response.json()["findings"]}
        assert set(scenario["expected_findings"]) <= categories, scenario["scenario_id"]


def test_change_assurance_compares_expected_and_observed_evidence():
    response = client.post("/api/v1/snowflake/execution-assurance/change", json={
        "change_id": "CHG-SF-1007",
        "evaluation_timestamp": "2026-11-24T00:00:00Z",
        "scenario_id": "SF-POST-01",
    })
    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "change"
    assert body["overall_status"] == "COMPLIANT"
    assert body["query_ids"] == ["SF-QRY-001"]
    assert body["expected_operations"]
    assert body["observed_operations"][0]["actor"] == "SFSECURITY01"


def test_user_mode_resolves_id_username_and_email():
    payload = {"window_days": 10, "evaluation_timestamp": "2026-11-24T00:00:00Z"}
    results = []
    for identity in ("SF-USER-014", "SFROGUE01", "rogue.engineer@example.invalid"):
        response = client.post("/api/v1/snowflake/execution-assurance/user", json={**payload, "user_identity": identity})
        assert response.status_code == 200
        results.append(response.json()["user"]["user_id"])
    assert results == ["SF-USER-014"] * 3


def test_user_window_boundary_is_inclusive_and_utc():
    response = client.post("/api/v1/snowflake/execution-assurance/user", json={
        "user_identity": "SFROGUE01", "window_days": 1,
        "evaluation_timestamp": "2026-11-21T12:00:00Z",
    })
    body = response.json()
    assert response.status_code == 200
    assert body["period_start"] == "2026-11-20T12:00:00Z"
    assert "SF-QRY-018" in body["query_ids"]


def test_unknown_identity_change_and_scenario_are_sanitized():
    unknown_user = client.post("/api/v1/snowflake/execution-assurance/user", json={"user_identity": "missing@example.invalid"})
    unknown_change = client.post("/api/v1/snowflake/execution-assurance/change", json={"change_id": "CHG-SF-9999"})
    wrong_scenario = client.post("/api/v1/snowflake/execution-assurance/change", json={
        "change_id": "CHG-SF-1007", "scenario_id": "SF-POST-17",
    })
    assert unknown_user.status_code == unknown_change.status_code == wrong_scenario.status_code == 404
    assert all("traceback" not in item.text.lower() for item in (unknown_user, unknown_change, wrong_scenario))


def test_user_time_range_is_restricted_to_supported_values():
    response = client.post("/api/v1/snowflake/execution-assurance/user", json={
        "user_identity": "SFROGUE01", "window_days": 2,
    })
    assert response.status_code == 422


@pytest.mark.parametrize("days", [1, 7, 10, 15, 30])
def test_every_supported_user_time_range_executes(days):
    response = client.post("/api/v1/snowflake/execution-assurance/user", json={
        "user_identity": "SFROGUE01", "window_days": days,
        "evaluation_timestamp": "2026-11-24T00:00:00Z",
    })
    assert response.status_code == 200


def test_unmatched_select_is_not_classified_as_unauthorized():
    response = client.post("/api/v1/snowflake/execution-assurance/user", json={
        "user_identity": "SFSECURITY05", "window_days": 1,
        "evaluation_timestamp": "2026-10-30T08:00:00Z",
    })
    categories = {item["category"] for item in response.json()["findings"]}
    assert "UNMATCHED_READ_ONLY_ACTIVITY" in categories
    assert "POSSIBLE_UNAPPROVED_ACTIVITY" not in categories


def test_missing_access_history_is_reported_as_limitation_not_final_state():
    response = client.post("/api/v1/snowflake/execution-assurance/change", json={
        "change_id": "CHG-SF-1003", "scenario_id": "SF-POST-16",
        "evaluation_timestamp": "2026-11-24T00:00:00Z",
    })
    body = response.json()
    assert any(item["category"] == "INSUFFICIENT_AUDIT_EVIDENCE" for item in body["findings"])
    assert any("final" in item.lower() for item in body["limitations"])
