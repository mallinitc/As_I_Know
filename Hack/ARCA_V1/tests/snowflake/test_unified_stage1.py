from datetime import datetime, timezone

from arca.providers import get_provider, provider_capabilities
from arca.time_filters import parse_utc
from arca.snowflake_stage2 import (
    UNIFIED_RESULT_SCHEMA_VERSION,
    normalize_unified_result,
    validate_unified_result_contract,
)
from arca.providers.snowflake import load_demo_scenarios
import pytest


def test_all_dedicated_demo_scenarios_match_real_unified_evaluator():
    adapter = get_provider("snowflake")
    bundle = adapter.load_bundle()
    changes = {item["change_id"]: item for item in bundle["changes"]}
    assert len(bundle["demo_scenarios"]) == 25
    for scenario in bundle["demo_scenarios"]:
        result = adapter.evaluate_stage1(
            changes[scenario["change_id"]],
            {**bundle, "evaluation_time": scenario["evaluation_timestamp"]},
        )
        actual = {
            "change_quality": result["change_quality"]["status"],
            "window": result["window_assessment"]["status"],
            "access": result["role_assessment"]["status"],
            "overall": result["status"],
        }
        assert actual == scenario["expected_check_outcomes"], scenario["scenario_id"]


def test_manual_unified_validation_uses_current_utc():
    adapter = get_provider("snowflake")
    bundle = adapter.load_bundle()
    before = datetime.now(timezone.utc)
    result = adapter.evaluate_stage1(bundle["changes"][0], bundle)
    after = datetime.now(timezone.utc)
    evaluated = parse_utc(result["window_assessment"]["evaluation_timestamp"])
    assert before <= evaluated <= after


def test_unified_capability_and_mock_relationships():
    bundle = get_provider("snowflake").load_bundle()
    assert provider_capabilities("snowflake") == {"stage1", "post_implementation", "undocumented", "investigation"}
    assert len(bundle["changes"]) == 23
    assert len(bundle["roles"]) == 10
    assert len(bundle["role_grants"]) == 8
    assert len(bundle["object_grants"]) == 23
    assert len(bundle["resources"]) == 12
    object_names = {item["object_name"] for item in bundle["resources"]}
    assert "REPORTING_WH" in object_names
    assert "FINANCE_DB.REPORTING.TRANSACTIONS" in object_names


@pytest.mark.parametrize("scenario_id", [
    "SF-UNIFIED-01", "SF-UNIFIED-07", "SF-UNIFIED-09", "SF-UNIFIED-02",
    "SF-UNIFIED-03", "SF-UNIFIED-05", "SF-UNIFIED-23", "SF-UNIFIED-10",
])
def test_required_result_contract_for_complete_and_partial_validation(scenario_id):
    adapter = get_provider("snowflake"); bundle = adapter.load_bundle()
    scenario = next(item for item in bundle["demo_scenarios"] if item["scenario_id"] == scenario_id)
    change = next(item for item in bundle["changes"] if item["change_id"] == scenario["change_id"])
    result = adapter.evaluate_stage1(change, {**bundle, "evaluation_time": scenario["evaluation_timestamp"]})
    assert {"status", "overall_status", "schema_version", "change_quality", "window_assessment", "role_assessment"} <= result.keys()
    assert result["status"] == result["overall_status"]
    assert result["schema_version"] == UNIFIED_RESULT_SCHEMA_VERSION
    for name in ("change_quality", "window_assessment", "role_assessment"):
        assert result[name].get("status")
        assert isinstance(result[name]["evidence"], list)
        assert isinstance(result[name]["findings"], list)


def test_chg_sf_1007_real_result_normalizes_to_renderer_contract():
    adapter = get_provider("snowflake")
    bundle = adapter.load_bundle()
    scenario = next(item for item in bundle["demo_scenarios"] if item["scenario_id"] == "SF-UNIFIED-01")
    change = next(item for item in bundle["changes"] if item["change_id"] == "CHG-SF-1007")
    result = adapter.evaluate_stage1(change, {**bundle, "evaluation_time": scenario["evaluation_timestamp"]})
    normalized = normalize_unified_result(result)
    assert normalized["overall_status"] == "PASS"
    assert all(name in normalized for name in ("change_quality", "window_assessment", "role_assessment"))


def test_incompatible_unified_result_contract_fails_explicitly():
    with pytest.raises(ValueError, match="missing mandatory sections"):
        validate_unified_result_contract({"status": "PASS"})


def test_missing_scenario_file_has_actionable_error(tmp_path):
    missing = tmp_path / "demo_scenarios.json"
    with pytest.raises(FileNotFoundError, match="Restore data/snowflake/demo_scenarios.json"):
        load_demo_scenarios(missing)
