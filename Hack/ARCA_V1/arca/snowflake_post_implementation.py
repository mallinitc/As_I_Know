"""Deterministic Snowflake post-implementation validation over synthetic audit evidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Iterable
from uuid import uuid4

from arca.paths import output_dir
from arca.time_filters import parse_utc

UTC = timezone.utc
GOVERNED_OPERATIONS = {
    "CREATE DATABASE", "ALTER DATABASE", "CREATE SCHEMA", "ALTER SCHEMA", "CREATE TABLE",
    "ALTER TABLE", "DROP TABLE", "TRUNCATE TABLE", "GRANT ROLE", "REVOKE ROLE",
    "GRANT SELECT", "REVOKE SELECT", "REVOKE INSERT", "ALTER USER", "CREATE USER",
    "ALTER WAREHOUSE", "CREATE WAREHOUSE", "INSERT", "UPDATE", "DELETE",
}
SEVERITY = {
    "COMPLIANT_EXECUTION": "INFO", "EXECUTED_OUTSIDE_WINDOW": "HIGH",
    "UNAUTHORIZED_IMPLEMENTER": "HIGH", "ROLE_MISMATCH": "HIGH", "UNAPPROVED_OPERATION": "HIGH",
    "WRONG_TARGET_OBJECT": "HIGH", "UNAPPROVED_CHANGE": "HIGH", "FAILED_EXECUTION": "MEDIUM",
    "EXPECTED_OPERATION_MISSING": "MEDIUM", "UNEXPECTED_ADDITIONAL_OPERATION": "HIGH",
    "NO_EXECUTION_EVIDENCE": "MEDIUM", "INSUFFICIENT_AUDIT_EVIDENCE": "REVIEW",
    "POSSIBLE_UNAPPROVED_ACTIVITY": "HIGH", "IDENTITY_NOT_FOUND": "REVIEW",
    "IDENTITY_AMBIGUOUS": "REVIEW",
}
_TAG = re.compile(r"(?:^|[;,\s])ARCA_CHANGE=([A-Z0-9-]+)(?:$|[;,\s])", re.IGNORECASE)


def normalize_name(value: object) -> str:
    return str(value or "").strip().upper()


def resolve_identity(identifier: str, users: list[dict], account_name: str | None = None) -> dict:
    """Resolve only exact user-name, user-id, or email matches; never partial strings."""
    needle = normalize_name(identifier)
    candidates = [user for user in users if needle in {
        normalize_name(user.get("user_name")), normalize_name(user.get("user_id")), normalize_name(user.get("email"))
    } and (not account_name or normalize_name(user.get("account_name")) == normalize_name(account_name))]
    if not candidates:
        return {"status": "NOT_FOUND", "identifier": identifier, "matches": []}
    if len(candidates) > 1:
        return {"status": "AMBIGUOUS", "identifier": identifier, "matches": candidates}
    return {"status": "RESOLVED", "identifier": identifier, "user": candidates[0], "matches": candidates}


def normalize_query(raw: dict, access_by_query: dict[str, dict]) -> dict:
    access = access_by_query.get(raw.get("query_id", ""))
    modified = (access or {}).get("objects_modified") or []
    target = modified[0].get("objectName") if modified else raw.get("target_object")
    tag_match = _TAG.search(str(raw.get("query_tag") or ""))
    return {
        "query_id": raw.get("query_id"), "timestamp": raw.get("start_time"),
        "user": normalize_name(raw.get("user_name")), "role": normalize_name(raw.get("role_name")),
        "operation": normalize_name(raw.get("query_type")), "target_object": target or "",
        "execution_status": normalize_name(raw.get("execution_status")),
        "change_id": tag_match.group(1).upper() if tag_match else None,
        "access_history_present": access is not None, "objects_modified": modified,
        "query_text": raw.get("query_text", ""), "raw": raw,
    }


def filter_queries(queries: Iterable[dict], start: datetime, end: datetime,
                   query_ids: set[str] | None = None) -> list[dict]:
    """Apply inclusive-start/exclusive-end UTC filtering before correlation."""
    return [item for item in queries if start <= parse_utc(item["start_time"]) < end
            and (query_ids is None or item.get("query_id") in query_ids)]


def _change_user(change: dict, users: list[dict]) -> str:
    resolved = resolve_identity(str(change.get("implementer") or ""), users)
    return normalize_name(resolved.get("user", {}).get("user_name")) if resolved["status"] == "RESOLVED" else ""


def _window(change: dict) -> tuple[datetime | None, datetime | None]:
    try:
        start, end = parse_utc(change.get("start")), parse_utc(change.get("end"))
        return (start, end) if start < end else (None, None)
    except (TypeError, ValueError):
        return None, None


def correlate_query(event: dict, changes: list[dict], users: list[dict]) -> dict:
    """Use structured tags first, then deterministic supporting signals."""
    by_id = {normalize_name(change.get("change_id")): change for change in changes}
    if event.get("change_id"):
        change = by_id.get(normalize_name(event["change_id"]))
        return {"classification": "MATCHED" if change else "UNMATCHED", "confidence": "STRONG",
                "change": change, "signals": ["QUERY_TAG"]}
    ranked = []
    for change in changes:
        expected = change.get("expected") or []
        start, end = _window(change)
        signals = []
        if event["user"] == _change_user(change, users): signals.append("IMPLEMENTER")
        if start and end and start <= parse_utc(event["timestamp"]) <= end: signals.append("WINDOW")
        if any(normalize_name(item.get("operation")) == event["operation"] for item in expected): signals.append("OPERATION")
        if any(normalize_name(item.get("resource_id")) == normalize_name(event["target_object"]) for item in expected): signals.append("TARGET")
        ranked.append((len(signals), change, signals))
    ranked.sort(key=lambda row: row[0], reverse=True)
    if ranked and ranked[0][0] >= 3 and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
        return {"classification": "POSSIBLE_MATCH", "confidence": "SUPPORTING",
                "change": ranked[0][1], "signals": ranked[0][2]}
    return {"classification": "UNMATCHED", "confidence": "NONE", "change": None, "signals": []}


def _finding(category: str, expected: object, observed: object, evidence: list[str], action: str) -> dict:
    return {"category": category, "severity": SEVERITY[category], "expected": expected,
            "observed": observed, "evidence": list(dict.fromkeys(evidence)), "recommended_action": action}


def _evaluate_event(event: dict, change: dict, users: list[dict], correlation: dict) -> tuple[list[dict], bool]:
    findings = []
    refs = [event["query_id"], change.get("change_id", "")]
    expected = change.get("expected") or []
    expected_user = _change_user(change, users)
    expected_role = normalize_name(change.get("snowflake_context", {}).get("requested_role"))
    exact = any(normalize_name(item.get("operation")) == event["operation"] and
                normalize_name(item.get("resource_id")) == normalize_name(event["target_object"]) for item in expected)
    operation_known = any(normalize_name(item.get("operation")) == event["operation"] for item in expected)
    start, end = _window(change)
    if normalize_name(change.get("state")) != "APPROVED":
        findings.append(_finding("UNAPPROVED_CHANGE", "Approved change", change.get("state"), refs, "Obtain approval before implementation."))
    if start and end and not (start <= parse_utc(event["timestamp"]) <= end):
        findings.append(_finding("EXECUTED_OUTSIDE_WINDOW", f"{change.get('start')} to {change.get('end')}", event["timestamp"], refs, "Review timing and obtain a valid implementation window."))
    if expected_user and event["user"] != expected_user:
        findings.append(_finding("UNAUTHORIZED_IMPLEMENTER", expected_user, event["user"], refs, "Confirm implementer authorization and investigate the executing identity."))
    if expected_role and event["role"] != expected_role:
        findings.append(_finding("ROLE_MISMATCH", expected_role, event["role"], refs, "Confirm the approved execution role and review effective privileges."))
    if not operation_known:
        findings.append(_finding("UNAPPROVED_OPERATION", [item.get("operation") for item in expected], event["operation"], refs, "Investigate the additional operation and obtain approval where appropriate."))
        findings.append(_finding("UNEXPECTED_ADDITIONAL_OPERATION", "Only documented operations", event["operation"], refs, "Review activity outside the approved change scope."))
    elif not exact:
        findings.append(_finding("WRONG_TARGET_OBJECT", [item.get("resource_id") for item in expected if normalize_name(item.get("operation")) == event["operation"]], event["target_object"], refs, "Validate the affected object and remediate unintended modifications."))
    if event["execution_status"] != "SUCCESS":
        findings.append(_finding("FAILED_EXECUTION", "SUCCESS", event["execution_status"], refs, "Review the Snowflake error and confirm whether implementation was retried."))
    if event["execution_status"] == "SUCCESS" and event["operation"] in GOVERNED_OPERATIONS and not event["access_history_present"]:
        findings.append(_finding("INSUFFICIENT_AUDIT_EVIDENCE", "Corroborating ACCESS_HISTORY where available", "No matching access record", refs, "Review audit latency/retention and corroborate through other evidence."))
    if not findings:
        findings.append(_finding("COMPLIANT_EXECUTION", "Approved operation, identity, role, target, and window", "Observed evidence is consistent", refs, "Retain evidence with the change record."))
    return findings, exact and event["execution_status"] == "SUCCESS"


def _overall(findings: list[dict]) -> str:
    categories = {item["category"] for item in findings}
    if categories == {"COMPLIANT_EXECUTION"}: return "COMPLIANT_EXECUTION"
    if categories & {"UNAUTHORIZED_IMPLEMENTER", "ROLE_MISMATCH", "UNAPPROVED_OPERATION", "WRONG_TARGET_OBJECT", "UNAPPROVED_CHANGE", "POSSIBLE_UNAPPROVED_ACTIVITY"}: return "DEVIATION_DETECTED"
    if categories & {"INSUFFICIENT_AUDIT_EVIDENCE", "NO_EXECUTION_EVIDENCE", "EXPECTED_OPERATION_MISSING"}: return "EVIDENCE_INCOMPLETE"
    return "DEVIATION_DETECTED"


def investigate_change(change_id: str, bundle: dict, *, evaluation_time: datetime | str | None = None,
                       query_ids: Iterable[str] | None = None) -> dict:
    changes = bundle.get("changes", [])
    change = next((item for item in changes if normalize_name(item.get("change_id")) == normalize_name(change_id)), None)
    if not change:
        return {"status": "NEED_MORE_INFO", "mode": "change", "subject": change_id,
                "findings": [_finding("NO_EXECUTION_EVIDENCE", "Existing change record", "Change not found", [], "Verify the change number.")], "timeline": []}
    evaluation = parse_utc(evaluation_time) if isinstance(evaluation_time, str) else evaluation_time or datetime.now(UTC)
    change_start, change_end = _window(change)
    evidence_start = (change_start - timedelta(days=1)) if change_start else evaluation - timedelta(days=30)
    evidence_end = max(evaluation, (change_end + timedelta(days=1)) if change_end else evaluation)
    raw = filter_queries(bundle.get("query_history", []), evidence_start, evidence_end, set(query_ids) if query_ids is not None else None)
    access = {item["query_id"]: item for item in bundle.get("access_history", [])}
    events, findings, covered = [], [], set()
    for item in raw:
        event = normalize_query(item, access)
        correlation = correlate_query(event, changes, bundle.get("users", []))
        if not correlation.get("change") or correlation["change"].get("change_id") != change["change_id"]: continue
        event_findings, exact = _evaluate_event(event, change, bundle.get("users", []), correlation)
        findings.extend(event_findings)
        if exact: covered.add((event["operation"], normalize_name(event["target_object"])))
        events.append(_timeline_row(event, correlation, event_findings))
    expected_keys = {(normalize_name(item.get("operation")), normalize_name(item.get("resource_id"))) for item in change.get("expected", [])}
    missing = expected_keys - covered
    if not events:
        findings.append(_finding("NO_EXECUTION_EVIDENCE", "Correlated Snowflake execution evidence", "No matching query history", [change["change_id"]], "Check audit retention and confirm implementation status manually."))
    if missing:
        findings.append(_finding("EXPECTED_OPERATION_MISSING", sorted(f"{op}@{target}" for op, target in missing), "Not observed successfully", [change["change_id"]], "Confirm whether the operation ran or remains outstanding."))
    return _result("change", change["change_id"], evidence_start, evidence_end, findings, events,
                   change=change, identity=None, logins=[])


def investigate_user(identifier: str, bundle: dict, *, days: int = 10,
                     evaluation_time: datetime | str | None = None, start: datetime | str | None = None,
                     end: datetime | str | None = None, query_ids: Iterable[str] | None = None) -> dict:
    identity = resolve_identity(identifier, bundle.get("users", []))
    evaluation = parse_utc(evaluation_time) if isinstance(evaluation_time, str) else evaluation_time or datetime.now(UTC)
    finish = parse_utc(end) if isinstance(end, str) else end or evaluation
    begin = parse_utc(start) if isinstance(start, str) else start or finish - timedelta(days=days)
    if identity["status"] != "RESOLVED":
        category = "IDENTITY_AMBIGUOUS" if identity["status"] == "AMBIGUOUS" else "IDENTITY_NOT_FOUND"
        finding = _finding(category, "One exact synthetic Snowflake identity", identity["status"],
                           [item.get("user_id", "") for item in identity.get("matches", [])], "Provide an exact user name, ID, or unique email address.")
        return _result("user", identifier, begin, finish, [finding], [], identity=identity, logins=[])
    user_name = normalize_name(identity["user"]["user_name"])
    raw = [item for item in filter_queries(bundle.get("query_history", []), begin, finish,
                                            set(query_ids) if query_ids is not None else None)
           if normalize_name(item.get("user_name")) == user_name]
    access = {item["query_id"]: item for item in bundle.get("access_history", [])}
    findings, events, matched = [], [], set()
    for item in raw:
        event = normalize_query(item, access)
        correlation = correlate_query(event, bundle.get("changes", []), bundle.get("users", []))
        event_findings = []
        change = correlation.get("change")
        if change:
            event_findings, _ = _evaluate_event(event, change, bundle.get("users", []), correlation)
            matched.add(change["change_id"])
        elif event["operation"] in GOVERNED_OPERATIONS:
            event_findings = [_finding("POSSIBLE_UNAPPROVED_ACTIVITY", "A matching approved change or stronger correlation evidence", "No approved change matched", [event["query_id"]], "Review the activity; unmatched evidence is not proof of malicious action.")]
        findings.extend(event_findings)
        events.append(_timeline_row(event, correlation, event_findings))
    logins = [item for item in bundle.get("login_history", []) if normalize_name(item.get("user_name")) == user_name
              and begin <= parse_utc(item["event_timestamp"]) < finish]
    result = _result("user", identity["user"]["email"], begin, finish, findings, events, identity=identity, logins=logins)
    result["summary"].update({
        "total_activity_events": len(events), "governed_change_operations": sum(row["operation"] in GOVERNED_OPERATIONS for row in events),
        "matched_approved_changes": len(matched), "deviations_identified": sum(item["category"] not in {"COMPLIANT_EXECUTION"} for item in findings),
        "unmatched_activities": sum(row["correlation"] == "UNMATCHED" for row in events),
        "manual_review_items": sum(item["severity"] == "REVIEW" for item in findings),
    })
    return result


def _timeline_row(event: dict, correlation: dict, findings: list[dict]) -> dict:
    categories = list(dict.fromkeys(item["category"] for item in findings))
    return {"timestamp": event["timestamp"], "user": event["user"], "role": event["role"],
            "operation": event["operation"], "target_object": event["target_object"], "query_id": event["query_id"],
            "change_id": correlation.get("change", {}).get("change_id") if correlation.get("change") else None,
            "correlation": correlation["classification"], "confidence": correlation["confidence"],
            "execution_status": event["execution_status"], "deviation": ", ".join(categories) or "ROUTINE_ACTIVITY",
            "access_history_present": event["access_history_present"]}


def _result(mode: str, subject: str, start: datetime, end: datetime, findings: list[dict], timeline: list[dict],
            **extra) -> dict:
    unique = []
    seen = set()
    for item in findings:
        marker = (item["category"], str(item["expected"]), str(item["observed"]), tuple(item["evidence"]))
        if marker not in seen: unique.append(item); seen.add(marker)
    timeline.sort(key=lambda row: parse_utc(row["timestamp"]))
    categories = list(dict.fromkeys(item["category"] for item in unique))
    return {"status": _overall(unique) if unique else "NO_GOVERNED_ACTIVITY", "mode": mode, "subject": subject,
            "investigation_window": {"start": start.isoformat().replace("+00:00", "Z"), "end": end.isoformat().replace("+00:00", "Z")},
            "summary": {"overall_assessment": _overall(unique) if unique else "NO_GOVERNED_ACTIVITY",
                        "finding_categories": categories, "activity_count": len(timeline)},
            "findings": unique, "timeline": timeline,
            "limitations": ["Successful query history verifies reported execution, not final object configuration.",
                            "Missing ACCESS_HISTORY may reflect retention or audit latency and is not proof that no modification occurred."],
            **extra}


def persist_investigation_result(result: dict) -> str:
    """Write a sanitized result to the isolated Snowflake output directory."""
    target = output_dir("snowflake", create=True) / f"post_implementation_{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid4().hex[:8]}.json"
    target.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    return str(target)
