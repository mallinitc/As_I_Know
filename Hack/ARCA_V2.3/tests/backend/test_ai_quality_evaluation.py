from __future__ import annotations

from copy import deepcopy

from scripts.evaluate_ai_quality import evaluate, load_cases, run_a1_a4, score_case


def test_dataset_covers_required_agents_and_scenario_families():
    cases = load_cases()
    assert len(cases) == 14
    assert {item["agent"] for item in cases} == {"A1", "A2", "A3", "A4", "A5"}
    assert {item["case_id"] for item in cases} >= {
        "A1-VALID", "A1-INCOMPLETE", "A1-RISKY",
        "A2-APPROPRIATE", "A2-OVERPRIVILEGED", "A2-INSUFFICIENT",
        "A3-COMPLIANT", "A3-WRONG-RESOURCE", "A3-ACTOR-DEVIATION",
        "A4-DOCUMENTED", "A4-POTENTIALLY-UNDOCUMENTED",
        "A5-RESOURCE", "A5-ACCESS", "A5-MULTITURN-FOLLOWUP",
    }


def test_every_case_has_traceable_evidence_and_verified_decision():
    report = evaluate(load_cases())
    for item in report["cases"]:
        assert item["expected_decision"] == item["actual_decision"], item["case_id"]
        assert set(item["expected_evidence_ids"]) <= set(item["available_evidence_ids"]), item["case_id"]
        assert item["scores"]["groundedness"] == "pass"


def test_mocked_quality_scores_are_reproducible_and_exclude_human_feedback():
    first = evaluate(load_cases())
    second = evaluate(load_cases())
    assert first["pass_rates"] == second["pass_rates"]
    assert all(value["fail"] == 0 for value in first["pass_rates"].values())
    assert first["evaluation_mode"] == "controlled_mock_llm"
    assert first["live_llm_calls"] == 0
    assert "human feedback" in " ".join(first["limitations"]).casefold()


def test_prompt_routes_are_stage_specific_and_agent5_uses_synthesis():
    report = evaluate(load_cases())
    expected = {"A1": "change_quality", "A2": "access_intelligence", "A3": "execution_assurance", "A4": "risk_investigation", "A5": "agent5_synthesis"}
    for item in report["cases"]:
        assert item["prompt_route"] == expected[item["agent"]]


def test_a2_and_a4_analysis_context_normalizes_decisions_without_mutating_results():
    cases = {item["case_id"]: item for item in load_cases()}
    a2_output, a2_source = run_a1_a4(cases["A2-OVERPRIVILEGED"])
    a4_output, a4_source = run_a1_a4(cases["A4-DOCUMENTED"])
    assert a2_output["decision"] == "OVERPRIVILEGED"
    assert "overall_status" not in a2_source and a2_source["overall_assessment"] == "OVERPRIVILEGED"
    assert a4_output["decision"] == "NO_FINDINGS"
    assert "overall_status" not in a4_source and a4_source["findings"] == []


def test_isolation_scoring_detects_cross_provider_and_persona_leakage():
    case = next(item for item in load_cases() if item["case_id"] == "A1-VALID")
    output, _ = run_a1_a4(case)
    leaked = deepcopy(output)
    leaked["visible_text"] += " AWS arca_manager"
    scores = score_case(case, leaked)
    assert scores["isolation"] == "fail"
    assert score_case(case, output)["isolation"] == "pass"


def test_fallback_validation_rejects_verbose_mock_and_preserves_decision():
    check = evaluate(load_cases())["fallback_validation"]
    assert check == {"passed": True, "status": "invalid_response", "deterministic_decision_preserved": True}
