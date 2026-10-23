from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.analytics import AnalyticsService
from backend.services.observability import observability_summary, record_execution_metrics


client = TestClient(app)
MANAGER = {"X-ARCA-Demo-Role": "arca_manager"}
ANALYST = {"X-ARCA-Demo-Role": "arca_analyst"}


def configure(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)


def test_feedback_is_persisted_idempotently_and_reported(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    payload = {"submission_id": "submission-0001", "assessment_id": "stage2:azure:CHG-AZ-2022", "stage": "A2", "provider": "azure", "result_reference": "CHG-AZ-2022", "finding_reference": "PIM-SCOPE", "original_decision": "OVERPRIVILEGED", "feedback_decision": "Incorrect", "feedback_reason": "Reviewer disputes the scope interpretation."}
    first = client.post("/api/v1/analytics/feedback", json=payload, headers=MANAGER)
    second = client.post("/api/v1/analytics/feedback", json=payload, headers=MANAGER)
    assert first.status_code == second.status_code == 200
    assert first.json()["feedback_id"] == second.json()["feedback_id"]
    latest = client.get("/api/v1/analytics/feedback/latest", params={"assessment_id": payload["assessment_id"], "stage": "A2"}, headers=MANAGER)
    assert latest.json()["item"]["feedback_decision"] == "Incorrect"
    summary = observability_summary(days=1, environment="azure")
    assert summary["summary"]["feedback_submissions"] == 1
    assert summary["summary"]["negative_feedback"] == 1
    assert summary["frequently_disputed"] == [{"name": "PIM-SCOPE", "value": 1}]


def test_invalid_feedback_choice_is_rejected(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    response = client.post("/api/v1/analytics/feedback", json={"submission_id": "submission-0002", "assessment_id": "a-123", "stage": "A1", "provider": "azure", "original_decision": "VALID", "feedback_decision": "Maybe", "feedback_reason": ""}, headers=ANALYST)
    assert response.status_code == 422


def test_execution_metrics_filters_and_unknown_cost(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    record_execution_metrics({"agent_id": "A5", "environment": "azure", "execution_mode": "llm_assisted", "provider": "openai", "model_identifier": "unpriced-model", "llm_invocation_status": "completed", "model_call_count": 1, "input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "model_execution_time_ms": 90, "total_analysis_time_ms": 110, "estimated_cost_usd": None, "pricing_catalog_version": None, "cost_status": "pricing_unavailable", "call_details": []})
    azure = observability_summary(days=1, environment="azure", agent="A5", provider="openai")
    aws = observability_summary(days=1, environment="aws")
    assert azure["summary"]["total_llm_calls"] == 1
    assert azure["summary"]["estimated_cost_usd"] is None
    assert azure["performance"]["p95_ms"] is None
    assert aws["summary"]["total_executions"] == 0


def test_observability_endpoint_and_exports(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    response = client.get("/api/v1/analytics/observability", params={"days": 1, "environment": "all", "agent": "all"}, headers=MANAGER)
    assert response.status_code == 200
    assert response.json()["metadata"]["source"] == "V2 local metadata-only telemetry"
    assert client.get("/api/v1/analytics/observability/export/executions", params={"days": 1}, headers=MANAGER).status_code == 200
    assert client.get("/api/v1/analytics/observability", params={"days": 3}, headers=MANAGER).status_code == 422


def test_executive_dashboard_separates_undocumented_from_unauthorized():
    result = AnalyticsService().overview(provider="azure", days=7)
    assert result["potentially_undocumented_changes"] == 14
    assert len({tuple(item.get("evidence_ids") or []) for item in result["undocumented_activity"]}) == len(result["undocumented_activity"])
    assert result["successfully_verified_changes"] <= result["approved_changes"]
    assert "potentially_undocumented_changes" in result
