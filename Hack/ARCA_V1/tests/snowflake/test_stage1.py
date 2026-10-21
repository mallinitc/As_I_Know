from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from arca.paths import data_dir
from arca.providers import get_provider, provider_capabilities
from arca.providers.snowflake import evaluate_change_quality
from arca.workflow import build


EXPECTED = {
    "CHG-SF-1001": "VALID",
    "CHG-SF-1002": "NEEDS_INFO",
    "CHG-SF-1003": "NEEDS_INFO",
    "CHG-SF-1004": "NEEDS_INFO",
    "CHG-SF-1005": "NEEDS_INFO",
    "CHG-SF-1006": "NEEDS_INFO",
    "CHG-SF-1007": "VALID",
    "CHG-SF-1008": "VALID",
    "CHG-SF-1009": "VALID",
    "CHG-SF-1010": "NEEDS_INFO",
    "CHG-SF-1011": "NEEDS_INFO",
    "CHG-SF-1012": "VALID",
    "CHG-SF-1013": "VALID",
    "CHG-SF-1014": "VALID",
    "CHG-SF-1015": "NEEDS_INFO",
    "CHG-SF-1016": "VALID",
    "CHG-SF-1017": "VALID",
    "CHG-SF-1018": "VALID",
    "CHG-SF-1019": "VALID",
    "CHG-SF-1020": "VALID",
    "CHG-SF-1021": "VALID",
    "CHG-SF-1022": "VALID",
    "CHG-SF-1023": "VALID",
}


@pytest.fixture(scope="module")
def snowflake_bundle():
    return get_provider("snowflake").load_bundle()


def test_snowflake_dataset_isolated_complete_and_unique(snowflake_bundle):
    changes = snowflake_bundle["changes"]
    assert data_dir("snowflake") != data_dir("aws") != data_dir("azure")
    assert (data_dir("snowflake") / "changes.json").is_file()
    assert len(changes) == 23
    assert len({item["change_id"] for item in changes}) == 23
    assert {item["change_id"] for item in changes} == set(EXPECTED)
    assert all(item["provider"] == "snowflake" for item in changes)
    existing_ids = {item["change_id"] for provider in ("aws", "azure")
                    for item in get_provider(provider).load_bundle()["changes"]}
    assert not ({item["change_id"] for item in changes} & existing_ids)


@pytest.mark.parametrize("change_id,expected_status", EXPECTED.items())
def test_all_snowflake_stage1_scenarios(change_id, expected_status, snowflake_bundle):
    adapter = get_provider("snowflake")
    change = next(item for item in snowflake_bundle["changes"] if item["change_id"] == change_id)
    result = evaluate_change_quality(change)
    assert result["status"] == expected_status


def test_invalid_scenarios_report_focused_reasons(snowflake_bundle):
    adapter = get_provider("snowflake")
    by_id = {item["change_id"]: item for item in snowflake_bundle["changes"]}
    assert "description" in evaluate_change_quality(by_id["CHG-SF-1002"])["missing"]
    assert "valid_change_window" in evaluate_change_quality(by_id["CHG-SF-1003"])["missing"]
    assert "implementer" in evaluate_change_quality(by_id["CHG-SF-1004"])["missing"]
    assert "approved_state" in evaluate_change_quality(by_id["CHG-SF-1005"])["missing"]
    assert "expected" in evaluate_change_quality(by_id["CHG-SF-1006"])["missing"]
    assert "valid_start_timestamp" in evaluate_change_quality(by_id["CHG-SF-1010"])["missing"]
    assert "expected[0].resource_id" in evaluate_change_quality(by_id["CHG-SF-1011"])["missing"]


def test_high_risk_does_not_fail_and_warehouse_is_account_level(snowflake_bundle):
    adapter = get_provider("snowflake")
    by_id = {item["change_id"]: item for item in snowflake_bundle["changes"]}
    assert evaluate_change_quality(by_id["CHG-SF-1013"])["status"] == "VALID"
    warehouse = by_id["CHG-SF-1014"]
    assert warehouse["expected"][0]["resource_id"] == "REPORTING_WH"
    assert warehouse["snowflake_context"]["database"] is None


def test_normalization_preserves_snowflake_context(snowflake_bundle):
    adapter = get_provider("snowflake")
    source = snowflake_bundle["changes"][0]
    normalized = adapter.normalize_change(source)
    assert normalized["change_id"] == source["change_id"]
    assert normalized["expected"] == source["expected"]
    assert normalized["raw"]["snowflake_context"] == source["snowflake_context"]


def test_workflow_runs_only_snowflake_supported_stages(monkeypatch, snowflake_bundle):
    monkeypatch.setenv("ARCA_MODE", "mock")
    scenario = snowflake_bundle["demo_scenarios"][0]
    change = next(x for x in snowflake_bundle["changes"] if x["change_id"] == scenario["change_id"])
    result = build().invoke({"provider": "snowflake", "change": change,
                             "context": {**snowflake_bundle, "evaluation_time": scenario["evaluation_timestamp"]}})
    assert result["stage1"]["status"] == "PASS"
    assert "stage2" not in result
    assert "stage3" not in result
    assert "investigation" not in result
    assert provider_capabilities("snowflake") == {"stage1", "post_implementation", "undocumented", "investigation"}
    explicit = build("snowflake").invoke({"change": change,
                                           "context": {**snowflake_bundle, "evaluation_time": scenario["evaluation_timestamp"]}})
    assert "stage2" not in explicit and "stage3" not in explicit


def test_snowflake_ui_exposes_only_supported_stages(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    app = AppTest.from_file(Path(__file__).resolve().parents[2] / "app.py").run(timeout=30)
    environment = next(widget for widget in app.selectbox if widget.label == "Environment")
    environment.set_value("snowflake").run(timeout=30)
    assert not list(app.exception)
    assessment = next(widget for widget in app.segmented_control if widget.label == "Assessment")
    assert list(assessment.options) == ["Change & Access Validation", "Post-Implementation Validation"]
    labels = [tab.label for tab in app.tabs]
    assert labels == ["Change Lifecycle", "Undocumented Changes", "Ask ARCA"]
    assert not any("Stage 2" in text.value or "Stage 3" in text.value for text in app.markdown)


def test_snowflake_ui_runs_selected_change_validation(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    app = AppTest.from_file(Path(__file__).resolve().parents[2] / "app.py").run(timeout=30)
    next(widget for widget in app.selectbox if widget.label == "Environment").set_value("snowflake").run(timeout=30)
    demo = next(widget for widget in app.selectbox if widget.label == "Verified Demo Example")
    assert len(demo.options) == 26
    assert demo.options[0] == "Manual Entry"
    assert any(label.startswith("01") and "Appropriate Role" in label for label in demo.options)
    demo.set_value("SF-UNIFIED-01").run(timeout=30)
    next(button for button in app.button if button.label == "Run Validation").click().run(timeout=30)
    assert not list(app.exception)
    assert any("Overall Result" in item.value for item in app.markdown)


def test_stage3_fails_closed_if_called(snowflake_bundle):
    adapter = get_provider("snowflake")
    with pytest.raises(NotImplementedError): adapter.evaluate_stage3({}, [])
