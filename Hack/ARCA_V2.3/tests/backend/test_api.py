from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.main import app, create_app
from backend.api.routes.snowflake import service
from backend.services.timestamps import parse_utc

client = TestClient(app, raise_server_exceptions=False)


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["mode"] == "synthetic-read-only"


def test_environment_discovery_uses_registered_capabilities():
    response = client.get("/api/v1/environments")
    assert response.status_code == 200
    by_provider = {item["provider"]: item for item in response.json()["environments"]}
    assert set(by_provider) == {"aws", "azure", "snowflake"}
    assert by_provider["aws"]["capabilities"] == ["change_quality_validation", "access_validation", "execution_assurance"]
    assert by_provider["azure"]["capabilities"] == ["change_quality_validation", "access_validation", "execution_assurance"]
    assert by_provider["snowflake"]["capabilities"] == ["change_access_validation", "execution_assurance"]


def test_snowflake_changes_endpoint_returns_synthetic_records():
    response = client.get("/api/v1/snowflake/changes")
    body = response.json()
    assert response.status_code == 200
    assert body["synthetic"] is True
    assert body["count"] == 25 == len(body["items"])
    assert "CHG-SF-1007" in {item["change_id"] for item in body["items"]}


def test_snowflake_demo_scenarios_endpoint_returns_verified_catalog():
    response = client.get("/api/v1/snowflake/demo-scenarios")
    body = response.json()
    assert response.status_code == 200
    assert body["synthetic"] is True
    assert body["count"] == 27 == len(body["items"])


def test_successful_snowflake_validation_preserves_contract():
    scenarios = client.get("/api/v1/snowflake/demo-scenarios").json()["items"]
    scenario = next(item for item in scenarios if item["scenario_id"] == "SF-UNIFIED-01")
    response = client.post("/api/v1/snowflake/validate", json={
        "change_id": scenario["change_id"],
        "evaluation_timestamp": scenario["evaluation_timestamp"],
    })
    body = response.json()
    assert response.status_code == 200
    assert body["provider"] == "snowflake"
    assert body["change_id"] == "CHG-SF-1007"
    assert body["overall_status"] == body["status"] == scenario["expected_check_outcomes"]["overall"]
    assert body["schema_version"] == 1
    assert {"change_quality", "window_assessment", "role_assessment", "missing_information", "findings", "evidence", "evaluation_timestamp"} <= body.keys()
    for section in ("change_quality", "window_assessment", "role_assessment"):
        assert isinstance(body[section]["findings"], list)
        assert isinstance(body[section]["evidence"], list)


def test_omitted_timestamp_uses_engine_current_utc_behavior():
    before = datetime.now(timezone.utc)
    response = client.post("/api/v1/snowflake/validate", json={"change_id": "CHG-SF-1007"})
    after = datetime.now(timezone.utc)
    assert response.status_code == 200
    evaluated = parse_utc(response.json()["evaluation_timestamp"])
    assert before <= evaluated <= after


def test_unknown_change_returns_404_without_internal_trace():
    response = client.post("/api/v1/snowflake/validate", json={"change_id": "CHG-SF-9999"})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    assert "traceback" not in response.text.lower()


@pytest.mark.parametrize("value", ["not-a-timestamp", "2026-10-21T10:30:00"])
def test_invalid_or_timezone_free_timestamp_returns_422(value):
    response = client.post("/api/v1/snowflake/validate", json={
        "change_id": "CHG-SF-1007",
        "evaluation_timestamp": value,
    })
    assert response.status_code == 422
    assert "traceback" not in response.text.lower()


def test_cors_allows_only_configured_local_frontend():
    allowed = client.options("/api/v1/health", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
    })
    denied = client.options("/api/v1/health", headers={
        "Origin": "https://untrusted.example",
        "Access-Control-Request-Method": "GET",
    })
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_cors_allows_loopback_frontend_origin():
    allowed = client.options("/api/v1/health", headers={
        "Origin": "http://127.0.0.1:3000",
        "Access-Control-Request-Method": "GET",
    })
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_wildcard_cors_configuration_is_rejected(monkeypatch):
    monkeypatch.setenv("ARCA_API_CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="cannot use a wildcard"):
        create_app()


def test_internal_error_is_sanitized_and_logged(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("sensitive internal diagnostic")

    monkeypatch.setattr(service, "validate", fail)
    response = client.post("/api/v1/snowflake/validate", json={"change_id": "CHG-SF-1007"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Snowflake validation could not be completed."}
    assert "sensitive internal diagnostic" not in response.text
