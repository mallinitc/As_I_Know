from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.schemas import AgentAssistanceOutput, LlmCallMetrics, LlmSynthesis, TokenUsage
from backend.services.ask_arca import AskArcaService
from backend.services.azure_execution import AzureExecutionService
from backend.services.llm_assistance import attach_ai_analysis, evidence_ids
from backend.services.risk_investigation import RiskInvestigationService
from backend.services.stage1 import extract_change, scenarios as stage1_scenarios, validate_draft
from backend.services.stage2 import Stage2Service
from backend.services.timestamps import parse_utc


DEFAULT_CASES = PROJECT_ROOT / "evaluation" / "ai_quality_cases.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "evaluation" / "results" / "ai_quality_mock_results.json"
AGENT_NAMES = {"A1": "change_quality", "A2": "access_intelligence", "A3": "execution_assurance", "A4": "risk_investigation"}


def usage(operation: str) -> TokenUsage:
    return TokenUsage(
        input_tokens=40,
        output_tokens=30,
        total_tokens=70,
        calls=[LlmCallMetrics(operation=operation, status="completed", provider="mock_evaluation", model_identifier="mock-quality-v1", duration_ms=1, input_tokens=40, output_tokens=30, total_tokens=70)],
    )


class MockAgentGateway:
    def __init__(self, response: dict[str, Any]):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def capability(self) -> dict[str, Any]:
        return {"enabled": True, "available": True, "provider": "mock_evaluation", "model_identifier": "mock-quality-v1", "status": "available"}

    def analyze(self, agent: str, payload: dict[str, Any], supplied_ids: list[str]):
        self.calls.append({"agent": agent, "payload": payload, "evidence_ids": supplied_ids})
        value = AgentAssistanceOutput(
            ai_summary=self.response["summary"],
            ai_observations=self.response["reasons"],
            ai_recommendations=self.response["next_action"],
            evidence_references=self.response["citations"],
            limitations=["Controlled mocked response; no live model was invoked."],
        )
        return value, "mock-quality-v1", usage(f"{agent}_analysis")


class MockAskGateway:
    def __init__(self, response: dict[str, Any]):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def capability(self) -> dict[str, Any]:
        return {"enabled": True, "available": True, "provider": "mock_evaluation", "model_identifier": "mock-quality-v1", "status": "available"}

    def synthesize(self, question: str, deterministic_result: dict[str, Any], supplied_ids: list[str]):
        self.calls.append({"question": question, "evidence_ids": supplied_ids})
        parts = [self.response["summary"], *self.response["reasons"], *self.response["next_action"]]
        value = LlmSynthesis(summary=" ".join(parts), evidence_citations=self.response["citations"])
        return value, "mock-quality-v1", usage("agent5_synthesis")


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise ValueError("The AI quality evaluation dataset must be a non-empty array.")
    return value


def deterministic_result(case: dict[str, Any]) -> dict[str, Any]:
    source = case["source"]
    kind = source["type"]
    if kind == "stage1":
        scenario = next(item for item in stage1_scenarios(case["provider"]) if item["scenario_id"] == source["scenario_id"])
        extracted = extract_change(scenario["text"], case["provider"])
        validation = validate_draft(extracted)
        return {
            "provider": case["provider"], "scenario_id": source["scenario_id"],
            "overall_status": validation.status, "findings": [item.model_dump(mode="json") for item in validation.issues],
            "missing_information": validation.missing_mandatory, "recommendations": validation.clarification_questions,
            "change": extracted.model_dump(mode="json"),
        }
    if kind == "stage2":
        scenario = next(item for item in Stage2Service().scenarios() if item["scenario_id"] == source["scenario_id"])
        result = Stage2Service().assess("change", change_id=scenario["change_id"])
        return {**result, "scenario_id": source["scenario_id"]}
    if kind == "stage3":
        return AzureExecutionService().assess_change(source["change_id"], parse_utc(source["evaluation_timestamp"]), source["scenario_id"])
    if kind == "stage4":
        arguments = {key: value for key, value in source.items() if key != "type"}
        return RiskInvestigationService().investigate(**arguments)
    raise ValueError(f"Unsupported deterministic source type: {kind}")


def decision_for(agent: str, result: dict[str, Any]) -> str:
    if agent == "A4":
        return "FINDINGS_IDENTIFIED" if result.get("findings") else "NO_FINDINGS"
    return str(result.get("overall_status") or result.get("overall_assessment") or "")


def run_a1_a4(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    deterministic = deterministic_result(case)
    gateway = MockAgentGateway(case["mock_response"])
    evaluated = attach_ai_analysis(deterministic, AGENT_NAMES[case["agent"]], "llm_assisted", gateway=gateway)
    analysis = evaluated["ai_analysis"]
    visible = " ".join(filter(None, [analysis["ai_summary"], *analysis["ai_observations"], *analysis["ai_recommendations"]]))
    return {
        "decision": decision_for(case["agent"], deterministic),
        "available_evidence_ids": evidence_ids(deterministic),
        "visible_text": visible,
        "summary": analysis["ai_summary"],
        "reasons": analysis["ai_observations"],
        "next_action": analysis["ai_recommendations"],
        "citations": analysis["evidence_references"],
        "llm_status": analysis["llm_status"],
        "prompt_route": gateway.calls[0]["agent"] if gateway.calls else None,
        "prompt_payload": gateway.calls[0]["payload"] if gateway.calls else {},
    }, deterministic


def run_a5(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source = case["source"]
    gateway = MockAskGateway(case["mock_response"])
    service = AskArcaService(gateway=gateway)
    context = None
    if source["type"] == "stage5_followup":
        first = service._ask_deterministic(source["initial_question"], source["evaluation_timestamp"])
        context = first["conversation_context"]
    result = service.ask(source["question"], mode="llm_assisted", evaluation_timestamp=source["evaluation_timestamp"], conversation_context=context)
    return {
        "decision": result["overall_status"],
        "available_evidence_ids": service._evidence_ids(result),
        "visible_text": result.get("model_generated_explanation") or "",
        "summary": result.get("model_generated_explanation"),
        "reasons": [],
        "next_action": case["mock_response"]["next_action"],
        "citations": result.get("llm_evidence_citations") or [],
        "llm_status": result["llm_status"],
        "prompt_route": "agent5_synthesis" if gateway.calls else None,
        "prompt_payload": {"latest_question": gateway.calls[0]["question"] if gateway.calls else None},
    }, result


def rating(passed: bool) -> str:
    return "pass" if passed else "fail"


def score_case(case: dict[str, Any], output: dict[str, Any]) -> dict[str, str]:
    text = output["visible_text"].casefold()
    expected_points = [item.casefold() for item in case["expected_points"]]
    available = set(output["available_evidence_ids"])
    expected_evidence = set(case["expected_evidence_ids"])
    citations = set(output["citations"])
    other_providers = {"aws", "azure", "snowflake"} - {case["provider"]}
    scores = {
        "relevance": rating(all(point in text for point in expected_points)),
        "correctness": rating(output["decision"] == case["expected_decision"] and output["llm_status"] == "completed"),
        "groundedness": rating(expected_evidence <= available and citations <= available and citations <= expected_evidence),
        "clarity": rating(bool(text.strip()) and "{" not in text and "[" not in text and len(text.split()) <= 100),
        "concision": rating(len(text.split()) <= 100 and len(output["reasons"]) <= 2 and len(output["next_action"]) <= 1),
        "actionability": "not_applicable" if not case["next_action_required"] else rating(bool(output["next_action"])),
        "isolation": rating(not any(provider in text for provider in other_providers) and "arca_manager" not in text and "arca_analyst" not in text),
    }
    return scores


def fallback_check() -> dict[str, Any]:
    class InvalidGateway(MockAgentGateway):
        def analyze(self, agent: str, payload: dict[str, Any], supplied_ids: list[str]):
            value, model, measured = super().analyze(agent, payload, supplied_ids)
            value.ai_summary = " ".join(["verbose"] * 101)
            return value, model, measured

    source = {"provider": "azure", "overall_status": "INCOMPLETE", "findings": [{"reason": "Implementer is missing."}]}
    result = attach_ai_analysis(source, "change_quality", "llm_assisted", gateway=InvalidGateway({"summary": "ignored", "reasons": [], "next_action": [], "citations": []}))
    analysis = result["ai_analysis"]
    return {
        "passed": analysis["llm_status"] == "invalid_response" and "model-generated interpretation is unavailable" in (analysis["ai_summary"] or ""),
        "status": analysis["llm_status"],
        "deterministic_decision_preserved": result["overall_status"] == "INCOMPLETE",
    }


def evaluate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for case in cases:
        output, _ = run_a5(case) if case["agent"] == "A5" else run_a1_a4(case)
        scores = score_case(case, output)
        failures = [dimension for dimension, value in scores.items() if value == "fail"]
        results.append({
            "case_id": case["case_id"], "agent": case["agent"], "provider": case["provider"],
            "source": case["source"], "expected_decision": case["expected_decision"], "actual_decision": output["decision"],
            "expected_evidence_ids": case["expected_evidence_ids"], "available_evidence_ids": output["available_evidence_ids"],
            "prompt_route": output["prompt_route"], "response": {key: output[key] for key in ("summary", "reasons", "next_action", "citations", "llm_status")},
            "scores": scores, "failure_causes": failures,
        })
    totals: dict[str, Counter] = {dimension: Counter() for dimension in ("relevance", "correctness", "groundedness", "clarity", "concision", "actionability", "isolation")}
    for result in results:
        for dimension, value in result["scores"].items():
            totals[dimension][value] += 1
    pass_rates = {
        dimension: {
            "pass": counts["pass"], "fail": counts["fail"], "not_applicable": counts["not_applicable"],
            "evaluated": counts["pass"] + counts["fail"],
            "pass_rate": round(counts["pass"] / (counts["pass"] + counts["fail"]), 4) if counts["pass"] + counts["fail"] else None,
        }
        for dimension, counts in totals.items()
    }
    return {
        "evaluation_version": "1.0", "evaluation_mode": "controlled_mock_llm", "live_llm_calls": 0,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "case_count": len(results), "agents": sorted({item["agent"] for item in results}),
        "pass_rates": pass_rates, "fallback_validation": fallback_check(), "cases": results,
        "limitations": [
            "Scores measure controlled mocked responses, prompt routing, deterministic consistency, and evidence reference handling; they do not measure live model variability.",
            "No LLM-as-judge or paid model request was used.",
            "Human feedback is not included in verified labels or pass-rate calculations.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ARCA's controlled offline AI response-quality evaluation.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = evaluate(load_cases(args.cases))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = sum(item["fail"] for item in report["pass_rates"].values())
    print(f"ARCA AI quality evaluation: {report['case_count']} mocked cases, {failed} failed dimension ratings")
    print(f"Results: {args.output}")
    return 1 if failed or not report["fallback_validation"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
