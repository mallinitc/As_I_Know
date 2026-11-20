"""Exact V1 Stage 1 deterministic extraction, validation, and draft behavior."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.config import PROJECT_ROOT
from backend.llm.gateway import LlmGateway, LlmGatewayError
from backend.llm.schemas import TokenUsage
from backend.schemas.stage1 import (
    DraftValidationResult, ExpectedOperation, ExtractedChange, ImprovedChangeDraft, ValidationIssue,
)
from backend.services.llm_metrics import execution_metrics

POLICY_PATH = PROJECT_ROOT / "config" / "change_validation_policy.json"
CATALOG_PATH = PROJECT_ROOT / "data" / "demo_catalog.json"
FIELDS = {
    "purpose": "purpose", "change title": "title", "title": "title", "change number": "change_id",
    "business justification": "business_justification", "environment": "environment",
    "implementer": "implementer", "resource": "target_resources", "target resource": "target_resources",
    "scope": "scope_requirements", "subscription": "subscription", "resource group": "resource_group",
    "resource name": "resource_name", "implementation tasks": "implementation_tasks",
    "implementation plan": "implementation_tasks", "start": "start", "start time": "start",
    "end": "end", "end time": "end", "timezone": "timezone", "expected outcome": "expected_outcome",
    "post-change validation": "validation_steps", "validation steps": "validation_steps",
    "rollback plan": "rollback_plan", "risk and impact": "risk_impact", "risk/impact": "risk_impact",
    "role requirements": "role_requirements", "scope requirements": "scope_requirements",
    "expected operations": "expected_operations",
}
LIST_FIELDS = {"target_resources", "implementation_tasks", "validation_steps", "role_requirements", "scope_requirements"}


def _parts(value: str) -> list[str]:
    return [item.strip(" -\t") for item in re.split(r"[;|]", value) if item.strip(" -\t")]


def extract_change(text: str, provider: str, overrides: dict[str, Any] | None = None) -> ExtractedChange:
    values: dict[str, Any] = {"provider": provider, "source_mode": "pasted", "raw_text": text}
    seen: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Za-z][A-Za-z /_-]+?)\s*:\s*(.+?)\s*$", line)
        if not match:
            continue
        key = FIELDS.get(match.group(1).strip().lower())
        if not key:
            continue
        value = match.group(2).strip()
        seen.setdefault(key, []).append(value)
        if key == "expected_operations":
            values[key] = [ExpectedOperation(operation=part.partition(" @ ")[0].strip(), resource_id=part.partition(" @ ")[2].strip()) for part in _parts(value)]
        elif key in LIST_FIELDS:
            values[key] = _parts(value)
        else:
            values[key] = value
    values["conflicts"] = [f"Conflicting values supplied for {key}: {items}" for key, items in seen.items() if len(set(items)) > 1]
    allowed = set(ExtractedChange.model_fields)
    for key, value in (overrides or {}).items():
        if key in allowed and value:
            values[key] = [value] if key == "target_resources" and isinstance(value, str) else value
    return ExtractedChange.model_validate(values)


def validate_draft(change: ExtractedChange) -> DraftValidationResult:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    values = change.model_dump()
    issues: list[ValidationIssue] = []
    missing: list[str] = []
    for field in policy["mandatory_fields"]:
        if not values.get(field):
            missing.append(field)
            issues.append(ValidationIssue(field=field, reason="Mandatory information is missing.", severity="ERROR", category="INCOMPLETE", recommended_correction=f"Provide an explicit {field.replace('_', ' ')}."))
    parsed: dict[str, datetime | None] = {"start": None, "end": None}
    for field in ("start", "end"):
        value = getattr(change, field)
        if not value:
            continue
        try:
            item = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if item.tzinfo is None or item.utcoffset() is None:
                raise ValueError("timezone is required")
            parsed[field] = item
        except ValueError as exc:
            issues.append(ValidationIssue(field=field, reason=f"Invalid {field} timestamp: {exc}.", severity="ERROR", category="INCONSISTENT", recommended_correction=f"Provide an ISO 8601 {field} timestamp with an explicit timezone."))
    if parsed["start"] and parsed["end"] and parsed["start"] >= parsed["end"]:
        issues.append(ValidationIssue(field="change_window", reason="The end timestamp must be later than the start timestamp.", severity="ERROR", category="INCONSISTENT", recommended_correction="Correct the change window and retain explicit timezones."))
    for conflict in change.conflicts:
        issues.append(ValidationIssue(field="change_details", reason=conflict, severity="ERROR", category="INCONSISTENT", recommended_correction="Resolve the conflicting values and provide one authoritative value."))
    for field in ("implementation_tasks", "purpose", "target_resources"):
        raw = values.get(field, "")
        text = " ".join(raw) if isinstance(raw, list) else str(raw)
        if text and any(phrase in text.lower() for phrase in policy.get("ambiguous_phrases", [])):
            issues.append(ValidationIssue(field=field, reason="The supplied information contains non-specific instructions.", severity="REVIEW", category="AMBIGUOUS", recommended_correction="Replace vague wording with explicit resources, operations, and accountable steps."))
    for ambiguity in change.ambiguities:
        issues.append(ValidationIssue(field="change_details", reason=ambiguity, severity="REVIEW", category="AMBIGUOUS", recommended_correction="Clarify the statement before submission."))
    categories = {item.category for item in issues}
    status = "INCONSISTENT" if "INCONSISTENT" in categories else "AMBIGUOUS" if "AMBIGUOUS" in categories else "INCOMPLETE" if missing else "MANUAL_REVIEW_REQUIRED" if "MANUAL_REVIEW_REQUIRED" in categories else "VALID"
    return DraftValidationResult(
        status=status, ready_for_submission=status == "VALID",
        completeness={"mandatory_supplied": sum(bool(values.get(x)) for x in policy["mandatory_fields"]), "mandatory_total": len(policy["mandatory_fields"]), "recommended_supplied": sum(bool(values.get(x)) for x in policy["recommended_fields"]), "recommended_total": len(policy["recommended_fields"])},
        extracted_change=change, issues=issues, missing_mandatory=missing,
        clarification_questions=[f"What is the {field.replace('_', ' ')}?" for field in missing] + [f"Please clarify: {item.reason}" for item in issues if item.category in {"AMBIGUOUS", "INCONSISTENT"}],
        expected_operations=change.expected_operations,
    )


def _resource_parts(resource: str) -> tuple[str, str]:
    sub = re.search(r"/subscriptions/([^/]+)", resource, re.I)
    group = re.search(r"/resourceGroups/([^/]+)", resource, re.I)
    if resource.startswith("arn:"):
        bits = resource.split(":", 5)
        return (bits[4] if len(bits) > 4 else "", "")
    return (sub.group(1) if sub else "", group.group(1) if group else "")


def deterministic_draft(change: ExtractedChange) -> ImprovedChangeDraft:
    resource = change.target_resources[0] if change.target_resources else ""
    subscription, group = _resource_parts(resource)
    zones = [m.group(1) for value in (change.start, change.end) if (m := re.search(r"(Z|[+-]\d{2}:\d{2})$", value))]
    timezone = change.timezone or (zones[0] if zones and len(set(zones)) == 1 else "")
    return ImprovedChangeDraft(provider=change.provider, change_title=change.title or change.purpose,
        change_number=change.change_id or "", business_justification=change.business_justification,
        environment=change.environment, subscription=change.subscription or subscription,
        resource_group=change.resource_group or group, resource_name_or_id=resource or change.resource_name,
        implementer=change.implementer, change_start=change.start, change_end=change.end, timezone=timezone,
        required_role="; ".join(change.role_requirements), required_access_scope="; ".join(change.scope_requirements),
        implementation_steps=list(change.implementation_tasks), validation_plan=list(change.validation_steps),
        rollback_plan=change.rollback_plan, expected_outcome=change.expected_outcome, risk_and_impact=change.risk_impact,
        expected_operations=list(change.expected_operations), source_mode=change.source_mode,
        source_text=change.raw_text, source_conflicts=list(change.conflicts))


def draft_to_extracted(draft: ImprovedChangeDraft) -> ExtractedChange:
    resource = draft.resource_name_or_id.strip()
    return ExtractedChange(change_id=draft.change_number or None, provider=draft.provider, source_mode=draft.source_mode,
        title=draft.change_title, purpose=draft.change_title, business_justification=draft.business_justification,
        environment=draft.environment, subscription=draft.subscription, resource_group=draft.resource_group,
        resource_name=resource, target_resources=[resource] if resource else [], implementer=draft.implementer,
        implementation_tasks=draft.implementation_steps, start=draft.change_start, end=draft.change_end,
        timezone=draft.timezone, expected_outcome=draft.expected_outcome, validation_steps=draft.validation_plan,
        rollback_plan=draft.rollback_plan, risk_impact=draft.risk_and_impact,
        role_requirements=[draft.required_role] if draft.required_role else [],
        scope_requirements=[draft.required_access_scope] if draft.required_access_scope else [],
        expected_operations=draft.expected_operations, conflicts=draft.source_conflicts, raw_text=draft.source_text)


def servicenow_text(draft: ImprovedChangeDraft) -> str:
    sections = [("CHANGE TITLE", draft.change_title), ("CHANGE NUMBER", draft.change_number),
        ("BUSINESS JUSTIFICATION", draft.business_justification), ("ENVIRONMENT", draft.environment),
        ("SUBSCRIPTION", draft.subscription), ("RESOURCE GROUP", draft.resource_group),
        ("RESOURCE NAME / ID", draft.resource_name_or_id), ("IMPLEMENTER", draft.implementer),
        ("CHANGE START", draft.change_start), ("CHANGE END", draft.change_end), ("TIMEZONE", draft.timezone),
        ("REQUIRED ROLE", draft.required_role), ("REQUIRED ACCESS SCOPE", draft.required_access_scope),
        ("IMPLEMENTATION STEPS", "\n".join(f"{i}. {x}" for i, x in enumerate(draft.implementation_steps, 1))),
        ("VALIDATION PLAN", "\n".join(f"{i}. {x}" for i, x in enumerate(draft.validation_plan, 1))),
        ("ROLLBACK PLAN", draft.rollback_plan), ("EXPECTED OUTCOME", draft.expected_outcome),
        ("RISK AND IMPACT", draft.risk_and_impact)]
    return "\n\n".join(f"{label}\n{value}" for label, value in sections)


def stage1_demo_text(variant: str) -> str:
    resource = "/subscriptions/00000000-1111-2222-3333-444444444444/resourceGroups/rg-arca-prod/providers/Microsoft.Storage/storageAccounts/starchprod01"
    lines = ["Purpose: Rotate the application storage configuration", "Business Justification: Maintain the approved security baseline",
        "Environment: production", "Implementer: engineer01@example.invalid", f"Target Resource: {resource}",
        "Implementation Tasks: Update the resource configuration; verify the deployment completes",
        "Start: 2026-10-22T10:00:00Z", "End: 2026-10-22T11:00:00Z",
        "Expected Outcome: The approved configuration is active", "Post-change Validation: Confirm service health; test application access",
        "Rollback Plan: Restore the previous configuration from the captured baseline",
        "Risk and Impact: Moderate risk with a five minute application interruption", "Role Requirements: Contributor",
        "Scope Requirements: Resource scope only", f"Expected Operations: Microsoft.Storage/storageAccounts/write @ {resource}"]
    if variant == "missing_implementer": lines = [x for x in lines if not x.startswith("Implementer:")]
    if variant == "missing_resource": lines = [x for x in lines if not x.startswith(("Target Resource:", "Expected Operations:"))]
    if variant == "reversed_window": lines = ["End: 2026-10-22T09:00:00Z" if x.startswith("End:") else x for x in lines]
    if variant == "ambiguous_task": lines = ["Implementation Tasks: Update as needed" if x.startswith("Implementation Tasks:") else x for x in lines]
    return "\n".join(lines)


def scenarios(provider: str) -> list[dict[str, Any]]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return [{"scenario_id": x["scenario_id"], "name": x["name"], "provider": provider,
             "expected_outcome": x["expected_outcome"], "explanation": x["explanation"],
             "text": stage1_demo_text(x["inputs"]["variant"])}
            for x in catalog if x["feature"] == "stage1" and x.get("provider", "azure") == provider]


def improve(change: ExtractedChange, mode: str, gateway: LlmGateway | None = None) -> dict[str, Any]:
    started = perf_counter()
    baseline = deterministic_draft(change)
    result = {"draft": baseline, "validation": validate_draft(change), "copy_text": servicenow_text(baseline),
              "llm_invoked": False, "llm_status": "not_invoked", "model_identifier": None,
              "disclosure": "Draft restructured from explicit source information; no AI refinement was requested."}
    usage = TokenUsage()
    provider_name = None
    if mode == "llm_assisted":
        client = gateway or LlmGateway()
        capability = client.capability()
        provider_name = str(capability.get("provider") or "") or None
        result["model_identifier"] = str(capability.get("model_identifier") or "") or None
        if capability.get("available"):
            try:
                refined, model, usage = client.improve_draft(baseline.model_dump())
                updates = {}
                for field in ("change_title", "business_justification", "implementation_steps", "validation_plan", "rollback_plan", "expected_outcome", "risk_and_impact"):
                    original, candidate = getattr(baseline, field), getattr(refined, field)
                    updates[field] = candidate if original not in ("", []) and candidate not in ("", []) else original
                result.update(draft=baseline.model_copy(update=updates), llm_invoked=True, llm_status="completed", model_identifier=model,
                              disclosure="Advisory AI refined source-supported prose; technical facts and validation status remain deterministic.")
            except LlmGatewayError as exc:
                usage = exc.usage
                result.update(llm_invoked=bool(usage.calls), llm_status=exc.status,
                              disclosure="AI refinement failed; the editable draft retains explicit source information only.")
        else:
            result["llm_status"] = str(capability.get("status") or "unavailable")
            result["disclosure"] = "AI refinement was unavailable; the editable draft retains explicit source information only."
    result["copy_text"] = servicenow_text(result["draft"])
    result["execution_metrics"] = execution_metrics(agent_id="A1", execution_mode=mode, provider=provider_name,
        model=result["model_identifier"], status=result["llm_status"], usage=usage, started_at=started, environment=change.provider)
    return result
