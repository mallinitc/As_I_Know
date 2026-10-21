from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from arca.investigation import InvestigationAgent
from arca.investigation.snowflake_tools import SnowflakeInvestigationTools
from arca.providers import get_provider


@pytest.fixture(scope="module")
def setup():
    bundle = get_provider("snowflake").load_bundle()
    return bundle, SnowflakeInvestigationTools(bundle)


def agent(bundle):
    return InvestigationAgent(SnowflakeInvestigationTools(bundle), model_mode="mock")


def summary_categories(result):
    return result["tool_results"]["summary"]["items"][0]["finding_categories"]


def test_snowflake_agent_registration_and_tool_availability(setup):
    _, tools = setup
    assert tools.provider == "snowflake"
    for name in ("get_change_details", "resolve_snowflake_user", "get_user_activity", "get_change_activity",
                 "get_access_history", "get_role_grants", "detect_change_deviations",
                 "get_unapproved_activity", "build_investigation_timeline", "summarize_investigation"):
        assert callable(getattr(tools, name))


def test_change_investigation_routes_to_snowflake_tools_and_preserves_query_ids(setup):
    bundle, _ = setup
    result = agent(bundle).ask("Was CHG-SF-1007 implemented correctly?", "change",
                               context={"evaluation_time": "2026-11-24T00:00:00Z"})
    assert result["status"] == "complete"
    assert "SF-QRY-001" in result["evidence_refs"]
    assert result["tool_results"]["change_details"]["items"][0]["change_id"] == "CHG-SF-1007"
    trace = [item["tool"] for item in result["tool_results"]["tool_trace"]["items"]]
    assert trace == ["Get Change Details", "Get Change Activity", "Get Access History",
                     "Detect Change Deviations", "Build Investigation Timeline", "Summarize Investigation"]


@pytest.mark.parametrize("identifier", ["rogue.engineer@example.invalid", "SFROGUE01", "SF-USER-014"])
def test_user_email_name_and_id_investigations(identifier, setup):
    bundle, _ = setup
    result = agent(bundle).ask(f"Investigate {identifier} for the last 15 days.", f"user-{identifier}",
                               context={"evaluation_time": "2026-11-24T00:00:00Z"})
    assert result["status"] == "complete"
    assert "POSSIBLE_UNAPPROVED_ACTIVITY" in summary_categories(result)
    assert result["tool_results"]["identity"]["query"]["status"] == "RESOLVED"


@pytest.mark.parametrize("days,expected", [(10, 4), (15, 5)])
def test_historical_user_windows(days, expected, setup):
    bundle, _ = setup
    result = agent(bundle).ask(f"Investigate rogue.engineer@example.invalid for the last {days} days.", f"days-{days}",
                               context={"evaluation_time": "2026-11-24T00:00:00Z"})
    assert result["tool_results"]["user_activity"]["count"] == expected


def test_unknown_and_ambiguous_identity_require_clarification(setup):
    bundle, _ = setup
    missing = agent(bundle).ask("Investigate absent@example.invalid for the last 10 days.", "missing")
    ambiguous = agent(bundle).ask("Investigate shared.operations@example.invalid for the last 10 days.", "ambiguous")
    assert missing["status"] == ambiguous["status"] == "clarification"
    assert "could not be resolved" in missing["response"]
    assert "Multiple exact" in ambiguous["response"]


@pytest.mark.parametrize("scenario_id", [f"SF-INV-{index:02d}" for index in range(1, 16)])
def test_all_demo_questions_execute_actual_tools(scenario_id, setup):
    bundle, _ = setup
    scenario = next(item for item in bundle["investigation_scenarios"] if item["scenario_id"] == scenario_id)
    result = agent(bundle).ask(scenario["investigation_prompt"], scenario_id,
                               context={"evaluation_time": scenario["evaluation_timestamp"]})
    assert result["status"] == "complete"
    assert set(summary_categories(result)) == set(scenario["expected_finding_categories"])
    assert result["tool_results"]["tool_trace"]["count"] >= 3


def test_role_grant_failed_wrong_object_and_missing_execution_findings(setup):
    bundle, _ = setup
    unapproved = agent(bundle).ask("Find unexpected role grants in the last 10 days.", "grants",
                                   context={"evaluation_time": "2026-11-24T00:00:00Z"})
    failed = agent(bundle).ask("Investigate CHG-SF-1008.", "failed",
                               context={"evaluation_time": "2026-11-24T00:00:00Z"})
    missing = agent(bundle).ask("Investigate CHG-SF-1017.", "no-exec",
                                context={"evaluation_time": "2026-11-24T00:00:00Z"})
    assert "SF-QRY-019" in unapproved["evidence_refs"]
    assert {"WRONG_TARGET_OBJECT", "FAILED_EXECUTION"} <= set(summary_categories(failed))
    assert "NO_EXECUTION_EVIDENCE" in summary_categories(missing)


def test_timeline_is_chronological_and_confidence_is_evidence_based(setup):
    bundle, _ = setup
    result = agent(bundle).ask("Investigate CHG-SF-1007.", "timeline",
                               context={"evaluation_time": "2026-11-24T00:00:00Z"})
    timeline = result["tool_results"]["timeline"]["items"]
    assert [row["timestamp"] for row in timeline] == sorted(row["timestamp"] for row in timeline)
    assert result["tool_results"]["summary"]["items"][0]["confidence"] == "STRONG"


def test_agent4_snowflake_unmatched_activity_is_not_called_malicious(setup):
    bundle, _ = setup
    findings = get_provider("snowflake").find_unmatched(bundle["changes"], bundle["query_history"], bundle)
    assert findings
    assert {item["classification"] for item in findings} == {"POSSIBLE_UNAPPROVED_ACTIVITY", "CHANGE_DEVIATION"}
    unmatched = [item for item in findings if item["classification"] == "POSSIBLE_UNAPPROVED_ACTIVITY"]
    assert unmatched and all("not proof" in item["warning"].lower() for item in unmatched)


def test_streamlit_snowflake_agent4_and_agent5_render(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock"); monkeypatch.setenv("ARCA_INVESTIGATION_MODEL", "mock")
    app = AppTest.from_file(Path(__file__).resolve().parents[2] / "app.py").run(timeout=30)
    next(widget for widget in app.selectbox if widget.label == "Environment").set_value("snowflake").run(timeout=30)
    assert [tab.label for tab in app.tabs] == ["Change Lifecycle", "Undocumented Changes", "Ask ARCA"]
    assert any("Snowflake Activity Investigation" in item.value for item in app.markdown)
    assert any(button.label == "Run Investigation" for button in app.button)
    demo = next(widget for widget in app.selectbox if widget.label == "Verified Demo Example" and len(widget.options) == 16)
    demo.set_value("SF-INV-04").run(timeout=30)
    question = next(widget for widget in app.text_input if widget.label == "Investigation question")
    assert "last 10 days" in question.value
    next(button for button in app.button if "Ask ARCA" in button.label and not button.disabled).click().run(timeout=60)
    assert not list(app.exception)
    turn = app.session_state["investigation_turns"][0]
    assert {"identity", "user_activity", "access_history", "deviations", "timeline", "summary", "tool_trace"} <= turn["tool_results"].keys()
