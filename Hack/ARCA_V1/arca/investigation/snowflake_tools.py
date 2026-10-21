"""Read-only Snowflake investigation tools backed by synthetic audit evidence."""
from __future__ import annotations

from datetime import timedelta
from typing import Iterable
from uuid import uuid4

from arca.snowflake_post_implementation import (
    GOVERNED_OPERATIONS, correlate_query, filter_queries, investigate_change, investigate_user,
    normalize_name, normalize_query, resolve_identity,
)
from arca.time_filters import parse_utc


def _result(tool: str, items: list[dict], **query) -> dict:
    return {"tool": tool, "count": len(items), "query": query, "items": items}


class SnowflakeInvestigationTools:
    """Provider-specific facade; all authorization findings come from the shared validator."""

    provider = "snowflake"

    def __init__(self, bundle: dict, evidence_mode: str = "demonstration"):
        self.bundle = bundle
        self.evidence_mode = evidence_mode

    @property
    def evidence_as_of(self) -> str:
        return max(self.bundle["query_history"], key=lambda row: parse_utc(row["start_time"]))["start_time"]

    def get_change_details(self, change_id: str) -> dict:
        items = [item for item in self.bundle["changes"] if normalize_name(item.get("change_id")) == normalize_name(change_id)]
        projected = [{"change_id": item["change_id"], "approval_status": item.get("state"),
                      "implementer": item.get("implementer"), "requested_role": item.get("snowflake_context", {}).get("requested_role"),
                      "window_start": item.get("start"), "window_end": item.get("end"),
                      "expected_operations": item.get("expected", [])} for item in items]
        return _result("get_change_details", projected, change_id=change_id)

    def resolve_snowflake_user(self, identifier: str) -> dict:
        resolved = resolve_identity(identifier, self.bundle["users"])
        return _result("resolve_snowflake_user", resolved.get("matches", []), identifier=identifier, status=resolved["status"])

    def get_user_activity(self, identifier: str, start: str, end: str) -> dict:
        resolved = resolve_identity(identifier, self.bundle["users"])
        if resolved["status"] != "RESOLVED": return _result("get_user_activity", [], identifier=identifier, start=start, end=end, identity_status=resolved["status"])
        user = normalize_name(resolved["user"]["user_name"])
        items = [row for row in filter_queries(self.bundle["query_history"], parse_utc(start), parse_utc(end))
                 if normalize_name(row.get("user_name")) == user]
        return _result("get_user_activity", items, identifier=identifier, start=start, end=end, identity_status="RESOLVED")

    def get_change_activity(self, change_id: str, evaluation_time: str | None = None,
                            query_ids: Iterable[str] | None = None) -> dict:
        assessment = investigate_change(change_id, self.bundle, evaluation_time=evaluation_time, query_ids=query_ids)
        return _result("get_change_activity", assessment.get("timeline", []), change_id=change_id,
                       assessment=assessment)

    def get_access_history(self, query_ids: Iterable[str] | None = None, identity: str | None = None,
                           start: str | None = None, end: str | None = None) -> dict:
        wanted = set(query_ids or [])
        items = []
        for row in self.bundle["access_history"]:
            if wanted and row["query_id"] not in wanted: continue
            if identity and normalize_name(row.get("user_name")) != normalize_name(identity): continue
            if start and parse_utc(row["query_start_time"]) < parse_utc(start): continue
            if end and parse_utc(row["query_start_time"]) >= parse_utc(end): continue
            items.append(row)
        return _result("get_access_history", items, query_ids=sorted(wanted), identity=identity, start=start, end=end)

    def get_role_grants(self, role_name: str | None = None, identity: str | None = None) -> dict:
        roles = set()
        if role_name: roles.add(normalize_name(role_name))
        if identity:
            resolved = resolve_identity(identity, self.bundle["users"])
            if resolved["status"] == "RESOLVED":
                user = normalize_name(resolved["user"]["user_name"])
                roles.update(normalize_name(row["role_name"]) for row in self.bundle["grants_to_users"]
                             if normalize_name(row["user_name"]) == user and not row.get("revoked_on"))
        items = [row for row in self.bundle["object_grants"] if not roles or normalize_name(row["grantee_role"]) in roles]
        items.extend(row for row in self.bundle["grants_to_roles"] if not roles or
                     normalize_name(row.get("grantee_role")) in roles or normalize_name(row.get("granted_role")) in roles)
        return _result("get_role_grants", items, role_name=role_name, identity=identity)

    def detect_change_deviations(self, change_id: str, evaluation_time: str | None = None,
                                 query_ids: Iterable[str] | None = None) -> dict:
        assessment = investigate_change(change_id, self.bundle, evaluation_time=evaluation_time, query_ids=query_ids)
        findings = self.structured_findings(assessment, change_id)
        return _result("detect_change_deviations", findings, change_id=change_id,
                       assessment=assessment)

    def structured_findings(self, assessment: dict, change_id: str | None = None) -> list[dict]:
        findings = []
        for index, item in enumerate(assessment.get("findings", []), start=1):
            refs = item.get("evidence", [])
            finding_change = change_id or assessment.get("change", {}).get("change_id") or "UNMATCHED"
            findings.append({"finding_id": f"SF-FIND-{finding_change}-{index:03d}", "finding_type": item["category"],
                             "severity": item["severity"], "explanation": f"Expected {item.get('expected')}; observed {item.get('observed')}.",
                             "expected_behavior": item.get("expected"), "observed_behavior": item.get("observed"),
                             "change_id": finding_change, "relevant_query_ids": [ref for ref in refs if str(ref).startswith("SF-QRY-")],
                             "evidence_source": "Synthetic Snowflake QUERY_HISTORY and ACCESS_HISTORY",
                             "correlation_confidence": "STRONG" if any(row.get("confidence") == "STRONG" for row in assessment.get("timeline", [])) else "SUPPORTING",
                             "recommended_action": item.get("recommended_action")})
        return findings

    def get_unapproved_activity(self, identifier: str | None = None, start: str | None = None,
                                end: str | None = None, role: str | None = None,
                                operation: str | None = None) -> dict:
        access = {row["query_id"]: row for row in self.bundle["access_history"]}
        raw = self.bundle["query_history"]
        if start and end: raw = filter_queries(raw, parse_utc(start), parse_utc(end))
        resolved_name = None
        if identifier:
            resolved = resolve_identity(identifier, self.bundle["users"])
            if resolved["status"] != "RESOLVED": return _result("get_unapproved_activity", [], identity_status=resolved["status"])
            resolved_name = normalize_name(resolved["user"]["user_name"])
        items = []
        for row in raw:
            event = normalize_query(row, access)
            if event["operation"] not in GOVERNED_OPERATIONS: continue
            if resolved_name and event["user"] != resolved_name: continue
            if role and event["role"] != normalize_name(role): continue
            if operation and normalize_name(operation) not in event["operation"]: continue
            correlation = correlate_query(event, self.bundle["changes"], self.bundle["users"])
            if correlation["classification"] != "UNMATCHED": continue
            items.append({"query_id": event["query_id"], "timestamp": event["timestamp"], "user": event["user"],
                          "role": event["role"], "operation": event["operation"], "target_object": event["target_object"],
                          "classification": "POSSIBLE_UNAPPROVED_ACTIVITY", "correlation_confidence": correlation["confidence"],
                          "warning": "Unmatched activity is not proof of a malicious or unauthorized change."})
        return _result("get_unapproved_activity", items, identifier=identifier, start=start, end=end, role=role, operation=operation)

    def build_investigation_timeline(self, evidence: Iterable[dict]) -> dict:
        items = sorted(list(evidence), key=lambda row: parse_utc(row.get("timestamp") or row.get("start_time")))
        return _result("build_investigation_timeline", items)

    def summarize_investigation(self, assessment: dict, question: str = "") -> dict:
        summary = {
            "provider": "snowflake", "investigation_id": f"sf-investigation-{uuid4().hex}",
            "investigation_type": assessment.get("mode"), "user_question": question,
            "change_id": assessment.get("change", {}).get("change_id") if assessment.get("change") else None,
            "user_identity": assessment.get("identity", {}).get("user") if assessment.get("identity") else None,
            "time_range": assessment.get("investigation_window"), "risk_classification": assessment.get("status"),
            "finding_categories": assessment.get("summary", {}).get("finding_categories", []),
            "confidence": "STRONG" if any(row.get("confidence") == "STRONG" for row in assessment.get("timeline", [])) else "SUPPORTING",
            "evidence_limitations": assessment.get("limitations", []),
            "recommended_follow_up_actions": list(dict.fromkeys(item["recommended_action"] for item in assessment.get("findings", []))),
        }
        return _result("summarize_investigation", [summary])

    def user_window(self, days: int, evaluation_time: str | None = None) -> tuple[str, str]:
        end = parse_utc(evaluation_time or self.evidence_as_of)
        start = end - timedelta(days=days)
        fmt = lambda value: value.isoformat(timespec="seconds").replace("+00:00", "Z")
        return fmt(start), fmt(end)
