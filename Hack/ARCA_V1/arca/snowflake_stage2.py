"""Deterministic Snowflake Stage 2 controls over synthetic grant evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatchcase
import re
from typing import Any

from .time_filters import parse_utc

ROLE_PATTERN = re.compile(r"required\s+snowflake\s+role\s*:\s*([A-Z][A-Z0-9_$]*)", re.IGNORECASE)


def validate_change_window(change: dict, evaluation_time: datetime | None = None) -> dict:
    """Check whether an approved change is active at a timezone-aware UTC instant."""
    evaluated = (evaluation_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    state = str(change.get("state") or "").strip().lower()
    start_raw, end_raw = change.get("start"), change.get("end")
    base = {"approved_start": start_raw, "approved_end": end_raw,
            "evaluation_timestamp": evaluated.isoformat().replace("+00:00", "Z")}
    if not state:
        return {**base, "status": "NEED_MORE_INFO", "explanation": "Approval state is missing."}
    if state != "approved":
        return {**base, "status": "NOT_APPROVED", "explanation": f"Change state is {state}; approved state is required."}
    if not start_raw or not end_raw:
        missing = [name for name, value in (("start", start_raw), ("end", end_raw)) if not value]
        return {**base, "status": "NEED_MORE_INFO", "explanation": f"Approved {' and '.join(missing)} timestamp information is missing."}
    try:
        start, end = parse_utc(start_raw), parse_utc(end_raw)
    except (TypeError, ValueError):
        return {**base, "status": "NEED_MORE_INFO", "explanation": "Approved window contains an invalid or timezone-free timestamp."}
    if start >= end:
        return {**base, "status": "NEED_MORE_INFO", "explanation": "Approved change window is structurally invalid."}
    if evaluated < start:
        return {**base, "status": "NOT_STARTED", "explanation": "Evaluation time is before the approved start."}
    if evaluated >= end:
        return {**base, "status": "EXPIRED", "explanation": "Evaluation time is at or after the approved end."}
    return {**base, "status": "ACTIVE", "explanation": "Change is approved and the evaluation time is within the active window."}


def _description_role(change: dict) -> str:
    match = ROLE_PATTERN.search(change.get("description") or "")
    return match.group(1).upper() if match else ""


def _object_type(operation: str) -> str:
    words = operation.upper().split()
    return words[-1] if words and words[-1] in {"DATABASE", "SCHEMA", "TABLE", "WAREHOUSE", "USER", "ROLE"} else ""


def _parent(target: str, levels: int = 1) -> str:
    parts = target.split(".")
    return ".".join(parts[:-levels]) if len(parts) > levels else ""


def _requirements(operation: str, target: str, account: str) -> list[dict] | None:
    op = " ".join(operation.upper().split())
    object_type = _object_type(op)
    if op == "CREATE DATABASE": return [{"privilege": "CREATE DATABASE", "object_type": "ACCOUNT", "object_name": account}]
    if op == "ALTER DATABASE": return [{"privilege": "OWNERSHIP", "object_type": "DATABASE", "object_name": target}]
    if op == "CREATE SCHEMA":
        database = _parent(target)
        return [{"privilege": "USAGE", "object_type": "DATABASE", "object_name": database},
                {"privilege": "CREATE SCHEMA", "object_type": "DATABASE", "object_name": database}]
    if op == "ALTER SCHEMA": return [{"privilege": "OWNERSHIP", "object_type": "SCHEMA", "object_name": target}]
    if op == "CREATE TABLE":
        schema, database = _parent(target), _parent(target, 2)
        return [{"privilege": "USAGE", "object_type": "DATABASE", "object_name": database},
                {"privilege": "USAGE", "object_type": "SCHEMA", "object_name": schema},
                {"privilege": "CREATE TABLE", "object_type": "SCHEMA", "object_name": schema}]
    if op == "ALTER TABLE": return [{"privilege": "OWNERSHIP", "object_type": "TABLE", "object_name": target}]
    if op in {"GRANT ROLE", "REVOKE ROLE"} or op.startswith("GRANT ") or op.startswith("REVOKE "):
        return [{"privilege": "MANAGE GRANTS", "object_type": "ACCOUNT", "object_name": account}]
    if op == "CREATE USER": return [{"privilege": "CREATE USER", "object_type": "ACCOUNT", "object_name": account}]
    if op == "ALTER USER": return [{"privilege": "OWNERSHIP", "object_type": "USER", "object_name": target.removeprefix("USER:")}]
    if op == "CREATE WAREHOUSE": return [{"privilege": "CREATE WAREHOUSE", "object_type": "ACCOUNT", "object_name": account}]
    if op == "ALTER WAREHOUSE": return [{"privilege": "MODIFY", "object_type": "WAREHOUSE", "object_name": target}]
    if object_type: return None
    return None


def _inherited_roles(role: str, role_grants: list[dict]) -> tuple[set[str], list[str]]:
    roles, evidence, pending = {role}, [], [role]
    while pending:
        grantee = pending.pop()
        for grant in role_grants:
            if grant.get("grantee_role", "").upper() == grantee:
                inherited = grant.get("granted_role", "").upper()
                if inherited and inherited not in roles:
                    roles.add(inherited); pending.append(inherited); evidence.append(grant.get("grant_id", ""))
    return roles, evidence


def _effective_grants(role: str, catalog: dict) -> tuple[list[dict], list[str]]:
    roles, evidence = _inherited_roles(role, catalog.get("role_grants", []))
    grants = [grant for grant in catalog.get("object_grants", []) if grant.get("grantee_role", "").upper() in roles]
    return grants, evidence + [grant.get("grant_id", "") for grant in grants]


def _grant_covers(grant: dict, required: dict) -> bool:
    if grant.get("object_type", "").upper() != required["object_type"]: return False
    if not fnmatchcase(required["object_name"].upper(), grant.get("object_name", "").upper()): return False
    privilege = grant.get("privilege", "").upper()
    return privilege == required["privilege"] or (privilege == "OWNERSHIP" and required["object_type"] != "ACCOUNT")


def _coverage(grants: list[dict], requirements: list[dict]) -> tuple[list[dict], list[dict]]:
    covered, missing = [], []
    for requirement in requirements:
        matches = [grant for grant in grants if _grant_covers(grant, requirement)]
        (covered if matches else missing).append({**requirement, "grant_ids": [x["grant_id"] for x in matches]})
    return covered, missing


def _grant_signatures(grants: list[dict]) -> set[tuple[str, str, str]]:
    return {(g.get("privilege", ""), g.get("object_type", ""), g.get("object_name", "")) for g in grants}


def assess_requested_role(change: dict, catalog: dict) -> dict:
    """Compare structured change intent with effective privileges from grant evidence."""
    structured = str(change.get("snowflake_context", {}).get("requested_role") or "").strip().upper()
    described = _description_role(change)
    expected = change.get("expected") or []
    base = {"change_id": change.get("change_id"), "requested_role": structured,
            "description_role": described, "intended_operations": expected}
    if structured and described and structured != described:
        return {**base, "status": "MANUAL_REVIEW", "recommended_role": None,
                "required_privileges": [], "effective_privileges": [], "evidence": [],
                "explanation": "Structured requested role conflicts with the role stated in the description."}
    requested = structured or described
    base["requested_role"] = requested
    if not requested:
        return {**base, "status": "NEED_MORE_INFO", "recommended_role": None,
                "required_privileges": [], "effective_privileges": [], "evidence": [],
                "explanation": "Requested Snowflake role is missing."}
    roles = {item.get("role_name", "").upper(): item for item in catalog.get("roles", [])}
    if requested not in roles:
        return {**base, "status": "NEED_MORE_INFO", "recommended_role": None,
                "required_privileges": [], "effective_privileges": [], "evidence": [],
                "explanation": "Requested role is not present in the synthetic role catalog."}
    if not expected:
        return {**base, "status": "NEED_MORE_INFO", "recommended_role": None,
                "required_privileges": [], "effective_privileges": [], "evidence": [],
                "explanation": "Expected Snowflake operations are missing."}
    account = change.get("snowflake_context", {}).get("account") or ""
    requirements = []
    for item in expected:
        operation, target = item.get("operation", ""), item.get("resource_id", "")
        if not operation or not target:
            return {**base, "status": "NEED_MORE_INFO", "recommended_role": None,
                    "required_privileges": requirements, "effective_privileges": [], "evidence": [],
                    "explanation": "Operation or target object evidence is missing."}
        required = _requirements(operation, target, account)
        if required is None:
            return {**base, "status": "MANUAL_REVIEW", "recommended_role": None,
                    "required_privileges": requirements, "effective_privileges": [], "evidence": [],
                    "explanation": f"Privilege requirements for {operation} are not supported by the catalog."}
        requirements.extend(required)
    requirements = [dict(item) for item in {tuple(sorted(x.items())) for x in requirements}]
    grants, evidence = _effective_grants(requested, catalog)
    if not grants:
        return {**base, "status": "MANUAL_REVIEW", "recommended_role": None,
                "required_privileges": requirements, "effective_privileges": [], "evidence": evidence,
                "explanation": "The role exists, but privilege grant evidence is unavailable."}
    covered, missing = _coverage(grants, requirements)
    effective = [{key: grant.get(key) for key in ("grant_id", "grantee_role", "privilege", "object_type", "object_name")} for grant in grants]
    if missing:
        return {**base, "status": "INSUFFICIENT_PRIVILEGES", "recommended_role": None,
                "required_privileges": requirements, "effective_privileges": effective, "missing_privileges": missing,
                "evidence": list(dict.fromkeys(evidence)), "explanation": "Effective grant evidence does not cover every required privilege and target."}
    requested_signatures = _grant_signatures(grants)
    candidates = []
    for role_name in sorted(roles):
        if role_name == requested: continue
        candidate_grants, candidate_evidence = _effective_grants(role_name, catalog)
        _, candidate_missing = _coverage(candidate_grants, requirements)
        signatures = _grant_signatures(candidate_grants)
        if not candidate_missing and signatures < requested_signatures:
            candidates.append((len(signatures), role_name, candidate_evidence))
    if candidates:
        _, role_name, candidate_evidence = min(candidates)
        return {**base, "status": "OVERPRIVILEGED", "recommended_role": role_name,
                "required_privileges": requirements, "effective_privileges": effective,
                "evidence": list(dict.fromkeys(evidence + candidate_evidence)),
                "explanation": "A narrower catalog role has evidence for all required privileges on the intended targets."}
    return {**base, "status": "APPROPRIATE", "recommended_role": None,
            "required_privileges": requirements, "effective_privileges": effective,
            "evidence": list(dict.fromkeys(evidence)),
            "explanation": "The requested role has evidenced coverage and no narrower eligible catalog role was established."}


def assess_stage2(change: dict, catalog: dict, evaluation_time: datetime | None = None) -> dict:
    window = validate_change_window(change, evaluation_time)
    role = assess_requested_role(change, catalog)
    if window["status"] == "NEED_MORE_INFO" or role["status"] == "NEED_MORE_INFO": overall = "NEED_MORE_INFO"
    elif window["status"] != "ACTIVE": overall = "NOT_AUTHORIZED"
    elif role["status"] == "OVERPRIVILEGED": overall = "RECOMMEND_LESSER_ROLE"
    elif role["status"] == "INSUFFICIENT_PRIVILEGES": overall = "INSUFFICIENT_ACCESS"
    elif role["status"] == "MANUAL_REVIEW": overall = "MANUAL_REVIEW_REQUIRED"
    else: overall = "APPROPRIATE"
    return {"status": overall, "provider": "snowflake", "change_id": change.get("change_id"),
            "window_assessment": window, "role_assessment": role,
            "evidence": list(dict.fromkeys(role.get("evidence", []))),
            "warning": "ARCA recommendation only; no Snowflake role was granted and no SQL was executed."}


def aggregate_unified_status(change_quality: dict, window: dict, role: dict) -> str:
    """Apply the documented fail-closed policy while retaining every component result."""
    if change_quality.get("status") != "VALID" or window.get("status") == "NEED_MORE_INFO" or role.get("status") == "NEED_MORE_INFO":
        return "NEEDS_INFO"
    if window.get("status") != "ACTIVE" or role.get("status") == "INSUFFICIENT_PRIVILEGES":
        return "FAIL"
    if role.get("status") == "OVERPRIVILEGED":
        return "OVERPRIVILEGED"
    if role.get("status") == "MANUAL_REVIEW":
        return "MANUAL_REVIEW"
    return "PASS"


def assess_unified_stage1(change: dict, catalog: dict, change_quality: dict,
                          evaluation_time: datetime | None = None) -> dict:
    """Combine change quality, window, and access checks without collapsing findings."""
    access = assess_stage2(change, catalog, evaluation_time)
    window, role = access["window_assessment"], access["role_assessment"]
    result = {
        "status": aggregate_unified_status(change_quality, window, role),
        "provider": "snowflake", "change_id": change.get("change_id"),
        "change_quality": change_quality, "window_assessment": window,
        "role_assessment": role, "evidence": access.get("evidence", []),
        "warning": access["warning"],
    }
    return normalize_unified_result(result)


UNIFIED_RESULT_SCHEMA_VERSION = 1


def normalize_unified_result(result: dict) -> dict:
    """Return the canonical provider/UI contract without masking incomplete results."""
    if not isinstance(result, dict):
        raise ValueError("Snowflake unified validation must return a dictionary")
    normalized = dict(result)
    status = normalized.get("overall_status") or normalized.get("status")
    normalized["status"] = status
    normalized["overall_status"] = status
    normalized["schema_version"] = UNIFIED_RESULT_SCHEMA_VERSION
    for section_name in ("change_quality", "window_assessment", "role_assessment"):
        section = normalized.get(section_name)
        if isinstance(section, dict):
            section = dict(section)
            section.setdefault("evidence", [])
            if section_name == "change_quality":
                section.setdefault("findings", list(section.get("issues", [])))
            elif section.get("status") in {"ACTIVE", "APPROPRIATE", "VALID"}:
                section.setdefault("findings", [])
            else:
                explanation = section.get("explanation")
                section.setdefault("findings", [explanation] if explanation else [])
            normalized[section_name] = section
    return validate_unified_result_contract(normalized)


def validate_unified_result_contract(result: dict) -> dict:
    """Fail explicitly when the provider/UI mandatory result contract is incompatible."""
    required = {"status", "overall_status", "change_quality", "window_assessment", "role_assessment"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"Snowflake unified validation result is missing mandatory sections: {sorted(missing)}")
    if result["status"] != result["overall_status"]:
        raise ValueError("Snowflake unified validation status and overall_status must match")
    for section in ("change_quality", "window_assessment", "role_assessment"):
        value = result[section]
        if not isinstance(value, dict) or not value.get("status"):
            raise ValueError(f"Snowflake unified validation section {section} must contain a status")
        if not isinstance(value.get("evidence"), list) or not isinstance(value.get("findings"), list):
            raise ValueError(f"Snowflake unified validation section {section} must contain evidence and findings lists")
    return result


def presentation_findings(change: dict, result: dict) -> dict[str, list[dict]]:
    """Project actual Stage 2 evidence into UI finding groups without re-evaluating it."""
    window = result["window_assessment"]
    role = result["role_assessment"]
    groups: dict[str, list[dict]] = {
        "Missing Information": [], "Validation Issues": [], "Access Risk Findings": []
    }

    def add(group: str, field: str, current: Any, expected: str, problem: str,
            recommendation: str, stage: str = "Stage 2") -> None:
        groups[group].append({
            "field": field, "current_value": current if current not in (None, "") else "Not provided",
            "expected": expected, "problem": problem, "recommendation": recommendation,
            "validation_stage": stage,
        })

    window_status = window.get("status")
    if window_status == "NEED_MORE_INFO":
        explanation = window.get("explanation", "Change-window evidence is incomplete.")
        field = "Approved Change Window"
        current = f"{window.get('approved_start') or 'Not provided'} to {window.get('approved_end') or 'Not provided'}"
        if "state" in explanation.lower(): field, current = "Approval Status", change.get("state")
        add("Missing Information", field, current, "An approved, valid start/end window with explicit timezone.",
            explanation, "Correct the approval state or supply valid timezone-aware window timestamps.")
    elif window_status in {"NOT_STARTED", "EXPIRED", "NOT_APPROVED"}:
        expected = "Evaluation time must be within an approved, active maintenance window."
        recommendation = ("Wait until the approved maintenance window begins."
                          if window_status == "NOT_STARTED" else
                          "Obtain a new approved maintenance window before executing the change."
                          if window_status == "EXPIRED" else
                          "Obtain change approval before requesting or using access.")
        add("Validation Issues", "Change Window" if window_status != "NOT_APPROVED" else "Approval Status",
            window.get("evaluation_timestamp") if window_status != "NOT_APPROVED" else change.get("state"),
            expected, window.get("explanation", "The maintenance window is not active."), recommendation)

    role_status = role.get("status")
    if role_status == "NEED_MORE_INFO":
        explanation = role.get("explanation", "Role evidence is incomplete.")
        field = "Requested Snowflake Role"
        current = role.get("requested_role")
        expected = "A catalogued Snowflake role required to perform the documented operation."
        if "operation" in explanation.lower():
            field, current, expected = "Expected Snowflake Operation", role.get("intended_operations"), "At least one explicit operation and target object."
        add("Missing Information", field, current, expected, explanation,
            "Specify supported structured metadata and ensure the role exists in the role catalog.")
    elif role_status == "OVERPRIVILEGED":
        add("Access Risk Findings", "Requested Snowflake Role", role.get("requested_role"),
            f"The narrowest evidenced role that covers the required privileges: {role.get('recommended_role')}",
            role.get("explanation", "The requested role is broader than required."),
            f"Request {role.get('recommended_role')} instead of {role.get('requested_role')}.")
    elif role_status == "INSUFFICIENT_PRIVILEGES":
        add("Access Risk Findings", "Role Privilege Coverage", role.get("requested_role"),
            "Effective grants must cover every required privilege on each intended object.",
            role.get("explanation", "Required privileges are not fully covered."),
            "Request an evidence-backed role or correct the documented target scope.")
    elif role_status == "MANUAL_REVIEW":
        conflict = bool(role.get("description_role") and role.get("description_role") != role.get("requested_role"))
        add("Validation Issues" if conflict else "Access Risk Findings",
            "Requested Snowflake Role" if conflict else "Role Privilege Evidence",
            role.get("requested_role"), "Consistent role evidence with complete catalogued grants.",
            role.get("explanation", "A deterministic assessment is not possible."),
            "Resolve conflicting role values." if conflict else "Complete the grant evidence or obtain manual security review.")
    return groups
