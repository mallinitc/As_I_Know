from __future__ import annotations

from copy import deepcopy
import json
import re
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

_TEXT_KEYS = ("category", "field", "severity", "confidence", "summary", "message", "reason", "explanation", "recommendation", "status")


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


def _selected_records(value: Any, limit: int = 6) -> list[Any]:
    if not isinstance(value, list):
        return []
    selected: list[Any] = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            selected.append(_bounded(item))
            continue
        record = {key: _bounded(item[key]) for key in _TEXT_KEYS if key in item}
        for key in ("evidence_id", "evidence_ids", "event_id", "event_ids", "event_data_id", "query_id", "operation", "resource", "resource_id", "actor", "caller", "timestamp", "event_timestamp", "change_id", "change_match", "correlation", "approval_state", "decision", "iam_action", "deviations"):
            if key in item:
                record[key] = _bounded(item[key])
        selected.append(record)
    return selected


def _compact_payload(result: dict[str, Any], agent: AgentName) -> dict[str, Any]:
    # Snowflake's existing shared contract is deliberately preserved.
    if agent == "snowflake_change_access":
        return {key: _bounded(result.get(key)) for key in _ALLOWED_FIELDS[agent] if key in result}
    decision = result.get("overall_status") or result.get("overall_assessment")
    if decision is None and agent == "risk_investigation":
        decision = "FINDINGS_IDENTIFIED" if result.get("findings") else "NO_FINDINGS"
    payload: dict[str, Any] = {
        "provider": result.get("provider") or result.get("providers_investigated"),
        "change_id": result.get("change_id"),
        "overall_status": decision,
        "findings": _selected_records(result.get("findings"), 6),
        "missing_information": _bounded((result.get("missing_information") or [])[:8]),
        "recommendations": _bounded((result.get("recommendations") or [])[:3]),
        "limitations": _bounded((result.get("limitations") or result.get("evidence_limitations") or [])[:4]),
    }
    if agent == "change_quality":
        change = result.get("change") if isinstance(result.get("change"), dict) else {}
        payload["change_intent"] = {key: (_bounded(change.get(key))[:1000] if isinstance(_bounded(change.get(key)), str) else _bounded(change.get(key))) for key in ("title", "short_description", "description", "environment", "expected") if change.get(key) not in (None, "", [])}
    elif agent == "access_intelligence":
        payload.update({
            "permission_evaluations": _selected_records(result.get("permission_evaluations"), 8),
            "pim_assessments": _selected_records(result.get("pim_assessments"), 6),
            "covered_operations": _bounded((result.get("covered_operations") or [])[:8]),
            "missing_operations": _bounded((result.get("missing_operations") or [])[:8]),
        })
        request = result.get("access_request") if isinstance(result.get("access_request"), dict) else {}
        payload["access_request"] = {key: _bounded(request.get(key)) for key in ("request_id", "principal_id", "principal_upn", "role", "role_name", "scope", "requested_start", "requested_end", "status", "justification") if request.get(key) not in (None, "", [])}
    elif agent == "execution_assurance":
        payload["expected_operations"] = _selected_records(result.get("expected_operations"), 8)
        payload["observed_operations"] = _selected_records(result.get("observed_operations"), 8)
        payload["confidence"] = result.get("confidence")
    elif agent == "risk_investigation":
        payload.update({
            "risk_counts": _bounded(result.get("risk_counts") or {}),
            "confidence": result.get("confidence"),
            "relevant_activity": _selected_records(result.get("activity_timeline"), 4),
        })
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def _fallback_analysis(result: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    decision = result.get("overall_status") or result.get("overall_assessment")
    status = str(decision or "REVIEW_REQUIRED").replace("_", " ").title()
    reasons: list[str] = []
    for item in (result.get("findings") or [])[:2]:
        if isinstance(item, dict):
            text = next((item.get(key) for key in ("summary", "message", "explanation", "category") if item.get(key)), None)
            if text:
                reasons.append(str(text)[:240])
    missing = result.get("missing_information") or []
    if not reasons and missing:
        reasons.append("Missing information: " + ", ".join(map(str, missing[:3])))
    recommendations = result.get("recommendations") or []
    return (
        f"The deterministic assessment is {status}; model-generated interpretation is unavailable.",
        reasons,
        [str(recommendations[0])[:240]] if recommendations else [],
    )


def _validate_generated(generated: Any, usage: TokenUsage, payload: dict[str, Any]) -> None:
    visible = [generated.ai_summary, *generated.ai_observations, *generated.ai_recommendations]
    if len(generated.ai_observations) > 2 or len(generated.ai_recommendations) > 1:
        raise LlmGatewayError("invalid_response", "The model response did not follow the concise analysis contract.", usage)
    if sum(len(str(item).split()) for item in visible) > 100:
        raise LlmGatewayError("invalid_response", "The model response exceeded the concise analysis limit.", usage)
    text = " ".join(map(str, visible))
    if re.search(r"\brisk[- ]free\b|\b(?:is|was|confirmed|proven)\s+(?:definitively\s+)?malicious\b", text, re.IGNORECASE):
        raise LlmGatewayError("invalid_response", "The model response introduced an unsupported security claim.", usage)
    source = json.dumps(payload, default=str, ensure_ascii=True).casefold()
    identifiers = re.findall(r"\b(?:CHG-[A-Z0-9-]+|[A-Z]{2,}(?:-[A-Z0-9]+)+)\b", text)
    identifiers.extend(re.findall(r"[\w.+-]+@[\w.-]+", text, re.IGNORECASE))
    if any(identifier.casefold() not in source for identifier in identifiers):
        raise LlmGatewayError("invalid_response", "The model response introduced an identifier absent from supplied evidence.", usage)


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
    evidence_environment = result.get("provider")
    if not evidence_environment and len(result.get("providers_investigated") or []) == 1:
        evidence_environment = result["providers_investigated"][0]
    result["ai_analysis"] = analysis
    if normalized_mode == "deterministic":
        analysis["execution_metrics"] = execution_metrics(
            agent_id=_AGENT_IDS[agent], execution_mode=normalized_mode, provider=None, model=None,
            status="not_invoked", usage=TokenUsage(), started_at=analysis_started, environment=evidence_environment,
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
            status=analysis["llm_status"], usage=TokenUsage(), started_at=analysis_started, environment=evidence_environment,
        )
        return result

    supplied_ids = evidence_ids(result)
    payload = _compact_payload(result, agent)
    try:
        generated, model, usage = llm.analyze(agent, payload, supplied_ids)
        if agent != "snowflake_change_access":
            _validate_generated(generated, usage, payload)
    except LlmGatewayError as exc:
        analysis["llm_invoked"] = bool(exc.usage.calls)
        analysis["llm_status"] = exc.status
        summary, observations, recommendations = _fallback_analysis(result)
        analysis["ai_summary"] = summary
        analysis["ai_observations"] = observations
        analysis["ai_recommendations"] = recommendations
        analysis["limitations"] = [f"{exc} Deterministic findings remain authoritative; the visible summary is a deterministic fallback."]
        analysis["token_usage"] = exc.usage.model_dump()
        analysis["execution_metrics"] = execution_metrics(
            agent_id=_AGENT_IDS[agent], execution_mode=normalized_mode,
            provider=str(capability.get("provider") or "") or None,
            model=str(capability.get("model_identifier") or "") or None,
            status=exc.status, usage=exc.usage, started_at=analysis_started, environment=evidence_environment,
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
        status="completed", usage=usage, started_at=analysis_started, environment=evidence_environment,
    )
    return result


__all__ = ["attach_ai_analysis", "evidence_ids"]
