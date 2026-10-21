from pathlib import Path

import pytest

from arca.change_extraction import get_extractor
from arca.change_validation import validate_draft
from arca.demo_catalog import demo_scenarios, load_demo_catalog, pim_records_json, stage1_demo_text
from arca.investigation import InvestigationAgent, InvestigationTools
from arca.pim_validation import assess_combined_pim, parse_pim_records, record_from_evidence
from arca.providers import get_provider
from arca.time_filters import evidence_reference_time, filter_evidence_window, undocumented_window_status
from arca.workflow import build


CATALOG = load_demo_catalog()


def test_catalog_has_unique_complete_records_and_feature_coverage():
    assert len(CATALOG) == 56
    assert len({item["scenario_id"] for item in CATALOG}) == len(CATALOG)
    for feature in ("stage1", "stage2_change", "stage2_user", "stage2_paste", "stage3",
                    "automated_investigation", "undocumented", "ask_arca"):
        assert len(demo_scenarios(feature)) >= 5
    assert len(demo_scenarios("snowflake_stage2", "snowflake")) == 15


@pytest.mark.parametrize("scenario", demo_scenarios("stage1"), ids=lambda x: x["scenario_id"])
def test_stage1_catalog_outcomes(scenario):
    extracted = get_extractor("mock").extract(stage1_demo_text(scenario["inputs"]["variant"]), scenario["provider"])
    assert validate_draft(extracted).status == scenario["expected_outcome"]


@pytest.mark.parametrize("scenario", [x for x in CATALOG if x["feature"].startswith("stage2_")], ids=lambda x: x["scenario_id"])
def test_stage2_catalog_outcomes_and_exact_paste_records(scenario):
    bundle = get_provider("azure").load_bundle()
    source = [x for x in bundle["access_requests"] if x.get("pim_request_id") in scenario["pim_request_ids"]]
    records = [record_from_evidence(x) for x in source]
    result = assess_combined_pim(scenario["associated_change_number"], records, bundle,
                                 evidence_reference_time("azure", bundle["events"]))
    assert result.overall_assessment == scenario["expected_outcome"]
    if scenario["feature"] == "stage2_paste":
        assert [x.pim_request_id for x in parse_pim_records(pim_records_json(scenario, bundle))] == scenario["pim_request_ids"]


@pytest.mark.parametrize("scenario", demo_scenarios("stage3"), ids=lambda x: x["scenario_id"])
def test_stage3_catalog_outcomes(scenario):
    adapter = get_provider(scenario["provider"]); bundle = adapter.load_bundle()
    change = next(x for x in bundle["changes"] if x["change_id"] == scenario["associated_change_number"])
    assert adapter.evaluate_stage3(change, bundle["events"], bundle)["status"] == scenario["expected_outcome"]


@pytest.mark.parametrize("scenario", demo_scenarios("automated_investigation"), ids=lambda x: x["scenario_id"])
def test_full_lifecycle_catalog_outcomes(scenario):
    adapter = get_provider(scenario["provider"]); bundle = adapter.load_bundle()
    change = next(x for x in bundle["changes"] if x["change_id"] == scenario["associated_change_number"])
    result = build().invoke({"provider": scenario["provider"], "change": change,
                             "access_request": adapter.access_for_change(bundle, change["change_id"]),
                             "events": bundle["events"], "context": bundle})
    terminal = result.get("investigation") or result.get("stage3") or result["stage1"]
    assert terminal["status"] == scenario["expected_outcome"]


@pytest.mark.parametrize("scenario", demo_scenarios("undocumented"), ids=lambda x: x["scenario_id"])
def test_undocumented_catalog_outcomes(scenario):
    provider = scenario["provider"]; adapter = get_provider(provider); bundle = adapter.load_bundle()
    reference = evidence_reference_time(provider, bundle["events"])
    window = filter_evidence_window(provider, bundle["changes"], bundle["events"],
                                    scenario["inputs"]["time_range"], mode="demonstration", reference_time=reference)
    findings = adapter.find_unmatched(window["changes"], window["events"], bundle)
    assert undocumented_window_status(window["events"], findings) == scenario["expected_outcome"]
    assert len(findings) == scenario["inputs"]["expected_count"]


@pytest.mark.parametrize("scenario", demo_scenarios("ask_arca"), ids=lambda x: x["scenario_id"])
def test_ask_arca_catalog_outcomes(scenario):
    provider = scenario["provider"]; bundle = get_provider(provider).load_bundle()
    agent = InvestigationAgent(InvestigationTools(bundle=bundle, provider=provider, evidence_mode="demonstration"), model_mode="mock")
    assert agent.ask(scenario["inputs"]["question"], thread_id=scenario["scenario_id"])["status"] == scenario["expected_outcome"]


def test_dashboard_contains_all_demo_entry_points():
    source = Path("app.py").read_text(encoding="utf-8")
    for feature in ("stage1", "stage2_change", "stage2_user", "stage2_paste", "stage3", "automated_investigation", "undocumented", "ask_arca"):
        assert f'"{feature}"' in source
