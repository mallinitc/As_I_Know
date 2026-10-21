from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from arca.paths import log_dir, output_dir
from arca.providers import get_provider, provider_capabilities
from arca.snowflake_post_implementation import (
    correlate_query, filter_queries, normalize_query, resolve_identity,
)

UTC = timezone.utc


@pytest.fixture(scope="module")
def evidence():
    adapter = get_provider("snowflake")
    return adapter, adapter.load_bundle()


def categories(result):
    return list(dict.fromkeys(item["category"] for item in result["findings"]))


def run_scenario(adapter, bundle, scenario):
    kwargs = {"evaluation_time": scenario["evaluation_timestamp"], "query_ids": scenario["evidence_query_ids"]}
    if scenario["investigation_mode"] == "change":
        return adapter.evaluate_post_implementation_by_change(scenario["change_id"], bundle, **kwargs)
    return adapter.evaluate_post_implementation_by_user(
        scenario["user_identity"], bundle, days=scenario.get("window_days", 10), **kwargs
    )


def test_mock_audit_dataset_counts_and_relationships(evidence):
    _, bundle = evidence
    assert len(bundle["query_history"]) == 100
    assert len(bundle["access_history"]) == 50
    assert len(bundle["login_history"]) == 20
    assert len(bundle["users"]) >= 15
    assert len(bundle["post_implementation_scenarios"]) == 20
    query_ids = {item["query_id"] for item in bundle["query_history"]}
    assert all(item["query_id"] in query_ids for item in bundle["access_history"])


def test_identity_resolution_by_name_id_and_email(evidence):
    _, bundle = evidence
    for identifier in ("SFSECURITY01", "SF-USER-001", "sfsecurity01@example.invalid"):
        assert resolve_identity(identifier, bundle["users"])["status"] == "RESOLVED"
    assert resolve_identity("missing@example.invalid", bundle["users"])["status"] == "NOT_FOUND"
    assert resolve_identity("shared.operations@example.invalid", bundle["users"])["status"] == "AMBIGUOUS"
    assert resolve_identity("SFSEC", bundle["users"])["status"] == "NOT_FOUND"


def test_query_tag_and_untagged_supporting_correlation(evidence):
    _, bundle = evidence
    access = {item["query_id"]: item for item in bundle["access_history"]}
    tagged = normalize_query(next(item for item in bundle["query_history"] if item["query_id"] == "SF-QRY-001"), access)
    assert correlate_query(tagged, bundle["changes"], bundle["users"])["classification"] == "MATCHED"
    raw = deepcopy(tagged["raw"]); raw["query_tag"] = None
    untagged = normalize_query(raw, access)
    correlated = correlate_query(untagged, bundle["changes"], bundle["users"])
    assert correlated["classification"] == "POSSIBLE_MATCH"
    assert correlated["confidence"] == "SUPPORTING"


@pytest.mark.parametrize("scenario_id", [f"SF-POST-{index:02d}" for index in range(1, 21)])
def test_all_verified_scenarios_use_real_engine(evidence, scenario_id):
    adapter, bundle = evidence
    scenario = next(item for item in bundle["post_implementation_scenarios"] if item["scenario_id"] == scenario_id)
    result = run_scenario(adapter, bundle, scenario)
    assert set(categories(result)) == set(scenario["expected_findings"])
    assert result["investigation_window"]["start"].endswith("Z")
    assert result["investigation_window"]["end"].endswith("Z")


def test_change_lookup_access_join_and_missing_access_evidence(evidence):
    adapter, bundle = evidence
    compliant = adapter.evaluate_post_implementation_by_change(
        "CHG-SF-1007", bundle, evaluation_time="2026-11-24T00:00:00Z", query_ids=["SF-QRY-001"]
    )
    assert compliant["timeline"][0]["access_history_present"] is True
    incomplete = adapter.evaluate_post_implementation_by_change(
        "CHG-SF-1003", bundle, evaluation_time="2026-11-24T00:00:00Z", query_ids=["SF-QRY-017"]
    )
    assert "INSUFFICIENT_AUDIT_EVIDENCE" in categories(incomplete)
    assert incomplete["timeline"][0]["access_history_present"] is False


def test_unapproved_change_is_classified_from_actual_change_state(evidence):
    adapter, bundle = evidence
    modified = deepcopy(bundle)
    event = deepcopy(next(item for item in bundle["query_history"] if item["query_id"] == "SF-QRY-011"))
    event.update({"query_id": "SF-QRY-UNAPPROVED", "query_tag": "ARCA_CHANGE=CHG-SF-1005",
                  "query_type": "ALTER SCHEMA", "target_object": "FINANCE_DB.REPORTING",
                  "user_name": "SFENGINEER05", "role_name": "SECURITYADMIN",
                  "start_time": "2026-11-05T10:15:00Z", "end_time": "2026-11-05T10:15:04Z"})
    modified["query_history"] = [event]
    result = adapter.evaluate_post_implementation_by_change(
        "CHG-SF-1005", modified, evaluation_time="2026-11-06T00:00:00Z", query_ids=[event["query_id"]]
    )
    assert "UNAPPROVED_CHANGE" in categories(result)


@pytest.mark.parametrize("days", [7, 10, 15, 30])
def test_historical_day_filters_are_utc_and_bounded(evidence, days):
    adapter, bundle = evidence
    result = adapter.evaluate_post_implementation_by_user(
        "rogue.engineer@example.invalid", bundle, days=days, evaluation_time="2026-11-24T00:00:00Z"
    )
    start = datetime.fromisoformat(result["investigation_window"]["start"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(result["investigation_window"]["end"].replace("Z", "+00:00"))
    assert (end - start).days == days
    assert all(start <= datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) < end for row in result["timeline"])


def test_custom_range_boundaries_and_timeline_sorting(evidence):
    adapter, bundle = evidence
    result = adapter.evaluate_post_implementation_by_user(
        "rogue.engineer@example.invalid", bundle,
        start="2026-11-20T12:00:00Z", end="2026-11-20T12:20:00Z",
    )
    assert [row["query_id"] for row in result["timeline"]] == ["SF-QRY-018", "SF-QRY-009", "SF-QRY-019"]
    sample = [{"query_id": "a", "start_time": "2026-01-01T00:00:00Z"},
              {"query_id": "b", "start_time": "2026-01-02T00:00:00Z"}]
    assert [item["query_id"] for item in filter_queries(sample, datetime(2026, 1, 1, tzinfo=UTC),
                                                         datetime(2026, 1, 2, tzinfo=UTC))] == ["a"]


def test_user_summary_multiple_changes_and_unknown_identity(evidence):
    adapter, bundle = evidence
    scenario = next(item for item in bundle["post_implementation_scenarios"] if item["scenario_id"] == "SF-POST-20")
    result = run_scenario(adapter, bundle, scenario)
    assert result["summary"]["matched_approved_changes"] == 2
    assert result["summary"]["total_activity_events"] == 2
    unknown = adapter.evaluate_post_implementation_by_user("not-a-user", bundle, evaluation_time="2026-11-24T00:00:00Z")
    assert categories(unknown) == ["IDENTITY_NOT_FOUND"]


def test_provider_and_output_isolation(evidence, tmp_path, monkeypatch):
    adapter, bundle = evidence
    assert log_dir("snowflake") != log_dir("aws") != log_dir("azure")
    assert output_dir("snowflake") != output_dir("aws") != output_dir("azure")
    monkeypatch.setattr("arca.snowflake_post_implementation.output_dir", lambda *_args, **_kwargs: tmp_path)
    result = adapter.evaluate_post_implementation_by_change(
        "CHG-SF-1007", bundle, evaluation_time="2026-11-24T00:00:00Z",
        query_ids=["SF-QRY-001"], persist_output=True,
    )
    assert Path(result["output_path"]).parent == tmp_path
    assert Path(result["output_path"]).is_file()


def test_aws_azure_capabilities_unchanged():
    expected = {"stage1", "stage2", "stage3", "lifecycle", "undocumented", "investigation"}
    assert provider_capabilities("aws") == expected
    assert provider_capabilities("azure") == expected


def test_streamlit_post_implementation_change_and_user_paths(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock"); monkeypatch.setenv("LLM_PROVIDER", "mock")
    app = AppTest.from_file(Path(__file__).resolve().parents[2] / "app.py").run(timeout=30)
    next(widget for widget in app.selectbox if widget.label == "Environment").set_value("snowflake").run(timeout=30)
    assessment = next(widget for widget in app.segmented_control if widget.label == "Assessment")
    assert list(assessment.options) == ["Change & Access Validation", "Post-Implementation Validation"]
    assessment.set_value("Post-Implementation Validation").run(timeout=30)
    demo = next(widget for widget in app.selectbox if widget.label == "Verified Demo Example")
    assert len(demo.options) == 21
    demo.set_value("SF-POST-01").run(timeout=30)
    assert next(widget for widget in app.selectbox if widget.label == "Change Number").value == "CHG-SF-1007"
    next(button for button in app.button if button.label == "Run Post-Implementation Validation").click().run(timeout=30)
    assert not list(app.exception)
    assert app.session_state["snowflake_post_result"]["status"] == "COMPLIANT_EXECUTION"
    demo = next(widget for widget in app.selectbox if widget.label == "Verified Demo Example")
    demo.set_value("SF-POST-17").run(timeout=30)
    assert next(widget for widget in app.text_input if widget.label == "User Identifier").value == "rogue.engineer@example.invalid"
    next(button for button in app.button if button.label == "Investigate User Activity").click().run(timeout=30)
    assert not list(app.exception)
    assert "POSSIBLE_UNAPPROVED_ACTIVITY" in app.session_state["snowflake_post_result"]["summary"]["finding_categories"]
