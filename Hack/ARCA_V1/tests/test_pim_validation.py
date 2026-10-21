from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from arca.pim_validation import activation_state, assess_combined_pim, assess_pim, find_pim_requests, find_pim_requests_by_change, parse_pim_record, parse_pim_records, record_from_evidence
from arca.providers import get_provider


@pytest.fixture()
def bundle():
    return get_provider("azure").load_bundle()


def test_parse_valid_pim_json(bundle):
    source = bundle["access_requests"][0]
    record = parse_pim_record(json.dumps(source))
    assert record.pim_request_id == "pim-az-0001"
    assert record.change_id == "CHG-AZ-2001"
    assert record.principal_name == "engineer01@example.invalid"
    assert not record.missing


def test_parse_incomplete_human_pim_record():
    record = parse_pim_record("Principal: engineer@example.invalid\nRole: Contributor")
    assert "scope" in record.missing
    assert "change_id" in record.missing
    assert record.requested_start == ""


def test_lookup_by_upn_and_principal_id_finds_multiple_requests(bundle):
    by_upn = find_pim_requests(bundle, "ENGINEER01@EXAMPLE.INVALID", "All", datetime(2026, 10, 21, 10, 30, tzinfo=timezone.utc))
    by_id = find_pim_requests(bundle, "20000000-0000-0000-0000-000000000001", "All", datetime(2026, 10, 21, 10, 30, tzinfo=timezone.utc))
    assert len(by_upn) >= 2
    assert {item["pim_request_id"] for item in by_upn} == {item["pim_request_id"] for item in by_id}


def test_activation_is_derived_from_assignment_not_approval(bundle):
    request = bundle["access_requests"][0]
    assert activation_state(request, bundle["rbac_assignments"], datetime(2026, 10, 20, 10, 30, tzinfo=timezone.utc)) == "Active"
    assert activation_state(request, bundle["rbac_assignments"], datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)) == "Scheduled"
    assert activation_state(request, [], datetime(2026, 10, 20, 10, 30, tzinfo=timezone.utc)) == "Inactive"


def test_missing_change_reference_is_evidence_insufficient(bundle):
    record = record_from_evidence(bundle["access_requests"][0]).model_copy(update={"change_id": "", "justification": "routine work", "missing": ["change_id"]})
    result = assess_pim(record, bundle)
    assert result.overall_assessment == "NEED_MORE_INFO"
    assert "corresponding_change_record" in result.missing_information or "change_id" in result.missing_information


def test_unapproved_change_requires_manual_review(bundle):
    context = deepcopy(bundle)
    context["changes"][0]["state"] = "draft"
    result = assess_pim(record_from_evidence(context["access_requests"][0]), context)
    assert result.overall_assessment == "MANUAL_REVIEW_REQUIRED"
    assert "CHANGE_NOT_APPROVED" in result.findings


def test_implementer_mismatch(bundle):
    record = record_from_evidence(bundle["access_requests"][0]).model_copy(update={"principal_id": "different-object-id"})
    result = assess_pim(record, bundle)
    assert result.overall_assessment == "MANUAL_REVIEW_REQUIRED"
    assert result.principal_match["status"] == "MISMATCH"


def test_excessive_role_recommends_catalog_role(bundle):
    result = assess_pim(record_from_evidence(bundle["access_requests"][2]), bundle)
    assert result.overall_assessment == "RECOMMEND_LESSER_ROLE"
    assert result.recommended_role == "Website Contributor"


def test_excessive_scope(bundle):
    result = assess_pim(record_from_evidence(bundle["access_requests"][4]), bundle)
    assert result.overall_assessment == "OVERPRIVILEGED"
    assert result.scope_assessment["status"] == "EXCESSIVE"


def test_excessive_duration_and_activation_outside_window(bundle):
    result = assess_pim(record_from_evidence(bundle["access_requests"][5]), bundle)
    assert result.overall_assessment == "OVERPRIVILEGED"
    assert result.duration_assessment["status"] == "EXCESSIVE_OR_OUTSIDE_WINDOW"
    assert "ACTIVATION_OUTSIDE_CHANGE_WINDOW" in result.findings


def test_insufficient_permissions(bundle):
    result = assess_pim(record_from_evidence(bundle["access_requests"][3]), bundle)
    assert result.overall_assessment == "INSUFFICIENT_ACCESS"
    assert result.role_assessment["missing_actions"]


def test_appropriate_least_privilege_request(bundle):
    result = assess_pim(record_from_evidence(bundle["access_requests"][0]), bundle)
    assert result.overall_assessment == "APPROVE_RECOMMENDED"
    assert result.recommended_role == "Storage Account Contributor"
    assert result.scope_assessment["status"] == "APPROPRIATE"


def test_stage2_executes_without_stage1_or_stage3(bundle, monkeypatch):
    adapter = get_provider("azure")
    monkeypatch.setattr(adapter, "evaluate_stage1", lambda *args, **kwargs: pytest.fail("Stage 1 was invoked"))
    monkeypatch.setattr(adapter, "evaluate_stage3", lambda *args, **kwargs: pytest.fail("Stage 3 was invoked"))
    assert assess_pim(record_from_evidence(bundle["access_requests"][0]), bundle).overall_assessment == "APPROVE_RECOMMENDED"


def test_stage2_ui_supports_change_user_and_paste_modes():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
    app.segmented_control[0].set_value(app.segmented_control[0].options[1]).run(timeout=30)
    assert not list(app.exception)
    assert app.segmented_control[0].value == app.segmented_control[0].options[1]
    pim_radio = next(radio for radio in app.radio if radio.options == ["Search by Change Number", "Search by User ID", "Paste PIM Records"])
    assert any(field.label == "Change number" for field in app.text_input)
    pim_radio.set_value("Search by User ID").run(timeout=30)
    assert not list(app.exception)
    assert any(field.label == "Azure UPN or Entra object ID" for field in app.text_input)
    assert any(select.label == "Access state" for select in app.selectbox)
    pim_radio = next(radio for radio in app.radio if radio.options == ["Search by Change Number", "Search by User ID", "Paste PIM Records"])
    pim_radio.set_value("Paste PIM Records").run(timeout=30)
    assert any(area.label == "PIM records" for area in app.text_area)


def combined(bundle, change_id):
    records = [record_from_evidence(item) for item in find_pim_requests_by_change(bundle, change_id)]
    return records, assess_combined_pim(change_id, records, bundle)


def test_change_lookup_returns_all_three_requests(bundle):
    records = find_pim_requests_by_change(bundle, "CHG-AZ-2021")
    assert [item["pim_request_id"] for item in records] == ["pim-az-0021", "pim-az-0022", "pim-az-0023"]
    assert all(item["reference_source"] == "ticket" for item in records)


def test_paste_multiple_json_pim_records(bundle):
    records = parse_pim_records(json.dumps(bundle["access_requests"][20:23]))
    assert [record.pim_request_id for record in records] == ["pim-az-0021", "pim-az-0022", "pim-az-0023"]


def test_combined_aggregation_for_one_principal(bundle):
    records, result = combined(bundle, "CHG-AZ-2021")
    assert len(records) == 3
    assert result.overall_assessment == "APPROVE_RECOMMENDED"
    assert not result.missing_tasks
    assert list(result.principal_coverage) == ["20000000-0000-0000-0000-000000000001"]
    assert len(result.overlapping_windows) == 3


def test_different_principals_remain_separate_and_authorized(bundle):
    _, result = combined(bundle, "CHG-AZ-2024")
    assert result.overall_assessment == "APPROVE_RECOMMENDED"
    assert len(result.principal_coverage) == 2
    assert all(len(item["supported_by"]) == 1 for item in result.task_coverage)
    assert not result.overlapping_windows


def test_combined_excessive_subscription_scope_and_redundancy(bundle):
    _, result = combined(bundle, "CHG-AZ-2022")
    assert result.overall_assessment == "OVERPRIVILEGED"
    assert result.excessive_permissions
    assert result.scope_duration_concerns
    assert result.potential_redundancies


def test_combined_missing_required_permission(bundle):
    _, result = combined(bundle, "CHG-AZ-2023")
    assert result.overall_assessment == "INSUFFICIENT_ACCESS"
    assert result.missing_tasks[0]["operation"] == "Microsoft.Network/networkSecurityGroups/write"


def test_structured_ticket_wins_and_wrong_justification_is_flagged(bundle):
    raw = find_pim_requests_by_change(bundle, "CHG-AZ-2025")
    assert len(raw) == 1
    record = record_from_evidence(raw[0])
    assert record.change_id == "CHG-AZ-2025"
    assert record.reference_source == "ticket"
    assert record.ambiguous
    result = assess_combined_pim("CHG-AZ-2025", [record], bundle)
    assert result.overall_assessment == "MANUAL_REVIEW_REQUIRED"


def test_multi_request_stage2_remains_independent(bundle, monkeypatch):
    adapter = get_provider("azure")
    monkeypatch.setattr(adapter, "evaluate_stage1", lambda *args, **kwargs: pytest.fail("Stage 1 was invoked"))
    monkeypatch.setattr(adapter, "evaluate_stage3", lambda *args, **kwargs: pytest.fail("Stage 3 was invoked"))
    _, result = combined(bundle, "CHG-AZ-2021")
    assert result.overall_assessment == "APPROVE_RECOMMENDED"


def test_change_centric_ui_retrieves_and_validates_all_requests():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
    app.segmented_control[0].set_value(app.segmented_control[0].options[1]).run(timeout=30)
    next(field for field in app.text_input if field.label == "Change number").set_value("CHG-AZ-2021")
    next(button for button in app.button if button.label == "Retrieve all PIM requests").click().run(timeout=30)
    assert not list(app.exception)
    assert len(app.dataframe[0].value) == 3
    next(button for button in app.button if button.label == "Validate All PIM Requests").click().run(timeout=30)
    assert not list(app.exception)
    assert any(expander.label == "Individual PIM assessments" or "Combined evidence details" in expander.label for expander in app.expander)
