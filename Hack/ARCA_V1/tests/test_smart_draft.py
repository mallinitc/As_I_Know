from copy import deepcopy
from pathlib import Path

from arca.change_extraction import MockChangeExtractor, extract_existing_change
from arca.change_validation import validate_draft
from arca.providers import get_provider
from arca.change_models import ValidationIssue
from arca.smart_draft import (DraftLanguageRefinement, clear_refinement_cache, draft_field_findings,
                              draft_to_extracted, improve_draft, improve_draft_with_status, servicenow_text)
from streamlit.testing.v1 import AppTest


def extract(text):
    return MockChangeExtractor().extract(text, "azure")


def test_missing_resource_and_timestamps_remain_empty():
    draft = improve_draft(extract("Purpose: Update approved network controls\nImplementer: operator@example.invalid"))
    assert draft.resource_name_or_id == ""
    assert draft.resource_group == ""
    assert draft.subscription == ""
    assert draft.change_start == ""
    assert draft.change_end == ""
    assert draft.timezone == ""


def test_explicit_values_are_preserved_exactly():
    resource = "/subscriptions/sub-001/resourceGroups/RG-Exact/providers/Microsoft.Storage/storageAccounts/StoreExact01"
    text = f"""Purpose: Permit 192.0.2.44 during the approved deployment
Implementer: Engineer.Exact@example.invalid
Target Resource: {resource}
Start: 2026-11-01T09:15:00+05:30
End: 2026-11-01T10:45:00+05:30
Role Requirements: Storage Blob Data Contributor
Scope Requirements: {resource}"""
    draft = improve_draft(extract(text))
    assert draft.change_title == "Permit 192.0.2.44 during the approved deployment"
    assert draft.resource_name_or_id == resource
    assert draft.implementer == "Engineer.Exact@example.invalid"
    assert draft.change_start == "2026-11-01T09:15:00+05:30"
    assert draft.timezone == "+05:30"
    assert draft.required_role == "Storage Blob Data Contributor"


def test_editable_corrections_are_retained_in_typed_draft():
    draft = improve_draft(extract("Purpose: Update storage"))
    edited = draft.model_copy(update={"implementer": "corrected@example.invalid", "rollback_plan": "Restore snapshot snap-001"})
    assert edited.implementer == "corrected@example.invalid"
    assert edited.rollback_plan == "Restore snapshot snap-001"
    assert draft.implementer == ""


def test_revalidation_detects_completed_mandatory_fields():
    draft = improve_draft(extract("Purpose: Update storage"))
    resource = "/subscriptions/sub-001/resourceGroups/rg-prod/providers/Microsoft.Storage/storageAccounts/store01"
    edited = draft.model_copy(update={
        "business_justification": "Apply the approved security baseline",
        "environment": "production", "resource_name_or_id": resource,
        "implementer": "engineer@example.invalid", "change_start": "2026-11-01T09:00:00Z",
        "change_end": "2026-11-01T10:00:00Z", "implementation_steps": ["Update the storage firewall"],
        "validation_plan": ["Confirm application access"], "rollback_plan": "Restore the previous firewall rules",
        "expected_outcome": "Only approved networks can access storage",
        "risk_and_impact": "Low risk; brief control-plane update",
    })
    result = validate_draft(draft_to_extracted(edited))
    assert result.status == "VALID"
    assert result.ready_for_submission is True


def test_contradictory_source_values_remain_flagged_after_improvement():
    extracted = extract("""Purpose: Update storage
Start: 2026-11-01T09:00:00Z
Start: 2026-11-01T10:00:00Z""")
    result = validate_draft(draft_to_extracted(improve_draft(extracted)))
    assert result.status == "INCONSISTENT"
    assert any("Conflicting values" in issue.reason for issue in result.issues)


def test_copy_output_contains_corrected_information():
    draft = improve_draft(extract("Purpose: Update storage"))
    edited = draft.model_copy(update={"implementer": "corrected@example.invalid", "rollback_plan": "Restore snapshot snap-001", "resource_name_or_id": "store-corrected"})
    output = servicenow_text(edited)
    assert "corrected@example.invalid" in output
    assert "Restore snapshot snap-001" in output
    assert "store-corrected" in output


def test_improvement_does_not_modify_change_records():
    adapter = get_provider("azure")
    bundle = adapter.load_bundle()
    before = deepcopy(bundle["changes"])
    improve_draft(extract_existing_change(bundle["changes"][0], "azure"))
    assert bundle["changes"] == before


def test_smart_draft_editor_retains_correction_across_rerun():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
    next(button for button in app.button if button.label == "Validate change").click().run(timeout=30)
    next(button for button in app.button if button.label == "Improve Draft").click().run(timeout=30)
    implementer = next(field for field in app.text_input if field.label == "Implementer")
    implementer.set_value("corrected.engineer@example.invalid")
    next(button for button in app.button if button.label == "Revalidate Draft").click().run(timeout=30)
    assert not list(app.exception)
    assert next(field for field in app.text_input if field.label == "Implementer").value == "corrected.engineer@example.invalid"


def _complete_for_findings(end="2026-10-22T11:00:00Z", resource="store01"):
    return extract(f"""Purpose: Update storage
Business Justification: Maintain security controls
Environment: production
Implementer: engineer@example.invalid
Target Resource: {resource}
Implementation Tasks: Update the storage configuration
Start: 2026-10-22T10:00:00Z
End: {end}
Expected Outcome: Configuration is updated
Post-change Validation: Confirm service health
Rollback Plan: Restore the prior configuration
Risk and Impact: Low risk""")


def test_reversed_window_maps_exact_error_to_end_field():
    result = validate_draft(_complete_for_findings("2026-10-22T09:00:00Z"))
    findings = draft_field_findings(result)
    assert findings["change_end"] == [{"message": "End time must be later than start time.", "level": "error", "field": "change_window"}]


def test_missing_mandatory_and_ambiguous_resource_map_to_editable_fields():
    missing = draft_field_findings(validate_draft(extract("Purpose: Update storage")))
    assert "implementer" in missing and "rollback_plan" in missing and "business_justification" in missing
    ambiguous = draft_field_findings(validate_draft(_complete_for_findings(resource="as needed")))
    assert ambiguous["resource_name_or_id"][0]["level"] == "review"


def test_multiple_findings_on_one_field_are_unique():
    result = validate_draft(_complete_for_findings())
    issue = ValidationIssue(field="role_requirements", reason="Role is unsupported.", severity="REVIEW",
                            category="MANUAL_REVIEW_REQUIRED", recommended_correction="Choose a catalog role.")
    issue2 = issue.model_copy(update={"reason": "Role scope is ambiguous."})
    updated = result.model_copy(update={"issues": [issue, issue, issue2]})
    messages = [item["message"] for item in draft_field_findings(updated)["required_role"]]
    assert messages == ["Role is unsupported.", "Role scope is ambiguous."]


def test_correcting_window_removes_field_error():
    draft = improve_draft(_complete_for_findings("2026-10-22T09:00:00Z"), mode="mock")
    before = draft_field_findings(validate_draft(draft_to_extracted(draft)))
    corrected = draft.model_copy(update={"change_end": "2026-10-22T11:00:00Z"})
    after = draft_field_findings(validate_draft(draft_to_extracted(corrected)))
    assert "change_end" in before
    assert "change_end" not in after


class _FakeRefiner:
    model = "gpt-5-mini"
    def __init__(self, error=None): self.calls, self.error = 0, error
    def parse(self, instructions, content, schema):
        self.calls += 1
        if self.error: raise self.error
        return DraftLanguageRefinement(change_title="Clear storage update")


def test_repeated_improve_uses_cache(monkeypatch):
    clear_refinement_cache(); fake = _FakeRefiner()
    monkeypatch.setattr("arca.smart_draft.get_llm_provider", lambda selected: fake)
    first = improve_draft_with_status(_complete_for_findings(), mode="openai")
    second = improve_draft_with_status(_complete_for_findings(), mode="openai")
    assert fake.calls == 1
    assert first.llm_used and not first.cache_hit
    assert second.llm_used and second.cache_hit


def test_revalidation_does_not_invoke_openai(monkeypatch):
    clear_refinement_cache(); fake = _FakeRefiner()
    monkeypatch.setattr("arca.smart_draft.get_llm_provider", lambda selected: fake)
    outcome = improve_draft_with_status(_complete_for_findings(), mode="openai")
    corrected = outcome.draft.model_copy(update={"change_end": "2026-10-22T12:00:00Z"})
    validate_draft(draft_to_extracted(corrected))
    assert fake.calls == 1


def test_llm_timeout_preserves_deterministic_editable_draft(monkeypatch):
    clear_refinement_cache(); fake = _FakeRefiner(TimeoutError("offline timeout"))
    monkeypatch.setattr("arca.smart_draft.get_llm_provider", lambda selected: fake)
    source = _complete_for_findings()
    outcome = improve_draft_with_status(source, mode="openai")
    assert outcome.status == "fallback" and not outcome.llm_used
    assert outcome.draft.change_start == source.start
    assert outcome.draft.resource_name_or_id == source.target_resources[0]
