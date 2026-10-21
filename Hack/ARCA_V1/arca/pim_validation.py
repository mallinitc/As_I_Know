"""Independent deterministic Azure PIM parsing, lookup, and assessment."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, Field
from .llm_provider import configured_provider, get_llm_provider

POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "pim_validation_policy.json"


class ParsedPIMRecord(BaseModel):
    pim_request_id: str = ""
    change_id: str = ""
    principal_id: str = ""
    principal_name: str = ""
    role_definition_id: str = ""
    role_name: str = ""
    scope: str = ""
    justification: str = ""
    requested_start: str = ""
    requested_end: str = ""
    request_status: str = ""
    activation_status: str = ""
    evidence_id: str = ""
    raw: dict | str = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    ambiguous: list[str] = Field(default_factory=list)
    reference_source: str = ""


class PIMAssessment(BaseModel):
    overall_assessment: Literal["APPROVE_RECOMMENDED", "RECOMMEND_LESSER_ROLE", "OVERPRIVILEGED", "INSUFFICIENT_ACCESS", "NEED_MORE_INFO", "MANUAL_REVIEW_REQUIRED"]
    change_id: str = ""
    pim_request_id: str = ""
    request_status: str = ""
    activation_status: str = ""
    principal_match: dict = Field(default_factory=dict)
    role_assessment: dict = Field(default_factory=dict)
    scope_assessment: dict = Field(default_factory=dict)
    duration_assessment: dict = Field(default_factory=dict)
    justification_assessment: dict = Field(default_factory=dict)
    recommended_role: str = ""
    recommended_scope: str = ""
    recommended_duration: str = ""
    supporting_evidence_references: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    human_review_requirements: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    disclaimer: str = "ARCA recommendation only; no PIM approval or rejection was executed."


class CombinedPIMAssessment(BaseModel):
    overall_assessment: Literal["APPROVE_RECOMMENDED", "RECOMMEND_LESSER_ROLE", "OVERPRIVILEGED", "INSUFFICIENT_ACCESS", "NEED_MORE_INFO", "MANUAL_REVIEW_REQUIRED"]
    risk_classification: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    change_id: str
    change_summary: dict = Field(default_factory=dict)
    individual_assessments: list[PIMAssessment] = Field(default_factory=list)
    task_coverage: list[dict] = Field(default_factory=list)
    principal_coverage: dict[str, list[str]] = Field(default_factory=dict)
    missing_tasks: list[dict] = Field(default_factory=list)
    excessive_permissions: list[str] = Field(default_factory=list)
    scope_duration_concerns: list[str] = Field(default_factory=list)
    potential_redundancies: list[str] = Field(default_factory=list)
    overlapping_windows: list[dict] = Field(default_factory=list)
    recommended_corrections: list[str] = Field(default_factory=list)
    supporting_evidence_references: list[str] = Field(default_factory=list)
    human_review_requirements: list[str] = Field(default_factory=list)
    disclaimer: str = "ARCA recommendation only; privileges were not combined across different principals and no PIM action was executed."


def load_pim_policy(path: Path | None = None) -> dict:
    return json.loads((path or POLICY_PATH).read_text(encoding="utf-8"))


def _change_reference(*values: str) -> str:
    text = " ".join(value or "" for value in values)
    match = re.search(r"\bCHG(?:-[A-Z]+-\d+|\d+)\b", text, re.I)
    return match.group(0).upper() if match else ""


def _change_references(value: str) -> list[str]:
    return list(dict.fromkeys(match.upper() for match in re.findall(r"\bCHG(?:-[A-Z]+-\d+|\d+)\b", value or "", re.I)))


def _normalize(raw: dict) -> dict:
    schedule = raw.get("schedule") or {}
    ticket = raw.get("ticket") or {}
    return {
        "pim_request_id": raw.get("pim_request_id") or raw.get("request_id", ""),
        "change_id": ticket.get("number") or raw.get("change_id") or _change_reference(raw.get("justification", "")),
        "principal_id": raw.get("principal_id") or raw.get("object_id", ""),
        "principal_name": raw.get("principal_name") or raw.get("upn") or raw.get("user_principal_name", ""),
        "role_definition_id": raw.get("role_definition_id", ""), "role_name": raw.get("role_name") or raw.get("role", ""),
        "scope": raw.get("scope", ""), "justification": raw.get("justification", ""),
        "requested_start": raw.get("requested_start") or raw.get("start") or schedule.get("start", ""),
        "requested_end": raw.get("requested_end") or raw.get("end") or schedule.get("end", ""),
        "request_status": raw.get("request_status") or raw.get("status", ""),
        "activation_status": raw.get("activation_status", ""),
        "evidence_id": raw.get("pim_request_id") or raw.get("request_id", ""), "raw": raw,
        "reference_source": "ticket" if ticket.get("number") else "structured" if raw.get("change_id") else "justification" if _change_reference(raw.get("justification", "")) else "",
    }


LABELS = {"pim request id": "pim_request_id", "request id": "pim_request_id", "change number": "change_id",
          "change id": "change_id", "principal id": "principal_id", "object id": "principal_id",
          "upn": "principal_name", "principal": "principal_name", "role": "role_name", "role name": "role_name",
          "role definition id": "role_definition_id", "scope": "scope", "justification": "justification",
          "requested start": "requested_start", "start": "requested_start", "requested end": "requested_end",
          "end": "requested_end", "request status": "request_status", "status": "request_status",
          "activation status": "activation_status"}
REQUIRED = ("principal", "role_name", "scope", "justification", "requested_start", "requested_end", "request_status")


def parse_pim_record(text: str, model_mode: str | None = None) -> ParsedPIMRecord:
    """Parse JSON or explicit human-readable labels without semantic invention."""
    try:
        raw = json.loads(text)
        if not isinstance(raw, dict): raise ValueError("PIM JSON must be an object")
        values = _normalize(raw)
    except (json.JSONDecodeError, ValueError):
        values, seen = {"raw": text}, {}
        for line in text.splitlines():
            match = re.match(r"^\s*([^:]+):\s*(.*?)\s*$", line)
            if not match: continue
            key = LABELS.get(match.group(1).strip().lower())
            if key:
                seen.setdefault(key, []).append(match.group(2))
                values[key] = match.group(2)
        values["change_id"] = values.get("change_id") or _change_reference(values.get("justification", ""))
        values["ambiguous"] = [f"Multiple values supplied for {key}" for key, items in seen.items() if len(set(items)) > 1]
        selected = configured_provider(model_mode)
        if selected != "mock" and (not values.get("justification") or len(values) <= 3):
            instructions = (
                "Extract only explicitly stated PIM request facts. Never invent missing values. Preserve principal IDs, "
                "UPNs, roles, scopes, change IDs, and timestamps exactly. This is interpretation only: do not assess, "
                "approve, reject, or activate access. Leave unknown fields empty."
            )
            parsed = get_llm_provider(selected).parse(instructions, text, ParsedPIMRecord)
            values = parsed.model_dump()
            values["raw"] = text
    principal = values.get("principal_id") or values.get("principal_name")
    missing = [name for name in REQUIRED if not (principal if name == "principal" else values.get(name))]
    if not values.get("change_id"): missing.append("change_id")
    values["missing"] = missing
    return ParsedPIMRecord.model_validate(values)


def record_from_evidence(raw: dict) -> ParsedPIMRecord:
    values = _normalize(raw)
    refs = _change_references(raw.get("justification", ""))
    if len(refs) > 1: values["ambiguous"] = ["Multiple change references appear in the justification."]
    elif values.get("reference_source") == "ticket" and refs and values["change_id"].upper() not in refs:
        values["ambiguous"] = [f"Structured ticket {values['change_id']} conflicts with justification reference {refs[0]}." ]
    values["missing"] = [name for name in REQUIRED if not ((values.get("principal_id") or values.get("principal_name")) if name == "principal" else values.get(name))]
    return ParsedPIMRecord.model_validate(values)


def parse_pim_records(text: str, model_mode: str | None = None) -> list[ParsedPIMRecord]:
    """Parse one or more JSON records; human-readable input remains one explicit record."""
    try:
        payload = json.loads(text)
        if isinstance(payload, list): return [record_from_evidence(item) for item in payload if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    return [parse_pim_record(text, model_mode=model_mode)]


def find_pim_requests_by_change(bundle: dict, change_id: str) -> list[dict]:
    """Prefer structured tickets and use justification references only when structured linkage is absent."""
    target = change_id.strip().upper()
    output = []
    for request in bundle.get("access_requests", []):
        ticket = (request.get("ticket") or {}).get("number", "").upper()
        structured = ticket or request.get("change_id", "").upper()
        refs = _change_references(request.get("justification", ""))
        if structured:
            if structured != target: continue
            source = "ticket" if ticket else "structured"
        else:
            if target not in refs: continue
            source = "justification"
        item = dict(request)
        item["reference_source"] = source
        item["reference_ambiguities"] = (["Multiple justification change references require review."] if len(refs) > 1 else [])
        if structured and refs and structured not in refs:
            item["reference_ambiguities"].append("Structured change reference conflicts with justification.")
        output.append(item)
    return output


def _at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None: raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def activation_state(request: dict, assignments: list[dict], reference_time: datetime) -> str:
    """Separate request approval from evidenced activation state."""
    ref = reference_time.astimezone(timezone.utc)
    related = [item for item in assignments if item.get("pim_request_id") == request.get("pim_request_id")]
    if any(item.get("assignment_type", "").lower() == "active" and _at(item["valid_from"]) <= ref <= _at(item["valid_to"]) for item in related if item.get("valid_from") and item.get("valid_to")):
        return "Active"
    schedule = request.get("schedule") or {}
    if schedule.get("start") and _at(schedule["start"]) > ref: return "Scheduled"
    if request.get("status", "").lower() in {"pending", "pendingapproval", "submitted"}: return "Pending"
    return "Inactive"


def find_pim_requests(bundle: dict, identity: str, status_filter: str = "All", reference_time: datetime | None = None) -> list[dict]:
    identity = identity.strip().lower()
    ref = reference_time or datetime.now(timezone.utc)
    output = []
    for request in bundle.get("access_requests", []):
        if identity not in {request.get("principal_id", "").lower(), request.get("principal_name", "").lower()}: continue
        item = dict(request)
        item["activation_status"] = activation_state(request, bundle.get("rbac_assignments", []), ref)
        if status_filter != "All" and item["activation_status"] != status_filter: continue
        output.append(item)
    return output


def _actions(role: dict, kind: str = "actions") -> list[str]:
    return [action for permission in role.get("permissions", []) for action in permission.get(kind, [])]


def _covers(operation: str, patterns: list[str]) -> bool:
    return any(fnmatchcase(operation.lower(), pattern.lower()) for pattern in patterns)


def _scope_covers(scope: str, resource: str) -> bool:
    scope, resource = scope.rstrip("/").lower(), resource.rstrip("/").lower()
    return bool(scope) and (scope == resource or resource.startswith(scope + "/"))


def _scope_levels_above(scope: str, resource: str) -> int:
    if not _scope_covers(scope, resource): return 10**6
    left = [part for part in scope.strip("/").split("/") if part]
    right = [part for part in resource.strip("/").split("/") if part]
    return max(0, len(right) - len(left))


def _narrowest_role(required: list[str], roles: list[dict]) -> tuple[str, bool]:
    candidates = []
    for role in roles:
        management = _actions(role, "actions")
        data = _actions(role, "data_actions")
        if required and all(_covers(action, management) for action in required):
            breadth = sum(100 if action == "*" else 1 if "*" in action else 0 for action in management)
            candidates.append((breadth, len(management), role.get("role_name", "")))
        elif required and all(_covers(action, data) for action in required):
            continue  # data-plane permission is not interchangeable with a management-plane operation
    return (min(candidates)[2], False) if candidates else ("Custom role review", True)


def assess_pim(record: ParsedPIMRecord, bundle: dict, manual_change_id: str = "", policy: dict | None = None,
               reference_time: datetime | None = None, intended_expected: list[dict] | None = None) -> PIMAssessment:
    policy = policy or load_pim_policy()
    change_id = record.change_id or manual_change_id.strip().upper()
    change = next((item for item in bundle.get("changes", []) if item.get("change_id", "").upper() == change_id.upper()), None)
    missing = list(record.missing)
    if manual_change_id and "change_id" in missing: missing.remove("change_id")
    findings, reviews, refs = [], list(record.ambiguous), [value for value in (record.evidence_id or record.pim_request_id,) if value]
    if not change:
        if "change_id" not in missing: missing.append("corresponding_change_record")
        return PIMAssessment(overall_assessment="NEED_MORE_INFO", change_id=change_id, pim_request_id=record.pim_request_id,
            request_status=record.request_status, activation_status=record.activation_status, missing_information=missing,
            supporting_evidence_references=refs, findings=["Corresponding change record was not found in available evidence."])
    refs.append(change.get("sys_id") or change.get("change_id"))
    expected = change.get("expected", []) if intended_expected is None else intended_expected
    required_actions = [item.get("operation", "") for item in expected if item.get("operation")]
    required_resources = [item.get("resource_id", "") for item in expected if item.get("resource_id")]
    role = next((item for item in bundle.get("role_definitions", []) if item.get("role_definition_id", "").lower() == record.role_definition_id.lower()), None)
    if not role: role = next((item for item in bundle.get("role_definitions", []) if item.get("role_name", "").lower() == record.role_name.lower()), None)
    actions = _actions(role or {})
    missing_actions = [action for action in required_actions if not _covers(action, actions)]
    recommended_role, custom_review = _narrowest_role(required_actions, bundle.get("role_definitions", []))
    broad_role = record.role_name in policy["broad_roles"] or "*" in actions
    role_result = {"status": "INSUFFICIENT" if missing_actions else "BROADER_THAN_NECESSARY" if broad_role and recommended_role != record.role_name else "SUITABLE",
                   "requested_role": record.role_name, "missing_actions": missing_actions, "required_actions": required_actions}
    uncovered = [resource for resource in required_resources if not _scope_covers(record.scope, resource)]
    scope_too_broad = bool(required_resources) and any(_scope_levels_above(record.scope, resource) > policy["maximum_scope_levels_above_resource"] for resource in required_resources)
    scope_result = {"status": "INSUFFICIENT" if uncovered else "EXCESSIVE" if scope_too_broad else "APPROPRIATE", "requested_scope": record.scope, "uncovered_resources": uncovered}
    try:
        start, end, change_start, change_end = map(_at, (record.requested_start, record.requested_end, change.get("start", ""), change.get("end", "")))
        tolerance = timedelta(minutes=policy["window_tolerance_minutes"])
        duration_ok = start >= change_start - tolerance and end <= change_end + tolerance and start < end
        duration_result = {"status": "COMPLIANT" if duration_ok else "EXCESSIVE_OR_OUTSIDE_WINDOW", "requested_start": record.requested_start, "requested_end": record.requested_end}
    except (ValueError, TypeError):
        duration_ok = False; duration_result = {"status": "UNKNOWN", "requested_start": record.requested_start, "requested_end": record.requested_end}; missing.append("valid_requested_window")
    authorized = change.get("authorized_implementers") or [change.get("implementer", {})]
    implementer = next((item for item in authorized if record.principal_id and item.get("principal_id", "").lower() == record.principal_id.lower()), None)
    if record.principal_id and any(item.get("principal_id") for item in authorized):
        principal_status = "MATCH" if implementer else "MISMATCH"
    elif record.principal_name and any(item.get("principal_name") for item in authorized):
        implementer = next((item for item in authorized if item.get("principal_name", "").strip().lower() == record.principal_name.strip().lower()), None)
        principal_status = "UPN_MATCH_UNCERTAIN" if implementer else "MISMATCH"
        if principal_status == "UPN_MATCH_UNCERTAIN" and policy["escalate_upn_only_match"]: reviews.append("Verify identity using immutable principal ID.")
    else: implementer = {}; principal_status = "UNKNOWN"; missing.append("principal_match_evidence")
    implementer = implementer or {}
    approved = change.get("state", "").lower() in policy["approved_change_states"]
    reference_match = change_id.upper() == change.get("change_id", "").upper()
    justification_match = change.get("change_id", "").lower() in record.justification.lower()
    if not approved: findings.append("CHANGE_NOT_APPROVED")
    if not reference_match: findings.append("CHANGE_REFERENCE_MISMATCH")
    if principal_status == "MISMATCH": findings.append("IMPLEMENTER_MISMATCH")
    if not justification_match: findings.append("JUSTIFICATION_NOT_LINKED_TO_CHANGE")
    if broad_role: findings.append("ROLE_BROADER_THAN_NECESSARY")
    if scope_result["status"] == "EXCESSIVE": findings.append("SCOPE_BROADER_THAN_NECESSARY")
    if not duration_ok: findings.append("ACTIVATION_OUTSIDE_CHANGE_WINDOW")
    if custom_review: reviews.append("No suitable built-in management-plane role was found; review a custom role.")
    activation = record.activation_status
    if not activation and record.pim_request_id:
        raw_request = next((item for item in bundle.get("access_requests", []) if item.get("pim_request_id") == record.pim_request_id), None)
        if raw_request: activation = activation_state(raw_request, bundle.get("rbac_assignments", []), reference_time or datetime.now(timezone.utc))
    if missing: overall = "NEED_MORE_INFO"
    elif missing_actions or uncovered: overall = "INSUFFICIENT_ACCESS"
    elif not approved or not reference_match or principal_status == "MISMATCH" or not justification_match: overall = "MANUAL_REVIEW_REQUIRED"
    elif broad_role and recommended_role != record.role_name: overall = "RECOMMEND_LESSER_ROLE"
    elif scope_result["status"] == "EXCESSIVE" or not duration_ok: overall = "OVERPRIVILEGED"
    elif reviews: overall = "MANUAL_REVIEW_REQUIRED"
    else: overall = "APPROVE_RECOMMENDED"
    assignment_refs = [item.get("assignment_id") for item in bundle.get("rbac_assignments", []) if item.get("pim_request_id") == record.pim_request_id]
    refs.extend(value for value in assignment_refs if value)
    return PIMAssessment(overall_assessment=overall, change_id=change_id, pim_request_id=record.pim_request_id,
        request_status=record.request_status, activation_status=activation,
        principal_match={"status": principal_status, "requested_principal_id": record.principal_id, "requested_upn": record.principal_name,
                         "documented_principal_id": implementer.get("principal_id", ""), "documented_upn": implementer.get("principal_name", "")},
        role_assessment=role_result, scope_assessment=scope_result, duration_assessment=duration_result,
        justification_assessment={"status": "CONSISTENT" if justification_match else "INCONSISTENT", "justification": record.justification},
        recommended_role=recommended_role, recommended_scope=required_resources[0] if len(required_resources) == 1 else "",
        recommended_duration=f"{change.get('start', '')} to {change.get('end', '')}", supporting_evidence_references=refs,
        missing_information=sorted(set(missing)), human_review_requirements=reviews, findings=findings)


def _role_for(record: ParsedPIMRecord, bundle: dict) -> dict:
    return next((role for role in bundle.get("role_definitions", []) if record.role_definition_id and role.get("role_definition_id", "").lower() == record.role_definition_id.lower()), None) or next((role for role in bundle.get("role_definitions", []) if role.get("role_name", "").lower() == record.role_name.lower()), {})


def _task_key(task: dict) -> str:
    return f"{task.get('operation', '')} @ {task.get('resource_id', '')}"


def assess_combined_pim(change_id: str, records: list[ParsedPIMRecord], bundle: dict,
                        reference_time: datetime | None = None) -> CombinedPIMAssessment:
    """Assess aggregate coverage while keeping each principal's privileges separate."""
    change = next((item for item in bundle.get("changes", []) if item.get("change_id", "").upper() == change_id.upper()), None)
    if not change:
        return CombinedPIMAssessment(overall_assessment="NEED_MORE_INFO", risk_classification="HIGH", change_id=change_id,
            recommended_corrections=["Provide a corresponding approved change record."], human_review_requirements=["Change evidence is unavailable."])
    tasks = change.get("expected", [])
    authorized = change.get("authorized_implementers") or [change.get("implementer", {})]
    authorized_ids = {item.get("principal_id", "").lower() for item in authorized if item.get("principal_id")}
    authorized_upns = {item.get("principal_name", "").lower() for item in authorized if item.get("principal_name")}
    per_request_support: dict[str, list[str]] = {}
    individual, excess, concerns, reviews, refs = [], [], [], [], [change.get("sys_id") or change_id]
    for record in records:
        role = _role_for(record, bundle)
        actions = _actions(role)
        supported = [task for task in tasks if _covers(task.get("operation", ""), actions) and _scope_covers(record.scope, task.get("resource_id", ""))]
        per_request_support[record.pim_request_id or record.evidence_id] = [_task_key(task) for task in supported]
        assessment = assess_pim(record, bundle, reference_time=reference_time, intended_expected=supported or tasks)
        individual.append(assessment)
        refs.extend(assessment.supporting_evidence_references)
        if assessment.role_assessment.get("status") == "BROADER_THAN_NECESSARY": excess.append(f"{record.pim_request_id}: role {record.role_name} is broader than supported tasks require.")
        if assessment.scope_assessment.get("status") == "EXCESSIVE": concerns.append(f"{record.pim_request_id}: scope is broader than documented resources.")
        if assessment.duration_assessment.get("status") != "COMPLIANT": concerns.append(f"{record.pim_request_id}: activation window is outside the approved change window.")
        reviews.extend(assessment.human_review_requirements)
    coverage, principal_coverage = [], {}
    for task in tasks:
        supporters = []
        required_principal = task.get("authorized_principal_id", "").lower()
        for record in records:
            principal = (record.principal_id or record.principal_name).lower()
            is_authorized = (record.principal_id.lower() in authorized_ids if record.principal_id else record.principal_name.lower() in authorized_upns)
            if required_principal: is_authorized = record.principal_id.lower() == required_principal
            if is_authorized and _task_key(task) in per_request_support.get(record.pim_request_id or record.evidence_id, []):
                supporters.append({"pim_request_id": record.pim_request_id, "principal": principal})
                principal_coverage.setdefault(principal, []).append(_task_key(task))
        coverage.append({"operation": task.get("operation", ""), "resource_id": task.get("resource_id", ""), "supported_by": supporters, "status": "COVERED" if supporters else "MISSING"})
    missing_tasks = [item for item in coverage if item["status"] == "MISSING"]
    redundancies = []
    for index, left in enumerate(records):
        left_key = left.pim_request_id or left.evidence_id
        for right in records[index + 1:]:
            right_key = right.pim_request_id or right.evidence_id
            same_principal = (left.principal_id and left.principal_id.lower() == right.principal_id.lower()) or (not left.principal_id and left.principal_name.lower() == right.principal_name.lower())
            overlap_tasks = set(per_request_support.get(left_key, [])) & set(per_request_support.get(right_key, []))
            if same_principal and overlap_tasks:
                redundancies.append(f"{left_key} and {right_key} overlap for {', '.join(sorted(overlap_tasks))}.")
    overlaps = []
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            try:
                overlap_start = max(_at(left.requested_start), _at(right.requested_start)); overlap_end = min(_at(left.requested_end), _at(right.requested_end))
                if overlap_start < overlap_end:
                    overlaps.append({"requests": [left.pim_request_id, right.pim_request_id], "principals": [left.principal_id or left.principal_name, right.principal_id or right.principal_name], "start": overlap_start.isoformat(), "end": overlap_end.isoformat(), "same_principal": (left.principal_id or left.principal_name).lower() == (right.principal_id or right.principal_name).lower()})
            except ValueError:
                reviews.append("At least one activation window could not be compared.")
    wrong_refs = [record.pim_request_id for record in records if record.change_id.upper() != change_id.upper() or record.ambiguous]
    if wrong_refs: reviews.append("Resolve conflicting or ambiguous change references: " + ", ".join(wrong_refs))
    corrections = []
    if missing_tasks: corrections.append("Add evidence-backed role and scope coverage for every missing documented task.")
    if excess: corrections.append("Remove or narrow roles that exceed the documented operations.")
    if redundancies: corrections.append("Review overlapping grants for redundancy; do not consolidate roles without confirming task boundaries.")
    if concerns: corrections.append("Constrain resource scopes and activation windows to the approved change intent.")
    if wrong_refs: corrections.append("Correct PIM ticket and justification references before activation.")
    if reviews: overall, risk = "MANUAL_REVIEW_REQUIRED", "HIGH"
    elif missing_tasks: overall, risk = "INSUFFICIENT_ACCESS", "HIGH"
    elif excess or concerns or redundancies: overall, risk = "OVERPRIVILEGED", "HIGH" if excess else "MODERATE"
    else: overall, risk = "APPROVE_RECOMMENDED", "LOW"
    return CombinedPIMAssessment(overall_assessment=overall, risk_classification=risk, change_id=change_id,
        change_summary={"state": change.get("state", ""), "description": change.get("description", ""), "start": change.get("start", ""), "end": change.get("end", ""), "authorized_implementers": authorized, "documented_tasks": tasks},
        individual_assessments=individual, task_coverage=coverage, principal_coverage=principal_coverage,
        missing_tasks=missing_tasks, excessive_permissions=excess, scope_duration_concerns=concerns,
        potential_redundancies=redundancies, overlapping_windows=overlaps,
        recommended_corrections=corrections, supporting_evidence_references=list(dict.fromkeys(ref for ref in refs if ref)),
        human_review_requirements=list(dict.fromkeys(reviews)))
