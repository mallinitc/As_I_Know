from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from arca.investigation import InvestigationAgent, InvestigationTools
from arca.investigation.ui import choose_question
from arca.providers import get_provider
from arca.time_filters import TIME_RANGES, evidence_reference_time, filter_evidence_window

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.mark.parametrize("provider_name", ["azure", "aws"])
@pytest.mark.parametrize("selection", list(TIME_RANGES))
def test_dashboard_and_agent_return_identical_unmatched_ids(provider_name, selection):
    adapter = get_provider(provider_name)
    bundle = adapter.load_bundle()
    reference = evidence_reference_time(provider_name, bundle["events"], "demonstration")
    window = filter_evidence_window(provider_name, bundle["changes"], bundle["events"], selection,
                                    mode="demonstration", reference_time=reference)
    dashboard = adapter.find_unmatched(window["changes"], window["events"], bundle)
    tools = InvestigationTools(bundle=bundle, provider=provider_name, evidence_mode="demonstration")
    agent_result = tools.find_undocumented_changes(
        start=window["start"].isoformat().replace("+00:00", "Z"),
        end=window["end"].isoformat().replace("+00:00", "Z"),
        environment="production",
    )
    assert {item["event_id"] for item in dashboard} == {item["event_id"] for item in agent_result["items"]}


def test_reference_time_modes_use_evidence_for_demo_and_clock_for_live():
    bundle = get_provider("azure").load_bundle()
    wall_clock = datetime(2030, 1, 1, tzinfo=timezone.utc)
    demonstration = evidence_reference_time("azure", bundle["events"], "demonstration", now=wall_clock)
    live = evidence_reference_time("azure", bundle["events"], "live", now=wall_clock)
    assert demonstration.isoformat().replace("+00:00", "Z") == InvestigationTools(bundle, "azure").evidence_as_of
    assert live == wall_clock
    assert demonstration != live


def test_custom_suggestion_and_followup_choose_one_submission():
    assert choose_question(main_submitted=True, main_text="  custom question  ", suggested_text="shortcut") == "custom question"
    assert choose_question(suggested_text="shortcut") == "shortcut"
    assert choose_question(followup_submitted=True, followup_text="  follow up ") == "follow up"
    assert choose_question(main_submitted=True, main_text="", suggested_text=None) is None


def test_streamlit_custom_question_shortcut_and_followup_share_session(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock")
    monkeypatch.setenv("ARCA_INVESTIGATION_MODEL", "mock")
    app = AppTest.from_file(APP).run(timeout=30)
    labels = [tab.label for tab in app.tabs]
    assert "Ask ARCA" in labels
    assert any(list(radio.options) == ["ARCA", "Metrics"] for radio in app.radio)
    app.text_input[0].input("Show undocumented production changes in the last 24 hours.")
    next(button for button in app.button if button.label.endswith("Ask ARCA")).click().run(timeout=30)
    assert len(app.chat_message) == 2
    assert len(app.session_state["investigation_turns"]) == 1
    app.text_input[1].input("Who performed those changes?")
    next(button for button in app.button if button.label == "Send follow-up").click().run(timeout=30)
    assert len(app.session_state["investigation_turns"]) == 2
    assert app.session_state["investigation_turns"][1]["query"] == "Who performed those changes?"


def test_streamlit_suggested_question_uses_agent_session(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock")
    monkeypatch.setenv("ARCA_INVESTIGATION_MODEL", "mock")
    app = AppTest.from_file(APP).run(timeout=30)
    next(button for button in app.button if button.label == "Find undocumented changes").click().run(timeout=30)
    assert len(app.session_state["investigation_turns"]) == 1
    assert app.session_state["investigation_turns"][0]["query"] == "Show undocumented production changes in the last 24 hours."
    assert len(app.chat_message) == 2


def test_missing_resource_still_requests_clarification():
    result = InvestigationAgent(model_mode="mock").ask("What changed on resource-not-in-evidence?", "missing-consistency")
    assert result["status"] == "clarification"
    assert "could not uniquely identify" in result["response"]
