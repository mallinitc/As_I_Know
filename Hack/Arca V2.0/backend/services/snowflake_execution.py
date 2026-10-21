from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any
from uuid import uuid4

from backend.errors import (
    SnowflakeChangeNotFound,
    SnowflakeIdentityAmbiguous,
    SnowflakeIdentityNotFound,
    SnowflakeScenarioNotFound,
)
from backend.repositories.snowflake import SnowflakeRepository
from backend.services.timestamps import parse_utc, utc_text


SCHEMA_VERSION = 1
CHANGE_TAG = re.compile(r"(?:^|[;,\s])ARCA_CHANGE=([A-Z0-9_-]+)(?:$|[;,\s])", re.IGNORECASE)
READ_ONLY_TYPES = {"SELECT", "SHOW", "DESCRIBE", "USE"}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _change_from_tag(query: dict[str, Any]) -> str | None:
    match = CHANGE_TAG.search(str(query.get("query_tag") or ""))
    return match.group(1).upper() if match else None


def _finding(category: str, message: str, query: dict[str, Any] | None = None,
             *, severity: str = "HIGH", confidence: str = "confirmed",
             change_id: str | None = None) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "message": message,
        "query_ids": [query["query_id"]] if query else [],
        "change_id": change_id,
    }


class SnowflakeExecutionService:
    """Read-only post-implementation correlation over native V2 evidence."""

    def __init__(self, repository: SnowflakeRepository | None = None) -> None:
        self.repository = repository or SnowflakeRepository()

    def scenarios(self) -> list[dict[str, Any]]:
        return self.repository.post_implementation_scenarios()

    def _scenario(self, scenario_id: str | None, mode: str) -> dict[str, Any] | None:
        if not scenario_id:
            return None
        scenario = next((item for item in self.scenarios() if item["scenario_id"] == scenario_id), None)
        if scenario is None or scenario["investigation_mode"] != mode:
            raise SnowflakeScenarioNotFound(scenario_id)
        return scenario

    def _resolve_user(self, identity: str) -> dict[str, Any]:
        needle = identity.strip().casefold()
        matches = [
            item for item in self.repository.users()
            if needle in {
                str(item.get("user_id") or "").casefold(),
                str(item.get("user_name") or "").casefold(),
                str(item.get("email") or "").casefold(),
            }
        ]
        if not matches:
            raise SnowflakeIdentityNotFound(identity)
        if len(matches) > 1:
            raise SnowflakeIdentityAmbiguous(identity)
        return matches[0]

    def _user_name_for_implementer(self, implementer: str) -> str | None:
        try:
            return str(self._resolve_user(implementer)["user_name"])
        except (SnowflakeIdentityNotFound, SnowflakeIdentityAmbiguous):
            return None

    def _query_scope(self, scenario: dict[str, Any] | None) -> list[dict[str, Any]]:
        queries = self.repository.query_history()
        if scenario is None:
            return queries
        allowed = set(scenario["evidence_query_ids"])
        return [item for item in queries if item.get("query_id") in allowed]

    def _assess_query(self, query: dict[str, Any], change: dict[str, Any],
                      access_by_query: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
        findings: list[dict[str, Any]] = []
        change_id = str(change["change_id"])
        expected = change.get("expected") or []
        operation, target = _norm(query.get("query_type")), _norm(query.get("target_object"))
        matching_operation = [item for item in expected if _norm(item.get("operation")) == operation]
        exact_match = any(_norm(item.get("resource_id")) == target for item in matching_operation)

        status = _norm(query.get("execution_status"))
        if status != "SUCCESS":
            findings.append(_finding("FAILED_EXECUTION", "The documented operation was attempted but did not complete successfully.", query, change_id=change_id))

        try:
            occurred = parse_utc(query["start_time"])
            start, end = parse_utc(change["start"]), parse_utc(change["end"])
            if not start <= occurred <= end:
                findings.append(_finding("EXECUTED_OUTSIDE_WINDOW", "The operation occurred outside the approved change window.", query, change_id=change_id))
        except (KeyError, TypeError, ValueError):
            findings.append(_finding("INSUFFICIENT_AUDIT_EVIDENCE", "The approved or observed timestamp could not be validated.", query, severity="MEDIUM", confidence="insufficient", change_id=change_id))

        expected_user = self._user_name_for_implementer(str(change.get("implementer") or ""))
        if expected_user is None:
            findings.append(_finding("INSUFFICIENT_AUDIT_EVIDENCE", "The documented implementer could not be resolved to a Snowflake user.", query, severity="MEDIUM", confidence="insufficient", change_id=change_id))
        elif _norm(query.get("user_name")) != _norm(expected_user):
            findings.append(_finding("UNAUTHORIZED_IMPLEMENTER", "The observed Snowflake user does not match the documented implementer.", query, change_id=change_id))

        requested_role = _norm((change.get("snowflake_context") or {}).get("requested_role"))
        if requested_role and _norm(query.get("role_name")) != requested_role:
            findings.append(_finding("ROLE_MISMATCH", "The operation used a role different from the approved requested role.", query, change_id=change_id))

        if not matching_operation:
            findings.append(_finding("UNAPPROVED_OPERATION", "The observed operation is not documented in the approved change.", query, change_id=change_id))
            findings.append(_finding("UNEXPECTED_ADDITIONAL_OPERATION", "Additional modifying activity was observed beyond the approved intent.", query, change_id=change_id))
        elif not exact_match:
            findings.append(_finding("WRONG_TARGET_OBJECT", "The operation type matched, but the modified target did not match the approved object.", query, change_id=change_id))

        if query.get("query_id") not in access_by_query and operation not in READ_ONLY_TYPES:
            findings.append(_finding("INSUFFICIENT_AUDIT_EVIDENCE", "Query history exists, but matching access-history evidence is unavailable; final object state is not confirmed.", query, severity="MEDIUM", confidence="insufficient", change_id=change_id))

        successful_match = status == "SUCCESS" and exact_match
        if successful_match and not findings:
            findings.append(_finding("COMPLIANT_EXECUTION", "The observed operation matches the approved identity, role, target, and window.", query, severity="INFO", change_id=change_id))
        return findings, successful_match

    def _response(self, *, mode: str, evaluated: datetime, queries: list[dict[str, Any]],
                  findings: list[dict[str, Any]], change: dict[str, Any] | None = None,
                  user: dict[str, Any] | None = None, period_start: datetime | None = None) -> dict[str, Any]:
        adverse = [item for item in findings if item["severity"] in {"HIGH", "CRITICAL"}]
        uncertain = [item for item in findings if item["confidence"] in {"possible", "insufficient"}]
        compliant = [item for item in findings if item["category"] == "COMPLIANT_EXECUTION"]
        if adverse and compliant:
            overall = "MIXED"
        elif adverse:
            overall = "NON_COMPLIANT"
        elif uncertain:
            overall = "REVIEW_REQUIRED"
        elif compliant:
            overall = "COMPLIANT"
        else:
            overall = "NO_RELEVANT_ACTIVITY"
        access_by_query = {item.get("query_id"): item for item in self.repository.access_history()}
        observed = [{
            "query_id": item.get("query_id"), "operation": item.get("query_type"),
            "target": item.get("target_object"), "actor": item.get("user_name"),
            "role": item.get("role_name"), "timestamp": item.get("start_time"),
            "status": item.get("execution_status"), "change_id": _change_from_tag(item),
        } for item in queries]
        limitations = [
            "Query and access history are audit evidence; they do not independently prove final Snowflake object state.",
            "Synthetic evidence is read-only and does not represent a live Snowflake connection.",
        ]
        if any(item.get("query_id") not in access_by_query for item in queries):
            limitations.append("Access-history evidence is missing for one or more observed queries.")
        advice = {
            "EXECUTED_OUTSIDE_WINDOW": "Reconcile the execution timestamp and require work to occur within an approved window.",
            "UNAUTHORIZED_IMPLEMENTER": "Confirm the actor's authorization or update the approved implementer before execution.",
            "ROLE_MISMATCH": "Use the approved least-privilege Snowflake role or obtain documented approval for the role change.",
            "WRONG_TARGET_OBJECT": "Review the modified object and correct either the implementation target or approved change record.",
            "UNAPPROVED_OPERATION": "Investigate the additional operation and obtain approval before any further modification.",
            "UNEXPECTED_ADDITIONAL_OPERATION": "Reconcile observed additional activity against the approved implementation plan.",
            "FAILED_EXECUTION": "Resolve the execution failure and collect evidence before confirming implementation.",
            "EXPECTED_OPERATION_MISSING": "Collect additional audit evidence or complete the documented operation in an approved window.",
            "NO_EXECUTION_EVIDENCE": "Obtain query or access-history evidence before concluding that the change was implemented.",
            "POSSIBLE_UNAPPROVED_ACTIVITY": "Review the modifying activity and link it to an approved change if supported by evidence.",
            "INSUFFICIENT_AUDIT_EVIDENCE": "Perform manual review using additional audit or final-state evidence.",
        }
        recommendations = list(dict.fromkeys(advice[item["category"]] for item in findings if item["category"] in advice))
        return {
            "schema_version": SCHEMA_VERSION,
            "investigation_id": f"SF-EXEC-{uuid4().hex[:12].upper()}",
            "provider": "snowflake", "mode": mode,
            "change_id": change.get("change_id") if change else None,
            "user": user, "evaluation_timestamp": utc_text(evaluated),
            "period_start": utc_text(period_start) if period_start else None,
            "period_end": utc_text(evaluated), "overall_status": overall,
            "findings": findings, "query_ids": [item["query_id"] for item in queries],
            "confidence": "limited" if uncertain else ("high" if queries else "none"),
            "timeline": observed,
            "expected_operations": (change or {}).get("expected", []),
            "observed_operations": observed,
            "evidence": [{"query_id": item["query_id"], "access_history_available": item["query_id"] in access_by_query} for item in queries],
            "recommendations": recommendations,
            "limitations": limitations,
        }

    def assess_change(self, change_id: str, evaluation_timestamp: datetime | None = None,
                      scenario_id: str | None = None) -> dict[str, Any]:
        scenario = self._scenario(scenario_id, "change")
        change = next((item for item in self.repository.changes() if item.get("change_id") == change_id), None)
        if change is None:
            raise SnowflakeChangeNotFound(change_id)
        if scenario and scenario.get("change_id") != change_id:
            raise SnowflakeScenarioNotFound(scenario_id or "")
        evaluated = (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
        queries = [item for item in self._query_scope(scenario) if _change_from_tag(item) == change_id and parse_utc(item["start_time"]) <= evaluated]
        access = {item.get("query_id"): item for item in self.repository.access_history()}
        findings: list[dict[str, Any]] = []
        covered: set[tuple[str, str]] = set()
        for query in queries:
            assessed, matched = self._assess_query(query, change, access)
            findings.extend(assessed)
            if matched:
                covered.add((_norm(query.get("query_type")), _norm(query.get("target_object"))))
        for expected in change.get("expected") or []:
            signature = (_norm(expected.get("operation")), _norm(expected.get("resource_id")))
            if signature not in covered:
                findings.append(_finding("EXPECTED_OPERATION_MISSING", f"No successful matching audit event was observed for {expected.get('operation')} on {expected.get('resource_id')}.", change_id=change_id))
        if not queries:
            findings.insert(0, _finding("NO_EXECUTION_EVIDENCE", "No query-history evidence was found for this change.", severity="MEDIUM", confidence="insufficient", change_id=change_id))
        return self._response(mode="change", evaluated=evaluated, queries=queries, findings=findings, change=change)

    def assess_user(self, identity: str, window_days: int = 10,
                    evaluation_timestamp: datetime | None = None,
                    scenario_id: str | None = None) -> dict[str, Any]:
        scenario = self._scenario(scenario_id, "user")
        user = self._resolve_user(identity)
        if scenario and self._resolve_user(str(scenario.get("user_identity")))["user_id"] != user["user_id"]:
            raise SnowflakeScenarioNotFound(scenario_id or "")
        evaluated = (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
        period_start = evaluated - timedelta(days=window_days)
        queries = [item for item in self._query_scope(scenario)
                   if _norm(item.get("user_name")) == _norm(user["user_name"])
                   and period_start <= parse_utc(item["start_time"]) <= evaluated]
        changes = {item["change_id"]: item for item in self.repository.changes()}
        access = {item.get("query_id"): item for item in self.repository.access_history()}
        findings: list[dict[str, Any]] = []
        for query in queries:
            linked_id = _change_from_tag(query)
            linked = changes.get(linked_id) if linked_id else None
            if linked:
                assessed, _ = self._assess_query(query, linked, access)
                findings.extend(assessed)
            elif _norm(query.get("query_type")) in READ_ONLY_TYPES:
                findings.append(_finding("UNMATCHED_READ_ONLY_ACTIVITY", "Read-only activity has no matching change; it is not classified as unauthorized.", query, severity="INFO", confidence="possible"))
            else:
                findings.append(_finding("POSSIBLE_UNAPPROVED_ACTIVITY", "A modifying operation has no matching approved change reference and requires review.", query, severity="MEDIUM", confidence="possible"))
        return self._response(mode="user", evaluated=evaluated, period_start=period_start, queries=queries, findings=findings, user=user)
