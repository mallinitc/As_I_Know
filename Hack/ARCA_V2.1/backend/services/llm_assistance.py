from __future__ import annotations

from copy import deepcopy
from time import perf_counter
from typing import Any, Literal

from backend.llm.gateway import LlmGateway, LlmGatewayError
from backend.llm.schemas import TokenUsage
from backend.services.llm_metrics import execution_metrics


AgentName = Literal[
    "change_quality",
    "access_intelligence",
    "execution_assurance",
    "risk_investigation",
    "snowflake_change_access",
]

_ALLOWED_FIELDS: dict[AgentName, tuple[str, ...]] = {
    "change_quality": ("provider", "change_id", "overall_status", "findings", "missing_information", "recommendations", "change"),
    "access_intelligence": ("provider", "change_id", "overall_status", "findings", "missing_information", "recommendations", "limitations", "permission_evaluations", "pim_assessments", "covered_operations", "missing_operations", "change", "access_request"),
    "execution_assurance": ("provider", "change_id", "overall_status", "confidence", "findings", "expected_operations", "observed_operations", "recommendations", "limitations", "evidence"),
    "risk_investigation": ("providers_investigated", "summary", "risk_counts", "findings", "evidence_references", "activity_timeline", "confidence", "evidence_limitations"),
    "snowflake_change_access": ("provider", "change_id", "overall_status", "change_quality", "window_assessment", "role_assessment", "missing_information", "findings", "evidence", "warning"),
}


def _bounded(value: Any, *, depth: int = 0) -> Any:
    if depth >= 7:
        return "[nested content omitted]"
    if isinstance(value, str):
        return value[:4000]
    if isinstance(value, list):
        return [_bounded(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, dict):
        return {str(key)[:100]: _bounded(item, depth=depth + 1) for key, item in list(value.items())[:80]}
    return value


def evidence_ids(result: dict[str, Any]) -> list[str]:
    found: list[str] = []

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str) and (
            key.casefold().endswith("_id")
            or key.casefold().endswith("_ids")
            or key.casefold() in {"change_id", "evidence_id", "eventid"}
        ):
            if value and value not in found:
                found.append(value)

    visit(result)
    return found[:100]


_AGENT_IDS: dict[AgentName, str] = {
    "change_quality": "A1",
    "access_intelligence": "A2",
    "execution_assurance": "A3",
    "risk_investigation": "A4",
    "snowflake_change_access": "A1/A2",
}


def _base_analysis(mode: str) -> dict[str, Any]:
    return {
        "execution_mode": mode,
        "llm_invoked": False,
        "llm_status": "not_invoked",
        "model_identifier": None,
        "ai_summary": None,
        "ai_observations": [],
        "ai_recommendations": [],
        "evidence_references": [],
        "limitations": [],
        "token_usage": None,
        "execution_metrics": None,
    }


def attach_ai_analysis(
    deterministic_result: dict[str, Any],
    agent: AgentName,
    mode: str = "deterministic",
    *,
    gateway: LlmGateway | None = None,
    started_at: float | None = None,
) -> dict[str, Any]:
    analysis_started = started_at or perf_counter()
    result = deepcopy(deterministic_result)
    normalized_mode = mode.strip().casefold()
    if normalized_mode not in {"deterministic", "llm_assisted"}:
        normalized_mode = "deterministic"
    analysis = _base_analysis(normalized_mode)
    result["ai_analysis"] = analysis
    if normalized_mode == "deterministic":
        analysis["execution_metrics"] = execution_metrics(
            agent_id=_AGENT_IDS[agent], execution_mode=normalized_mode, provider=None, model=None,
            status="not_invoked", usage=TokenUsage(), started_at=analysis_started,
        )
        return result

    llm = gateway or LlmGateway()
    capability = llm.capability()
    analysis["model_identifier"] = capability.get("model_identifier")
    if not capability.get("available"):
        analysis["llm_status"] = str(capability.get("status") or "unavailable")
        analysis["limitations"] = ["LLM assistance was unavailable; deterministic findings remain authoritative."]
        analysis["execution_metrics"] = execution_metrics(
            agent_id=_AGENT_IDS[agent], execution_mode=normalized_mode,
            provider=str(capability.get("provider") or "") or None,
            model=str(capability.get("model_identifier") or "") or None,
            status=analysis["llm_status"], usage=TokenUsage(), started_at=analysis_started,
        )
        return result

    supplied_ids = evidence_ids(result)
    payload = {key: _bounded(result.get(key)) for key in _ALLOWED_FIELDS[agent] if key in result}
    try:
        generated, model, usage = llm.analyze(agent, payload, supplied_ids)
    except LlmGatewayError as exc:
        analysis["llm_invoked"] = bool(exc.usage.calls)
        analysis["llm_status"] = exc.status
        analysis["limitations"] = [f"LLM assistance was not completed ({exc.status}); deterministic findings remain authoritative."]
        analysis["token_usage"] = exc.usage.model_dump()
        analysis["execution_metrics"] = execution_metrics(
            agent_id=_AGENT_IDS[agent], execution_mode=normalized_mode,
            provider=str(capability.get("provider") or "") or None,
            model=str(capability.get("model_identifier") or "") or None,
            status=exc.status, usage=exc.usage, started_at=analysis_started,
        )
        return result

    valid_references = [item for item in generated.evidence_references if item in supplied_ids]
    fabricated = [item for item in generated.evidence_references if item not in supplied_ids]
    limitations = list(generated.limitations)
    if fabricated:
        limitations.append("One or more model-generated evidence references were removed because they were not present in the supplied evidence.")
    analysis.update({
        "llm_invoked": True,
        "llm_status": "completed",
        "model_identifier": model,
        "ai_summary": generated.ai_summary,
        "ai_observations": generated.ai_observations,
        "ai_recommendations": generated.ai_recommendations,
        "evidence_references": valid_references,
        "limitations": list(dict.fromkeys(limitations)),
        "token_usage": usage.model_dump(),
    })
    analysis["execution_metrics"] = execution_metrics(
        agent_id=_AGENT_IDS[agent], execution_mode=normalized_mode,
        provider=str(capability.get("provider") or "") or None, model=model,
        status="completed", usage=usage, started_at=analysis_started,
    )
    return result


__all__ = ["attach_ai_analysis", "evidence_ids"]
