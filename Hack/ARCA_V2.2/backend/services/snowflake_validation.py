from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatchcase
import re
from typing import Any

from backend.services.timestamps import parse_utc, utc_text


SCHEMA_VERSION = 1
ROLE_REFERENCE = re.compile(
    r"required\s+snowflake\s+role\s*:\s*([A-Z][A-Z0-9_$]*)",
    re.IGNORECASE,
)


def assess_change_quality(change: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    issues: list[dict[str, str]] = []

    def require(field: str, value: Any, reason: str) -> None:
        if value in (None, "", []):
            missing.append(field)
            issues.append({"field": field, "severity": "ERROR", "reason": reason})

    require("change_id", change.get("change_id"), "Change ID is required.")
    require("description", change.get("description"), "Change description is required.")
    require("environment", change.get("environment"), "Environment is required.")
    require("implementer", change.get("implementer"), "Implementer is required.")
    require("start", change.get("start"), "Start timestamp is required.")
    require("end", change.get("end"), "End timestamp is required.")
    expected = change.get("expected") or []
    require("expected", expected, "At least one expected operation is required.")

    if str(change.get("state") or "").strip().lower() != "approved":
        missing.append("approved_state")
        issues.append({"field": "state", "severity": "ERROR", "reason": "Change must be approved before implementation."})

    start = end = None
    if change.get("start"):
        try:
            start = parse_utc(change["start"])
        except (TypeError, ValueError):
            missing.append("valid_start_timestamp")
            issues.append({"field": "start", "severity": "ERROR", "reason": "Start timestamp must be valid ISO 8601 with an explicit timezone."})
    if change.get("end"):
        try:
            end = parse_utc(change["end"])
        except (TypeError, ValueError):
            missing.append("valid_end_timestamp")
            issues.append({"field": "end", "severity": "ERROR", "reason": "End timestamp must be valid ISO 8601 with an explicit timezone."})
    if start and end and start >= end:
        missing.append("valid_change_window")
        issues.append({"field": "change_window", "severity": "ERROR", "reason": "End timestamp must be later than start timestamp."})

    for index, intent in enumerate(expected):
        if not intent.get("operation"):
            missing.append(f"expected[{index}].operation")
            issues.append({"field": "expected", "severity": "ERROR", "reason": f"Expected operation {index + 1} is missing its operation name."})
        if not intent.get("resource_id"):
            missing.append(f"expected[{index}].resource_id")
            issues.append({"field": "expected", "severity": "ERROR", "reason": f"Expected operation {index + 1} is missing its target object."})

    return {
        "status": "VALID" if not issues else "NEEDS_INFO",
        "provider": "snowflake",
        "missing": missing,
        "issues": issues,
        "findings": list(issues),
        "evidence": [],
        "expected": expected,
        "risk": change.get("risk"),
        "snowflake_context": change.get("snowflake_context", {}),
    }


def assess_change_window(change: dict[str, Any], evaluated_at: datetime | None) -> dict[str, Any]:
    evaluated = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    state = str(change.get("state") or "").strip().lower()
    start_raw, end_raw = change.get("start"), change.get("end")
    result: dict[str, Any] = {
        "approved_start": start_raw,
        "approved_end": end_raw,
        "evaluation_timestamp": utc_text(evaluated),
        "evidence": [],
    }
    if not state:
        status, explanation = "NEED_MORE_INFO", "Approval state is missing."
    elif state != "approved":
        status, explanation = "NOT_APPROVED", f"Change state is {state}; approved state is required."
    elif not start_raw or not end_raw:
        absent = [name for name, value in (("start", start_raw), ("end", end_raw)) if not value]
        status, explanation = "NEED_MORE_INFO", f"Approved {' and '.join(absent)} timestamp information is missing."
    else:
        try:
            start, end = parse_utc(start_raw), parse_utc(end_raw)
        except (TypeError, ValueError):
            status, explanation = "NEED_MORE_INFO", "Approved window contains an invalid or timezone-free timestamp."
        else:
            if start >= end:
                status, explanation = "NEED_MORE_INFO", "Approved change window is structurally invalid."
            elif evaluated < start:
                status, explanation = "NOT_STARTED", "Evaluation time is before the approved start."
            elif evaluated >= end:
                status, explanation = "EXPIRED", "Evaluation time is at or after the approved end."
            else:
                status, explanation = "ACTIVE", "Change is approved and the evaluation time is within the active window."
    result.update(status=status, explanation=explanation)
    result["findings"] = [] if status == "ACTIVE" else [explanation]
    return result


def _stated_role(change: dict[str, Any]) -> str:
    match = ROLE_REFERENCE.search(str(change.get("description") or ""))
    return match.group(1).upper() if match else ""


def _parent(target: str, levels: int = 1) -> str:
    parts = target.split(".")
    return ".".join(parts[:-levels]) if len(parts) > levels else ""


def _required_privileges(operation: str, target: str, account: str) -> list[dict[str, str]] | None:
    operation = " ".join(operation.upper().split())
    rules: dict[str, list[dict[str, str]]] = {
        "CREATE DATABASE": [{"privilege": "CREATE DATABASE", "object_type": "ACCOUNT", "object_name": account}],
        "ALTER DATABASE": [{"privilege": "OWNERSHIP", "object_type": "DATABASE", "object_name": target}],
        "ALTER SCHEMA": [{"privilege": "OWNERSHIP", "object_type": "SCHEMA", "object_name": target}],
        "ALTER TABLE": [{"privilege": "OWNERSHIP", "object_type": "TABLE", "object_name": target}],
        "CREATE USER": [{"privilege": "CREATE USER", "object_type": "ACCOUNT", "object_name": account}],
        "ALTER USER": [{"privilege": "OWNERSHIP", "object_type": "USER", "object_name": target.removeprefix("USER:")}],
        "CREATE WAREHOUSE": [{"privilege": "CREATE WAREHOUSE", "object_type": "ACCOUNT", "object_name": account}],
        "ALTER WAREHOUSE": [{"privilege": "MODIFY", "object_type": "WAREHOUSE", "object_name": target}],
    }
    if operation == "CREATE SCHEMA":
        database = _parent(target)
        return [
            {"privilege": "USAGE", "object_type": "DATABASE", "object_name": database},
            {"privilege": "CREATE SCHEMA", "object_type": "DATABASE", "object_name": database},
        ]
    if operation == "CREATE TABLE":
        schema, database = _parent(target), _parent(target, 2)
        return [
            {"privilege": "USAGE", "object_type": "DATABASE", "object_name": database},
            {"privilege": "USAGE", "object_type": "SCHEMA", "object_name": schema},
            {"privilege": "CREATE TABLE", "object_type": "SCHEMA", "object_name": schema},
        ]
    if operation in {"GRANT ROLE", "REVOKE ROLE"} or operation.startswith(("GRANT ", "REVOKE ")):
        return [{"privilege": "MANAGE GRANTS", "object_type": "ACCOUNT", "object_name": account}]
    return rules.get(operation)


def _role_family(role: str, hierarchy: list[dict[str, Any]]) -> tuple[set[str], list[str]]:
    family, pending, evidence = {role}, [role], []
    while pending:
        parent = pending.pop()
        for grant in hierarchy:
            if str(grant.get("grantee_role", "")).upper() != parent:
                continue
            inherited = str(grant.get("granted_role", "")).upper()
            if inherited and inherited not in family:
                family.add(inherited)
                pending.append(inherited)
                if grant.get("grant_id"):
                    evidence.append(grant["grant_id"])
    return family, evidence


def _effective_grants(role: str, catalog: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    family, evidence = _role_family(role, catalog["role_grants"])
    grants = [item for item in catalog["object_grants"] if str(item.get("grantee_role", "")).upper() in family]
    evidence.extend(item["grant_id"] for item in grants if item.get("grant_id"))
    return grants, evidence


def _covers(grant: dict[str, Any], required: dict[str, str]) -> bool:
    if str(grant.get("object_type", "")).upper() != required["object_type"]:
        return False
    if not fnmatchcase(required["object_name"].upper(), str(grant.get("object_name", "")).upper()):
        return False
    actual = str(grant.get("privilege", "")).upper()
    return actual == required["privilege"] or (actual == "OWNERSHIP" and required["object_type"] != "ACCOUNT")


def _coverage(grants: list[dict[str, Any]], requirements: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    covered, missing = [], []
    for requirement in requirements:
        matches = [item for item in grants if _covers(item, requirement)]
        enriched = {**requirement, "grant_ids": [item["grant_id"] for item in matches]}
        (covered if matches else missing).append(enriched)
    return covered, missing


def _role_result(base: dict[str, Any], status: str, explanation: str, **values: Any) -> dict[str, Any]:
    result = {
        **base,
        "status": status,
        "recommended_role": None,
        "required_privileges": [],
        "effective_privileges": [],
        "evidence": [],
        "explanation": explanation,
        **values,
    }
    result["findings"] = [] if status == "APPROPRIATE" else [explanation]
    return result


def assess_role(change: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    context = change.get("snowflake_context") or {}
    structured = str(context.get("requested_role") or "").strip().upper()
    described = _stated_role(change)
    expected = change.get("expected") or []
    base = {
        "change_id": change.get("change_id"),
        "requested_role": structured,
        "description_role": described,
        "intended_operations": expected,
    }
    if structured and described and structured != described:
        return _role_result(base, "MANUAL_REVIEW", "Structured requested role conflicts with the role stated in the description.")
    requested = structured or described
    base["requested_role"] = requested
    if not requested:
        return _role_result(base, "NEED_MORE_INFO", "Requested Snowflake role is missing.")

    roles = {str(item.get("role_name", "")).upper() for item in catalog["roles"]}
    if requested not in roles:
        return _role_result(base, "NEED_MORE_INFO", "Requested role is not present in the synthetic role catalog.")
    if not expected:
        return _role_result(base, "NEED_MORE_INFO", "Expected Snowflake operations are missing.")

    requirements: list[dict[str, str]] = []
    account = str(context.get("account") or "")
    for intent in expected:
        operation, target = str(intent.get("operation") or ""), str(intent.get("resource_id") or "")
        if not operation or not target:
            return _role_result(base, "NEED_MORE_INFO", "Operation or target object evidence is missing.", required_privileges=requirements)
        required = _required_privileges(operation, target, account)
        if required is None:
            return _role_result(
                base,
                "MANUAL_REVIEW",
                f"Privilege requirements for {operation} are not supported by the catalog.",
                required_privileges=requirements,
            )
        for item in required:
            if item not in requirements:
                requirements.append(item)

    grants, evidence = _effective_grants(requested, catalog)
    if not grants:
        return _role_result(
            base,
            "MANUAL_REVIEW",
            "The role exists, but privilege grant evidence is unavailable.",
            required_privileges=requirements,
            evidence=evidence,
        )

    _, missing = _coverage(grants, requirements)
    effective = [
        {key: grant.get(key) for key in ("grant_id", "grantee_role", "privilege", "object_type", "object_name")}
        for grant in grants
    ]
    if missing:
        return _role_result(
            base,
            "INSUFFICIENT_PRIVILEGES",
            "Effective grant evidence does not cover every required privilege and target.",
            required_privileges=requirements,
            effective_privileges=effective,
            missing_privileges=missing,
            evidence=list(dict.fromkeys(evidence)),
        )

    requested_signature = {
        (item.get("privilege"), item.get("object_type"), item.get("object_name")) for item in grants
    }
    narrower: list[tuple[int, str, list[str]]] = []
    for candidate in sorted(roles - {requested}):
        candidate_grants, candidate_evidence = _effective_grants(candidate, catalog)
        _, candidate_missing = _coverage(candidate_grants, requirements)
        signature = {
            (item.get("privilege"), item.get("object_type"), item.get("object_name")) for item in candidate_grants
        }
        if not candidate_missing and signature < requested_signature:
            narrower.append((len(signature), candidate, candidate_evidence))
    if narrower:
        _, recommendation, recommendation_evidence = min(narrower)
        return _role_result(
            base,
            "OVERPRIVILEGED",
            "A narrower catalog role has evidence for all required privileges on the intended targets.",
            recommended_role=recommendation,
            required_privileges=requirements,
            effective_privileges=effective,
            evidence=list(dict.fromkeys(evidence + recommendation_evidence)),
        )
    return _role_result(
        base,
        "APPROPRIATE",
        "The requested role has evidenced coverage and no narrower eligible catalog role was established.",
        required_privileges=requirements,
        effective_privileges=effective,
        evidence=list(dict.fromkeys(evidence)),
    )


def _overall(change_quality: dict[str, Any], window: dict[str, Any], role: dict[str, Any]) -> str:
    if change_quality["status"] != "VALID" or window["status"] == "NEED_MORE_INFO" or role["status"] == "NEED_MORE_INFO":
        return "NEEDS_INFO"
    if window["status"] != "ACTIVE" or role["status"] == "INSUFFICIENT_PRIVILEGES":
        return "FAIL"
    if role["status"] == "OVERPRIVILEGED":
        return "OVERPRIVILEGED"
    if role["status"] == "MANUAL_REVIEW":
        return "MANUAL_REVIEW"
    return "PASS"


def validate_change(change: dict[str, Any], catalog: dict[str, Any], evaluated_at: datetime | None) -> dict[str, Any]:
    quality = assess_change_quality(change)
    window = assess_change_window(change, evaluated_at)
    role = assess_role(change, catalog)
    overall = _overall(quality, window, role)
    missing = list(quality["missing"])
    if role["status"] == "NEED_MORE_INFO" and "requested_role" not in missing:
        missing.append("requested_role_or_privilege_evidence")

    findings: list[dict[str, Any]] = []
    for section_name, section in (
        ("change_quality", quality),
        ("window_assessment", window),
        ("role_assessment", role),
    ):
        for finding in section["findings"]:
            findings.append(
                {"assessment": section_name, **finding}
                if isinstance(finding, dict)
                else {"assessment": section_name, "message": finding}
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "change_id": change.get("change_id"),
        "provider": "snowflake",
        "status": overall,
        "overall_status": overall,
        "change_quality": quality,
        "window_assessment": window,
        "role_assessment": role,
        "missing_information": missing,
        "findings": findings,
        "evidence": list(dict.fromkeys(role["evidence"])),
        "evaluation_timestamp": window["evaluation_timestamp"],
        "warning": "ARCA recommendation only; no Snowflake role was granted and no SQL was executed.",
    }
