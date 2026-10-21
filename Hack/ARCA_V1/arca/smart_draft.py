"""Safe restructuring and export helpers for the Stage 1 Smart Draft Assistant."""
from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import logging
import os
from time import perf_counter

from pydantic import BaseModel, Field

from .change_models import ExtractedChange, ImprovedChangeDraft
from .llm_provider import configured_provider, get_llm_provider
from .observability import log_performance

LOGGER = logging.getLogger("arca.smart_draft")


class DraftLanguageRefinement(BaseModel):
    """Only prose fields may be refined; technical facts never enter model output."""
    change_title: str = ""
    business_justification: str = ""
    implementation_steps: list[str] = Field(default_factory=list)
    validation_plan: list[str] = Field(default_factory=list)
    rollback_plan: str = ""
    expected_outcome: str = ""
    risk_and_impact: str = ""


@dataclass
class DraftRefinementOutcome:
    draft: ImprovedChangeDraft
    llm_used: bool = False
    cache_hit: bool = False
    status: str = "deterministic"
    timings: dict = field(default_factory=dict)


def _resource_parts(resource_id: str) -> tuple[str, str, str]:
    """Read structural components already explicit in an Azure ID or AWS ARN."""
    if not resource_id:
        return "", "", ""
    subscription = resource_group = ""
    sub = re.search(r"/subscriptions/([^/]+)", resource_id, re.I)
    group = re.search(r"/resourceGroups/([^/]+)", resource_id, re.I)
    if sub: subscription = sub.group(1)
    if group: resource_group = group.group(1)
    name = resource_id.rstrip("/").split("/")[-1] if "/" in resource_id else resource_id
    if resource_id.startswith("arn:"):
        parts = resource_id.split(":", 5)
        subscription = parts[4] if len(parts) > 4 else ""
        name = parts[5] if len(parts) > 5 else resource_id
    return subscription, resource_group, name


def _explicit_timezone(start: str, end: str, supplied: str) -> str:
    if supplied: return supplied
    zones = []
    for value in (start, end):
        match = re.search(r"(Z|[+-]\d{2}:\d{2})$", value)
        if match: zones.append(match.group(1))
    return zones[0] if zones and len(set(zones)) == 1 else ""


def _deterministic_draft(change: ExtractedChange) -> ImprovedChangeDraft:
    """Restructure explicit extraction output without filling unsupported values."""
    resource = change.target_resources[0] if change.target_resources else ""
    subscription, resource_group, resource_name = _resource_parts(resource)
    return ImprovedChangeDraft(
        provider=change.provider, change_title=change.title or change.purpose,
        change_number=change.change_id or "", business_justification=change.business_justification,
        environment=change.environment, subscription=change.subscription or subscription,
        resource_group=change.resource_group or resource_group,
        resource_name_or_id=resource or change.resource_name, implementer=change.implementer,
        change_start=change.start, change_end=change.end,
        timezone=_explicit_timezone(change.start, change.end, change.timezone),
        required_role="; ".join(change.role_requirements), required_access_scope="; ".join(change.scope_requirements),
        implementation_steps=list(change.implementation_tasks), validation_plan=list(change.validation_steps),
        rollback_plan=change.rollback_plan, expected_outcome=change.expected_outcome,
        risk_and_impact=change.risk_impact, expected_operations=list(change.expected_operations),
        source_mode=change.source_mode, source_text=change.raw_text, source_conflicts=list(change.conflicts),
    )


def _refinement_payload(baseline: ImprovedChangeDraft) -> str:
    return json.dumps({
        "change_title": baseline.change_title,
        "business_justification": baseline.business_justification,
        "implementation_steps": baseline.implementation_steps,
        "validation_plan": baseline.validation_plan,
        "rollback_plan": baseline.rollback_plan,
        "expected_outcome": baseline.expected_outcome,
        "risk_and_impact": baseline.risk_and_impact,
    }, sort_keys=True)


def _model_settings(selected: str) -> str:
    if selected == "openai":
        return "|".join((os.getenv("OPENAI_MODEL", "gpt-5-mini"),
                         os.getenv("OPENAI_REASONING_EFFORT", "minimal"),
                         os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1200")))
    return os.getenv("BEDROCK_MODEL_ID") or os.getenv("ARCA_BEDROCK_MODEL_ID", "")


@lru_cache(maxsize=64)
def _cached_refinement(selected: str, settings: str, payload_hash: str, payload: str) -> tuple[dict, dict]:
    del settings, payload_hash  # values intentionally participate in the cache key
    instructions = (
        "Improve readability and organization using only the supplied prose. Never add facts or fill blank fields. "
        "Do not alter technical identifiers because they are intentionally excluded. Do not approve or submit the change."
    )
    provider = get_llm_provider(selected)
    if hasattr(provider, "parse_with_metrics"):
        refined, metrics = provider.parse_with_metrics(instructions, payload, DraftLanguageRefinement)
    else:
        started = perf_counter()
        refined = provider.parse(instructions, payload, DraftLanguageRefinement)
        metrics = {"model": getattr(provider, "model", ""), "request_ms": (perf_counter() - started) * 1000,
                   "parse_ms": 0.0, "input_tokens": None, "output_tokens": None, "status": "success"}
    return refined.model_dump(), metrics


def clear_refinement_cache():
    _cached_refinement.cache_clear()


def improve_draft_with_status(change: ExtractedChange, mode: str | None = None) -> DraftRefinementOutcome:
    """Refine once per input/model key and safely retain a deterministic fallback."""
    input_started = perf_counter()
    baseline = _deterministic_draft(change)
    input_ms = (perf_counter() - input_started) * 1000
    log_performance(component_name="Input extraction", stage="Improve Draft", agent="Smart Draft Assistant",
                    duration_ms=input_ms)
    selected = configured_provider(mode)
    if selected == "mock":
        return DraftRefinementOutcome(draft=baseline, timings={"input_ms": input_ms})
    payload = _refinement_payload(baseline)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    before = _cached_refinement.cache_info()
    try:
        values, metrics = _cached_refinement(selected, _model_settings(selected), digest, payload)
        cache_hit = _cached_refinement.cache_info().hits > before.hits
        updates = {}
        for field_name in DraftLanguageRefinement.model_fields:
            original = getattr(baseline, field_name)
            candidate = values.get(field_name)
            updates[field_name] = original if original in ("", [], None) else candidate or original
        draft = baseline.model_copy(update=updates)
        metrics = {"input_ms": input_ms, **metrics}
        log_performance(component_name="LLM response parsing", stage="Improve Draft", agent="Smart Draft Assistant",
                        duration_ms=metrics.get("parse_ms", 0), llm_call_id=metrics.get("call_id"))
        LOGGER.info("draft_refinement provider=%s model=%s status=success cache_hit=%s input_ms=%.1f request_ms=%.1f parse_ms=%.1f input_tokens=%s output_tokens=%s",
                    selected, metrics.get("model"), cache_hit, input_ms, metrics.get("request_ms", 0), metrics.get("parse_ms", 0),
                    metrics.get("input_tokens"), metrics.get("output_tokens"))
        return DraftRefinementOutcome(draft=draft, llm_used=True, cache_hit=cache_hit, status="success", timings=metrics)
    except Exception as exc:
        LOGGER.warning("draft_refinement provider=%s model=%s status=fallback error_type=%s input_ms=%.1f",
                       selected, _model_settings(selected).split("|")[0], type(exc).__name__, input_ms)
        return DraftRefinementOutcome(draft=baseline, llm_used=False, status="fallback",
                                      timings={"input_ms": input_ms, "error_type": type(exc).__name__})


def improve_draft(change: ExtractedChange, mode: str | None = None) -> ImprovedChangeDraft:
    return improve_draft_with_status(change, mode).draft


FIELD_TO_DRAFT = {
    "purpose": "change_title", "title": "change_title", "change_id": "change_number",
    "business_justification": "business_justification", "environment": "environment",
    "subscription": "subscription", "resource_group": "resource_group", "resource_name": "resource_name_or_id",
    "target_resources": "resource_name_or_id", "implementer": "implementer", "start": "change_start",
    "end": "change_end", "change_window": "change_end", "timezone": "timezone",
    "role_requirements": "required_role", "scope_requirements": "required_access_scope",
    "implementation_tasks": "implementation_steps", "validation_steps": "validation_plan",
    "rollback_plan": "rollback_plan", "expected_outcome": "expected_outcome", "risk_impact": "risk_and_impact",
    "change_details": "change_title",
}


def draft_field_findings(validation) -> dict[str, list[dict]]:
    """Map existing validation issues to editable fields without changing policy results."""
    output: dict[str, list[dict]] = {}
    for issue in validation.issues if validation else []:
        field_name = FIELD_TO_DRAFT.get(issue.field)
        if not field_name:
            continue
        message = "End time must be later than start time." if issue.field == "change_window" else issue.reason
        level = "error" if issue.severity == "ERROR" or issue.category == "INCONSISTENT" else "review"
        item = {"message": message, "level": level, "field": issue.field}
        if item not in output.setdefault(field_name, []):
            output[field_name].append(item)
    return output


def draft_to_extracted(draft: ImprovedChangeDraft) -> ExtractedChange:
    """Convert edited controls back to the shared validation schema."""
    resource = draft.resource_name_or_id.strip()
    return ExtractedChange(
        change_id=draft.change_number or None, provider=draft.provider, source_mode=draft.source_mode,
        title=draft.change_title, purpose=draft.change_title,
        business_justification=draft.business_justification, environment=draft.environment,
        subscription=draft.subscription, resource_group=draft.resource_group,
        resource_name=resource, target_resources=[resource] if resource else [], implementer=draft.implementer,
        implementation_tasks=draft.implementation_steps, start=draft.change_start, end=draft.change_end,
        timezone=draft.timezone, expected_outcome=draft.expected_outcome,
        validation_steps=draft.validation_plan, rollback_plan=draft.rollback_plan,
        risk_impact=draft.risk_and_impact,
        role_requirements=[draft.required_role] if draft.required_role else [],
        scope_requirements=[draft.required_access_scope] if draft.required_access_scope else [],
        expected_operations=draft.expected_operations, conflicts=draft.source_conflicts, raw_text=draft.source_text,
    )


def servicenow_text(draft: ImprovedChangeDraft) -> str:
    """Create a clean copy-ready text representation without inventing content."""
    sections = [
        ("CHANGE TITLE", draft.change_title), ("CHANGE NUMBER", draft.change_number),
        ("BUSINESS JUSTIFICATION", draft.business_justification), ("ENVIRONMENT", draft.environment),
        ("SUBSCRIPTION", draft.subscription), ("RESOURCE GROUP", draft.resource_group),
        ("RESOURCE NAME / ID", draft.resource_name_or_id), ("IMPLEMENTER", draft.implementer),
        ("CHANGE START", draft.change_start), ("CHANGE END", draft.change_end), ("TIMEZONE", draft.timezone),
        ("REQUIRED ROLE", draft.required_role), ("REQUIRED ACCESS SCOPE", draft.required_access_scope),
        ("IMPLEMENTATION STEPS", "\n".join(f"{i}. {value}" for i, value in enumerate(draft.implementation_steps, 1))),
        ("VALIDATION PLAN", "\n".join(f"{i}. {value}" for i, value in enumerate(draft.validation_plan, 1))),
        ("ROLLBACK PLAN", draft.rollback_plan), ("EXPECTED OUTCOME", draft.expected_outcome),
        ("RISK AND IMPACT", draft.risk_and_impact),
    ]
    return "\n\n".join(f"{label}\n{value}" for label, value in sections)
