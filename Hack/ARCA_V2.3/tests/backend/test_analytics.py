from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.analytics import AnalyticsService


client = TestClient(app)


def test_overview_metrics_are_reconciled_and_deduplicated() -> None:
    result = AnalyticsService().overview()
    assert result["total_unique_changes"] == 70
    assert result["compliance_denominator"] == result["change_assurance"]["denominator"]
    assert result["noncompliant_changes"] == result["change_assurance"]["noncompliant"]
    assert sum(item["value"] for item in result["provider_risk_counts"]) == sum(item["value"] for item in result["findings_by_severity"])
    ids = [item["finding_id"] for item in result["recent_significant_findings"]]
    assert len(ids) == len(set(ids))


def test_provider_and_severity_filters_apply_consistently() -> None:
    service = AnalyticsService()
    risks = service.risks(provider="azure", severity="high")
    assert risks["findings"]
    assert all(item["provider"] == "azure" and item["severity"] == "high" for item in risks["findings"])
    assert sum(item["value"] for item in risks["findings_by_provider"]) == risks["total_findings"]


def test_time_filters_use_synthetic_reference_timestamp() -> None:
    service = AnalyticsService()
    seven = service.overview(days=7)
    fifteen = service.overview(days=15)
    thirty = service.overview(days=30)
    all_available = service.overview()
    assert seven["total_unique_changes"] <= fifteen["total_unique_changes"] <= thirty["total_unique_changes"] <= all_available["total_unique_changes"]
    assert seven["metadata"]["reference_timestamp"] == all_available["metadata"]["reference_timestamp"]


def test_unknown_outcomes_are_not_counted_as_compliant() -> None:
    result = AnalyticsService().overview(provider="snowflake")
    summary = result["change_assurance"]
    assert summary["review_or_unknown"] > 0
    assert summary["denominator"] == summary["compliant"] + summary["noncompliant"]
    assert result["compliance_rate"] == 0.0


def test_execution_evidence_coverage_has_explicit_denominator() -> None:
    result = AnalyticsService().execution()
    coverage = result["evidence_coverage"]
    assert coverage["eligible"] >= coverage["covered"] >= 0
    assert coverage["percentage"] == round(coverage["covered"] * 100 / coverage["eligible"], 1)


def test_versioned_analytics_endpoints_and_schemas() -> None:
    for endpoint in ("overview", "risks", "execution", "access"):
        response = client.get(f"/api/v1/analytics/{endpoint}", params={"provider": "aws", "days": 30, "severity": "all"})
        assert response.status_code == 200, response.text
        assert response.json()["metadata"]["synthetic"] is True


def test_invalid_analytics_filter_is_rejected() -> None:
    response = client.get("/api/v1/analytics/overview", params={"provider": "unknown"})
    assert response.status_code == 422

