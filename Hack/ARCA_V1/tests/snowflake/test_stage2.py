from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from arca.observability import log_assessment
from arca.providers import get_provider, provider_capabilities
from arca.snowflake_stage2 import assess_requested_role, presentation_findings, validate_change_window
from arca.demo_catalog import demo_scenarios
from arca.workflow import build

UTC = timezone.utc


@pytest.fixture(scope="module")
def evidence():
    adapter = get_provider("snowflake")
    bundle = adapter.load_bundle()
    return adapter, bundle, {item["change_id"]: item for item in bundle["changes"]}


def at(day, hour=10, minute=30):
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def test_window_active_and_boundaries(evidence):
    change = evidence[2]["CHG-SF-1001"]
    assert validate_change_window(change, at(1))["status"] == "ACTIVE"
    assert validate_change_window(change, at(1, 10, 0))["status"] == "ACTIVE"
    assert validate_change_window(change, at(1, 11, 0))["status"] == "EXPIRED"


def test_window_not_started_expired_and_unapproved(evidence):
    changes = evidence[2]
    assert validate_change_window(changes["CHG-SF-1001"], at(1, 9, 59))["status"] == "NOT_STARTED"
    assert validate_change_window(changes["CHG-SF-1001"], at(1, 12, 0))["status"] == "EXPIRED"
    assert validate_change_window(changes["CHG-SF-1005"], at(5))["status"] == "NOT_APPROVED"


def test_window_invalid_timestamp_and_missing_approval(evidence):
    changes = evidence[2]
    assert validate_change_window(changes["CHG-SF-1010"], at(10))["status"] == "NEED_MORE_INFO"
    missing = deepcopy(changes["CHG-SF-1001"]); missing["state"] = ""
    assert validate_change_window(missing, at(1))["status"] == "NEED_MORE_INFO"


def test_requested_role_appropriate(evidence):
    result = assess_requested_role(evidence[2]["CHG-SF-1007"], evidence[1])
    assert result["status"] == "APPROPRIATE"
    assert "sf-object-grant-001" in result["evidence"]


def test_requested_role_overprivileged_with_defensible_recommendation(evidence):
    result = assess_requested_role(evidence[2]["CHG-SF-1008"], evidence[1])
    assert result["status"] == "OVERPRIVILEGED"
    assert result["recommended_role"] == "REPORTING_DDL_ADMIN"
    assert result["required_privileges"] == [{"object_name": "FINANCE_DB.REPORTING.TRANSACTIONS", "object_type": "TABLE", "privilege": "OWNERSHIP"}]


def test_requested_role_insufficient(evidence):
    result = assess_requested_role(evidence[2]["CHG-SF-1001"], evidence[1])
    assert result["status"] == "INSUFFICIENT_PRIVILEGES"
    assert result["missing_privileges"]


def test_inherited_privileges_and_object_ownership(evidence):
    change = deepcopy(evidence[2]["CHG-SF-1008"])
    change["snowflake_context"]["requested_role"] = "SYSADMIN"
    change["description"] = "Alter the approved reporting table."
    result = assess_requested_role(change, evidence[1])
    assert result["status"] == "OVERPRIVILEGED"
    assert "sf-role-grant-004" in result["evidence"]
    assert any(item["privilege"] == "OWNERSHIP" for item in result["effective_privileges"])


def test_incorrect_object_scope_is_insufficient(evidence):
    change = deepcopy(evidence[2]["CHG-SF-1008"])
    change["snowflake_context"]["requested_role"] = "REPORTING_DDL_ADMIN"
    change["description"] = "Alter another table."
    change["expected"][0]["resource_id"] = "FINANCE_DB.REPORTING.OTHER_TABLE"
    assert assess_requested_role(change, evidence[1])["status"] == "INSUFFICIENT_PRIVILEGES"


def test_missing_unknown_and_incomplete_role_evidence(evidence):
    bundle, changes = evidence[1], evidence[2]
    missing = deepcopy(changes["CHG-SF-1014"]); missing["snowflake_context"]["requested_role"] = ""; missing["description"] = "Modify the approved warehouse."
    assert assess_requested_role(missing, bundle)["status"] == "NEED_MORE_INFO"
    unknown = deepcopy(missing); unknown["snowflake_context"]["requested_role"] = "UNKNOWN_ROLE"
    assert assess_requested_role(unknown, bundle)["status"] == "NEED_MORE_INFO"
    incomplete = deepcopy(changes["CHG-SF-1008"])
    incomplete["snowflake_context"]["requested_role"] = "CATALOG_INCOMPLETE_ROLE"
    incomplete["description"] = "Alter the approved reporting table."
    assert assess_requested_role(incomplete, bundle)["status"] == "MANUAL_REVIEW"


def test_multiple_operations_require_combined_privileges(evidence):
    result = assess_requested_role(evidence[2]["CHG-SF-1012"], evidence[1])
    assert result["status"] == "INSUFFICIENT_PRIVILEGES"
    assert any(item["privilege"] == "MANAGE GRANTS" for item in result["missing_privileges"])


def test_description_and_metadata_conflict(evidence):
    result = assess_requested_role(evidence[2]["CHG-SF-1009"], evidence[1])
    assert result["status"] == "MANUAL_REVIEW"
    assert result["requested_role"] == "USERADMIN"
    assert result["description_role"] == "ACCOUNTADMIN"


def test_unsupported_operation_requires_manual_review(evidence):
    change = deepcopy(evidence[2]["CHG-SF-1007"])
    change["expected"] = [{"operation": "DROP NETWORK POLICY", "resource_id": "POLICY:OLD_POLICY"}]
    assert assess_requested_role(change, evidence[1])["status"] == "MANUAL_REVIEW"


def test_warehouse_operator_is_appropriate(evidence):
    result = assess_requested_role(evidence[2]["CHG-SF-1014"], evidence[1])
    assert result["status"] == "APPROPRIATE"
    assert {item["privilege"] for item in result["effective_privileges"]} >= {"MODIFY", "USAGE"}


def test_stage2_preserves_both_results(evidence):
    result = evidence[0].evaluate_stage2(evidence[2]["CHG-SF-1008"], {}, {**evidence[1], "evaluation_time": at(8)})
    assert result["window_assessment"]["status"] == "ACTIVE"
    assert result["role_assessment"]["status"] == "OVERPRIVILEGED"
    assert result["status"] == "RECOMMEND_LESSER_ROLE"


def test_workflow_runs_unified_stage1_only(evidence, monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock")
    context = {**evidence[1], "evaluation_time": at(7, 10, 15)}
    result = build().invoke({"provider": "snowflake", "change": evidence[2]["CHG-SF-1007"],
                             "access_request": {}, "context": context})
    assert result["stage1"]["status"] == "PASS"
    assert result["stage1"]["window_assessment"]["status"] == "ACTIVE"
    assert result["stage1"]["role_assessment"]["status"] == "APPROPRIATE"
    assert "stage2" not in result and "stage3" not in result and "investigation" not in result
    assert provider_capabilities("snowflake") == {"stage1", "post_implementation", "undocumented", "investigation"}


def test_snowflake_logs_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCA_LOG_DIR", str(tmp_path / "logs"))
    log_assessment(feature="Stage 2 Snowflake Validation", environment="snowflake", final_status="APPROPRIATE")
    assert (tmp_path / "logs" / "snowflake" / "assessments.jsonl").is_file()
    assert not (tmp_path / "logs" / "aws" / "assessments.jsonl").exists()
    assert not (tmp_path / "logs" / "azure" / "assessments.jsonl").exists()


def test_snowflake_unified_stage1_ui_and_no_later_stages(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock"); monkeypatch.setenv("LLM_PROVIDER", "mock")
    app = AppTest.from_file(Path(__file__).resolve().parents[2] / "app.py").run(timeout=30)
    next(widget for widget in app.selectbox if widget.label == "Environment").set_value("snowflake").run(timeout=30)
    assessment = next(widget for widget in app.segmented_control if widget.label == "Assessment")
    assert list(assessment.options) == ["Change & Access Validation", "Post-Implementation Validation"]
    assert "Full Lifecycle Assessment" not in assessment.options
    assert "Stage 3 — Verify Execution" not in assessment.options
    demo = next(widget for widget in app.selectbox if widget.label == "Verified Demo Example")
    demo.set_value("SF-UNIFIED-01").run(timeout=30)
    assert any(button.label == "Run Validation" for button in app.button)
    next(button for button in app.button if button.label == "Run Validation").click().run(timeout=30)
    assert not list(app.exception)
    rendered = "\n".join(item.value for item in app.markdown)
    assert "CHANGE WINDOW" in rendered and "REQUESTED ROLE & ACCESS ASSESSMENT" in rendered


def test_legacy_stage2_demo_catalog_scenarios_execute_real_assessments(evidence):
    adapter, bundle, changes = evidence
    scenarios = demo_scenarios("snowflake_stage2", "snowflake")
    assert len(scenarios) == 15
    for scenario in scenarios:
        result = adapter.evaluate_stage2(changes[scenario["associated_change_number"]], {},
                                         {**bundle, "evaluation_time": scenario["inputs"]["evaluation_time"]})
        assert result["status"] == scenario["expected_outcome"]


def test_findings_are_classified_from_actual_results(evidence):
    adapter, bundle, changes = evidence
    expired = adapter.evaluate_stage2(changes["CHG-SF-1007"], {}, {**bundle, "evaluation_time": at(7, 11)})
    assert presentation_findings(changes["CHG-SF-1007"], expired)["Validation Issues"][0]["field"] == "Change Window"
    excessive = adapter.evaluate_stage2(changes["CHG-SF-1008"], {}, {**bundle, "evaluation_time": at(8)})
    risk = presentation_findings(changes["CHG-SF-1008"], excessive)["Access Risk Findings"][0]
    assert risk["current_value"] == "ACCOUNTADMIN" and "REPORTING_DDL_ADMIN" in risk["recommendation"]
    missing = adapter.evaluate_stage2(changes["CHG-SF-1017"], {}, {**bundle, "evaluation_time": at(17)})
    assert presentation_findings(changes["CHG-SF-1017"], missing)["Missing Information"][0]["field"] == "Requested Snowflake Role"


def test_demo_selection_populates_change_time_and_clears_stale_result(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock"); monkeypatch.setenv("LLM_PROVIDER", "mock")
    app = AppTest.from_file(Path(__file__).resolve().parents[2] / "app.py").run(timeout=30)
    next(widget for widget in app.selectbox if widget.label == "Environment").set_value("snowflake")
    app.run(timeout=30)
    demo = next(widget for widget in app.selectbox if widget.label == "Verified Demo Example")
    demo.set_value("SF-UNIFIED-02").run(timeout=30)
    selected = next(widget for widget in app.selectbox if widget.label == "Approved Change Record")
    assert selected.value == "CHG-SF-1008"
    assert any("Demo Evaluation Time" in item.value and "08 Nov 2026, 10:30 UTC" in item.value for item in app.markdown)
    next(button for button in app.button if button.label == "Run Validation").click().run(timeout=30)
    assert app.session_state["snowflake_unified_result"]["status"] == "OVERPRIVILEGED"
    next(widget for widget in app.selectbox if widget.label == "Verified Demo Example").set_value("SF-UNIFIED-03").run(timeout=30)
    assert "snowflake_unified_result" not in app.session_state
    assert next(widget for widget in app.selectbox if widget.label == "Approved Change Record").value == "CHG-SF-1001"


def test_invalid_timestamp_is_reported_as_missing_validation_evidence(evidence):
    adapter, bundle, changes = evidence
    result = adapter.evaluate_stage2(changes["CHG-SF-1010"], {}, {**bundle, "evaluation_time": at(10)})
    finding = presentation_findings(changes["CHG-SF-1010"], result)["Missing Information"][0]
    assert finding["field"] == "Approved Change Window"
    assert "invalid" in finding["problem"].lower()


def test_aws_and_azure_stage2_capabilities_unchanged():
    expected = {"stage1", "stage2", "stage3", "lifecycle", "undocumented", "investigation"}
    assert expected <= provider_capabilities("aws")
    assert expected <= provider_capabilities("azure")
