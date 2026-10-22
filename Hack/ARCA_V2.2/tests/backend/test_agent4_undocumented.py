from fastapi.testclient import TestClient

from backend.main import app
from backend.services.risk_investigation import RiskInvestigationService


service = RiskInvestigationService()
client = TestClient(app, raise_server_exceptions=False)


def by_id(result, evidence_id):
    return next(item for item in result["activity_timeline"] if item["evidence_id"] == evidence_id)


def test_original_v1_azure_demo_catalog_and_actual_outcomes():
    expected = {
        "UD-AZ-24H": ("Azure unmatched activity — 24 hours", 1, 10),
        "UD-AZ-2D": ("Azure unmatched activity — 2 days", 2, 10),
        "UD-AZ-7D": ("Azure unmatched activity — 7 days", 7, 14),
        "UD-AZ-15D": ("Azure unmatched activity — 15 days", 15, 14),
    }
    catalog = {item["scenario_id"]: item for item in service.scenarios()}
    for scenario_id, (name, days, count) in expected.items():
        scenario = catalog[scenario_id]
        assert scenario["scenario_name"] == name
        assert scenario["window_days"] == days
        result = service.investigate(scenario_id=scenario_id)
        assert len(result["findings"]) == count
        assert {item["category"] for item in result["findings"]} == {"UNMATCHED_IN_AVAILABLE_RECORDS"}


def test_exact_match_is_documented_without_an_unmatched_finding():
    result = service.investigate(environment="azure", window_days=7, evaluation_timestamp="2026-10-26T08:20:00Z")
    event = by_id(result, "az-event-0001")
    assert event["correlation"] == "MATCHED_APPROVED_CHANGE"
    assert event["change_id"] == "CHG-AZ-2001"
    assert event["approval_state"] == "approved"
    assert not any("az-event-0001" in item["evidence_ids"] for item in result["findings"])


def test_v1_actor_window_and_operation_resource_mismatch_rules():
    result = service.investigate(environment="azure", window_days=7, evaluation_timestamp="2026-10-26T08:20:00Z")
    assert by_id(result, "az-event-0007")["correlation_reasons"] == ["OPERATION_OR_RESOURCE_MISMATCH"]
    assert by_id(result, "az-event-0008")["correlation_reasons"] == ["OUTSIDE_CHANGE_WINDOW"]
    assert by_id(result, "az-event-0009")["correlation_reasons"] == ["ACTOR_MISMATCH"]


def test_time_filter_is_backend_applied_and_uses_demo_reference_clock():
    one_day = service.investigate(environment="azure", window_days=1)
    two_days = service.investigate(environment="azure", window_days=2)
    assert one_day["period_end"] == "2026-10-26T08:20:00Z"
    assert one_day["period_start"] == "2026-10-25T08:20:00Z"
    assert {item["evidence_id"] for item in one_day["activity_timeline"]} <= {item["evidence_id"] for item in two_days["activity_timeline"]}
    assert len(one_day["findings"]) == 10


def test_evidence_preserves_provider_actor_operation_resource_time_and_correlation():
    result = service.investigate(scenario_id="UD-AZ-24H")
    reference = result["evidence_references"][0]
    assert reference["provider"] == "azure"
    assert reference["source"] == "Azure Activity Log"
    assert {"evidence_id", "resource_id", "operation", "actor", "actor_principal_id", "timestamp", "correlation_id", "classification", "correlation_reasons"} <= reference.keys()
    assert all(item["confidence"] == "possible" for item in result["findings"])
    assert "not confirmed malicious activity" in " ".join(result["evidence_limitations"])


def test_provider_isolation_and_existing_legacy_scenarios_remain_compatible():
    azure = service.investigate(scenario_id="UD-AZ-24H")
    assert azure["providers_investigated"] == ["azure"]
    assert {item["provider"] for item in azure["activity_timeline"]} == {"azure"}
    assert "POSSIBLE_UNAPPROVED_ACTIVITY" in {item["category"] for item in service.investigate(scenario_id="RISK-04")["findings"]}
    assert service.investigate(scenario_id="RISK-01")["providers_investigated"] == ["aws"]
    assert service.investigate(scenario_id="RISK-07")["providers_investigated"] == ["snowflake"]


def test_api_contract_and_deterministic_fallback_do_not_invoke_llm():
    response = client.post("/api/v1/investigations/risk", json={"scenario_id": "UD-AZ-24H", "environment": "azure", "window_days": 1, "severity": "all", "execution_mode": "deterministic"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_analysis"]["llm_invoked"] is False
    assert payload["ai_analysis"]["execution_mode"] == "deterministic"
    assert payload["findings"][0]["category"] == "UNMATCHED_IN_AVAILABLE_RECORDS"

