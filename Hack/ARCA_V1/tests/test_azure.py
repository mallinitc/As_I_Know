from datetime import datetime

from arca.providers import azure
from arca.workflow import build


def bundle():
    return azure.load_bundle()


def by_scenario(data, name):
    return next(item for item in data["changes"] if item["scenario"] == name)


def access(data, change):
    return azure.access_for_change(data, change["change_id"])


def test_azure_record_counts_and_relationships():
    data = bundle()
    assert len(data["changes"]) == 25
    assert len(data["access_requests"]) == 29
    assert len(data["rbac_assignments"]) == 29
    assert len(data["role_definitions"]) >= 8
    assert len(data["resources"]) == 30
    assert len(data["events"]) == 100
    change_ids = {x["change_id"] for x in data["changes"]}
    role_ids = {x["role_definition_id"] for x in data["role_definitions"]}
    request_ids = {x["pim_request_id"] for x in data["access_requests"]}
    resource_ids = {x["resource_id"] for x in data["resources"]}
    assert all(x["change_id"] in change_ids and x["role_definition_id"] in role_ids for x in data["access_requests"])
    assert all(x["pim_request_id"] in request_ids and x["role_definition_id"] in role_ids for x in data["rbac_assignments"])
    assert all(any(expected["resource_id"].startswith(resource_id) for resource_id in resource_ids)
               for change in data["changes"] for expected in change["expected"])


def test_all_azure_timestamps_are_utc_and_ids_are_preserved():
    data = bundle()
    timestamps = [x["start"] for x in data["changes"]] + [x["end"] for x in data["changes"]]
    timestamps += [x["event_timestamp"] for x in data["events"]]
    assert all(value.endswith("Z") and datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset().total_seconds() == 0 for value in timestamps)
    raw = data["events"][0]
    normalized = azure.normalize_activity(raw)
    assert normalized["evidence_id"] == raw["event_data_id"]
    assert normalized["timestamp"] == raw["event_timestamp"]
    assert normalized["raw"] is raw


def test_valid_and_incomplete_changes():
    data = bundle()
    valid = by_scenario(data, "VALID_APPROVED_CHANGE")
    incomplete = by_scenario(data, "INCOMPLETE_CHANGE_REQUEST")
    assert azure.evaluate_stage1(valid, data)["status"] == "VALID"
    result = azure.evaluate_stage1(incomplete, data)
    assert result["status"] == "NEEDS_INFO"
    assert "description" in result["missing"]


def test_azure_permission_scenarios_are_provider_specific():
    data = bundle()
    cases = {
        "OVERPRIVILEGED_PIM_REQUEST": ("OVERPRIVILEGED", "ROLE_BROADER_THAN_REQUIRED"),
        "INSUFFICIENT_RBAC_PERMISSIONS": ("INSUFFICIENT", None),
        "EXCESSIVE_SUBSCRIPTION_SCOPE": ("OVERPRIVILEGED", "EXCESSIVE_SUBSCRIPTION_SCOPE"),
        "PIM_EXTENDS_BEYOND_CHANGE_WINDOW": ("OVERPRIVILEGED", "PIM_EXTENDS_BEYOND_CHANGE_WINDOW"),
    }
    for scenario, (status, finding) in cases.items():
        change = by_scenario(data, scenario)
        result = azure.evaluate_stage2(change, access(data, change), data)
        assert result["status"] == status
        if finding:
            assert finding in result["findings"]
        assert "Azure RBAC/PIM" in result["warning"]


def test_activity_deviation_scenarios():
    data = bundle()
    expected_reason = {
        "UNEXPECTED_RESOURCE_MODIFICATION": "UNEXPECTED_OPERATION_OR_RESOURCE",
        "ACTIVITY_OUTSIDE_CHANGE_WINDOW": "OUTSIDE_WINDOW",
        "UNEXPECTED_ENGINEER": "ACTOR_MISMATCH",
    }
    for scenario, reason in expected_reason.items():
        change = by_scenario(data, scenario)
        result = azure.evaluate_stage3(change, data["events"], data)
        assert result["status"] == "DEVIATION_DETECTED"
        assert any(reason in event["reasons"] for event in result["events"])


def test_storage_access_loss_signals_are_cautious_and_evidence_backed():
    data = bundle()
    cases = {
        "STORAGE_ACCESS_LOSS_ROLE_REMOVAL": "STORAGE_ACCESS_LOSS_POSSIBLY_RELATED_TO_ROLE_ASSIGNMENT_REMOVAL",
        "STORAGE_ACCESS_LOSS_FIREWALL": "STORAGE_ACCESS_LOSS_POSSIBLY_RELATED_TO_FIREWALL_MODIFICATION",
    }
    for scenario, signal in cases.items():
        change = by_scenario(data, scenario)
        result = azure.evaluate_stage3(change, data["events"], data)
        assert signal in result["impact_signals"]
        assert "not proof" in result["warning"]


def test_unmatched_activity_is_not_labeled_unauthorized():
    data = bundle()
    results = azure.find_unmatched(data["changes"], data["events"], data)
    undocumented_ids = {x["event_data_id"] for x in data["events"] if x["properties"].get("synthetic_scenario") == "UNDOCUMENTED_PRODUCTION_MODIFICATION"}
    result_ids = {x["event_id"] for x in results}
    assert undocumented_ids <= result_ids
    assert all(x["classification"] == "UNMATCHED_IN_AVAILABLE_RECORDS" for x in results)
    assert all("does not establish" in x["warning"] for x in results)


def test_azure_workflow_end_to_end_in_mock_mode(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock")
    data = bundle()
    change = by_scenario(data, "UNEXPECTED_RESOURCE_MODIFICATION")
    result = build("azure").invoke({"provider": "azure", "change": change, "access_request": access(data, change),
                                    "events": data["events"], "context": data})
    assert result["investigation"]["status"] == "REVIEW_REQUIRED"
    assert result["stage3"]["status"] == "DEVIATION_DETECTED"
    assert result["narrative"].startswith("MOCK NARRATIVE")
