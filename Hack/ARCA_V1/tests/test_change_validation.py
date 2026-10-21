from pathlib import Path

import pytest

from arca.change_extraction import MockChangeExtractor, extract_existing_change, get_extractor
from arca.change_validation import load_validation_policy, validate_draft
from arca.providers import get_provider
from streamlit.testing.v1 import AppTest


COMPLETE = """Purpose: Rotate the application storage configuration
Business Justification: Maintain the approved security baseline
Environment: production
Implementer: engineer01@example.invalid
Target Resource: {resource}
Implementation Tasks: Update the resource configuration; verify the deployment completes
Start: 2026-10-22T10:00:00Z
End: 2026-10-22T11:00:00Z
Expected Outcome: The approved configuration is active
Post-change Validation: Confirm service health; test application access
Rollback Plan: Restore the previous configuration from the captured baseline
Risk and Impact: Moderate risk with a five minute application interruption
Role Requirements: Contributor
Scope Requirements: Resource scope only
Expected Operations: {operation} @ {resource}
"""
AZURE_RESOURCE = "/subscriptions/00000000-1111-2222-3333-444444444444/resourceGroups/rg-arca-prod/providers/Microsoft.Storage/storageAccounts/starchprod01"
AWS_RESOURCE = "arn:aws:s3:::arca-demo-reports"


def parsed(text=COMPLETE, provider="azure", resource=AZURE_RESOURCE):
    operation = "Microsoft.Storage/storageAccounts/write" if provider == "azure" else "PutBucketPolicy"
    return MockChangeExtractor().extract(text.format(resource=resource, operation=operation), provider)


def test_complete_draft_is_ready_for_submission():
    result = validate_draft(parsed())
    assert result.status == "VALID"
    assert result.ready_for_submission is True
    assert result.completeness["mandatory_supplied"] == result.completeness["mandatory_total"]


@pytest.mark.parametrize("label,field", [("Implementer", "implementer"), ("Target Resource", "target_resources"), ("Rollback Plan", "rollback_plan")])
def test_missing_mandatory_field(label, field):
    text = "\n".join(line for line in COMPLETE.splitlines() if not line.startswith(label + ":"))
    result = validate_draft(parsed(text))
    assert result.status == "INCOMPLETE"
    assert field in result.missing_mandatory
    assert result.ready_for_submission is False


def test_invalid_change_window_requires_timezone():
    result = validate_draft(parsed(COMPLETE.replace("2026-10-22T10:00:00Z", "2026-10-22 10:00")))
    assert result.status == "INCONSISTENT"
    assert any(issue.field == "start" for issue in result.issues)


def test_conflicting_or_reversed_timestamps_are_inconsistent():
    result = validate_draft(parsed(COMPLETE.replace("2026-10-22T11:00:00Z", "2026-10-22T09:00:00Z")))
    assert result.status == "INCONSISTENT"
    assert any(issue.field == "change_window" for issue in result.issues)


def test_equal_timestamps_are_inconsistent():
    result = validate_draft(parsed(COMPLETE.replace("2026-10-22T11:00:00Z", "2026-10-22T10:00:00Z")))
    assert result.status == "INCONSISTENT"
    assert any(issue.field == "change_window" for issue in result.issues)


def test_valid_timestamp_window_has_no_window_finding():
    result = validate_draft(parsed())
    assert not any(issue.field in {"start", "end", "change_window"} for issue in result.issues)


def test_ambiguous_implementation_instructions():
    result = validate_draft(parsed(COMPLETE.replace("Update the resource configuration; verify the deployment completes", "Update as needed")))
    assert result.status == "AMBIGUOUS"
    assert any(issue.field == "implementation_tasks" for issue in result.issues)


@pytest.mark.parametrize("provider", ["azure", "aws"])
def test_existing_change_selection_is_provider_compatible(provider):
    bundle = get_provider(provider).load_bundle()
    extracted = extract_existing_change(bundle["changes"][0], provider)
    assert extracted.change_id == bundle["changes"][0]["change_id"]
    assert extracted.provider == provider
    assert extracted.target_resources


@pytest.mark.parametrize("provider,resource", [("azure", AZURE_RESOURCE), ("aws", AWS_RESOURCE)])
def test_pasted_change_is_provider_compatible(provider, resource):
    result = validate_draft(parsed(provider=provider, resource=resource))
    assert result.status == "VALID"
    assert result.extracted_change.provider == provider


def test_stage1_is_independent_of_pim_and_execution_evidence():
    result = validate_draft(parsed())
    assert result.status == "VALID"
    assert "access_request" not in result.model_dump()
    assert "events" not in result.model_dump()


def test_mock_is_default_and_does_not_construct_bedrock(monkeypatch):
    monkeypatch.delenv("ARCA_CHANGE_EXTRACTOR", raising=False)
    assert isinstance(get_extractor(), MockChangeExtractor)


def test_policy_is_external_and_configurable():
    policy = load_validation_policy()
    assert "rollback_plan" in policy["mandatory_fields"]
    assert "role_requirements" in policy["recommended_fields"]
    assert Path("config/change_validation_policy.json").exists()


def test_dashboard_exposes_all_independent_paths():
    source = Path("app.py").read_text(encoding="utf-8")
    for label in ("Stage 1 — Validate Change", "Stage 2 — Validate Privileges", "Stage 3 — Verify Execution", "Full Lifecycle Assessment"):
        assert label in source
    assert "Paste Change Details" in source


@pytest.mark.parametrize("mode", ["Stage 1 — Validate Change", "Stage 2 — Validate Privileges", "Stage 3 — Verify Execution", "Full Lifecycle Assessment"])
def test_each_lifecycle_path_renders_without_error(mode):
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
    app.segmented_control[0].set_value(mode).run(timeout=30)
    assert not list(app.exception)
