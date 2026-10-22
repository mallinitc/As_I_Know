from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.stage1 import deterministic_draft, draft_to_extracted, extract_change, scenarios, servicenow_text, stage1_demo_text, validate_draft


def test_all_v1_azure_scenarios_keep_exact_outcomes():
    expected = {"S1-VALID": "VALID", "S1-MISSING-IMPLEMENTER": "INCOMPLETE", "S1-MISSING-RESOURCE": "INCOMPLETE", "S1-REVERSED-WINDOW": "INCONSISTENT", "S1-AMBIGUOUS-TASK": "AMBIGUOUS"}
    items = scenarios("azure")
    assert len(items) == 5
    assert {item["scenario_id"]: validate_draft(extract_change(item["text"], "azure")).status for item in items} == expected


def test_demo_values_and_explicit_technical_facts_are_preserved():
    change = extract_change(stage1_demo_text("complete"), "azure")
    assert change.implementer == "engineer01@example.invalid"
    assert change.start == "2026-10-22T10:00:00Z"
    assert change.target_resources[0].endswith("/storageAccounts/starchprod01")


def test_manual_overrides_match_v1_truthy_behavior():
    change = extract_change("Purpose: Test", "aws", {"environment": "production", "implementer": "ops@example.invalid", "target_resources": "arn:aws:s3:::arca-demo"})
    assert change.provider == "aws"
    assert change.target_resources == ["arn:aws:s3:::arca-demo"]


def test_revalidation_and_copy_preserve_edits_without_mutating_source():
    source = extract_change(stage1_demo_text("missing_implementer"), "azure")
    draft = deterministic_draft(source)
    edited = draft.model_copy(update={"implementer": "engineer01@example.invalid"})
    assert validate_draft(draft_to_extracted(edited)).status == "VALID"
    assert "engineer01@example.invalid" in servicenow_text(edited)
    assert source.implementer == ""


def test_stage1_api_contract_and_unknown_provider():
    client = TestClient(create_app())
    response = client.get("/api/v1/agents/change-quality/stage1/demo-scenarios?provider=azure")
    assert response.status_code == 200 and response.json()["count"] == 5
    validation = client.post("/api/v1/agents/change-quality/stage1/validate-draft", json={"provider": "azure", "text": stage1_demo_text("reversed_window"), "overrides": {}})
    assert validation.status_code == 200 and validation.json()["status"] == "INCONSISTENT"
    assert client.get("/api/v1/agents/change-quality/stage1/demo-scenarios?provider=snowflake").status_code == 422


def test_invalid_equal_window_and_missing_fields():
    equal = stage1_demo_text("complete").replace("End: 2026-10-22T11:00:00Z", "End: 2026-10-22T10:00:00Z")
    result = validate_draft(extract_change(equal, "azure"))
    assert result.status == "INCONSISTENT"
    assert "change_window" in [item.field for item in result.issues]
    missing = validate_draft(extract_change("Purpose: Test", "azure"))
    assert missing.status == "INCOMPLETE" and "implementer" in missing.missing_mandatory
