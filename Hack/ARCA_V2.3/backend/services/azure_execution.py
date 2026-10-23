from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from backend.errors import (
    AzureChangeNotFound,
    AzureIdentityAmbiguous,
    AzureIdentityNotFound,
    AzureScenarioNotFound,
)
from backend.repositories.azure import AzureRepository
from backend.services.azure_validation import AzureValidationService, _norm, _scope_covers
from backend.services.timestamps import parse_utc, utc_text


SCHEMA_VERSION = 1


def _operation(event: dict[str, Any]) -> str:
    value = event.get("operation_name") or {}
    return str(value.get("value") if isinstance(value, dict) else value or "")


def _status(event: dict[str, Any]) -> str:
    value = event.get("status") or {}
    return str(value.get("value") if isinstance(value, dict) else value or "")


def _explicit_change(event: dict[str, Any]) -> str | None:
    value = (event.get("properties") or {}).get("change_id")
    return str(value).upper() if value else None


def _finding(category: str, message: str, event: dict[str, Any] | None = None, *,
             severity: str = "HIGH", confidence: str = "confirmed",
             change_id: str | None = None, recommendation: str) -> dict[str, Any]:
    return {
        "category": category, "severity": severity, "confidence": confidence,
        "message": message, "event_ids": [event["event_data_id"]] if event else [],
        "change_id": change_id, "recommendation": recommendation,
    }


def _authorized(change: dict[str, Any]) -> list[dict[str, Any]]:
    return change.get("authorized_implementers") or [change.get("implementer") or {}]


def _event_score(event: dict[str, Any], change: dict[str, Any]) -> tuple[int, str]:
    change_id = str(change.get("change_id"))
    explicit = _explicit_change(event)
    if explicit and explicit != change_id:
        return -100, "UNMATCHED"
    if explicit == change_id:
        return 100, "MATCHED"
    expected = change.get("expected") or []
    principals = {_norm(item.get("principal_id")) for item in _authorized(change)}
    score = 0
    if _norm(event.get("caller_principal_id")) in principals: score += 2
    if any(_norm(item.get("operation")) == _norm(_operation(event)) for item in expected): score += 2
    if any(_norm(item.get("resource_id")) == _norm(event.get("resource_id")) for item in expected): score += 2
    near_window = False
    try:
        occurred, start, end = parse_utc(event["event_timestamp"]), parse_utc(change["start"]), parse_utc(change["end"])
        near_window = start - timedelta(days=1) <= occurred <= end + timedelta(days=1)
        if start <= occurred <= end: score += 2
    except (KeyError, TypeError, ValueError):
        pass
    if not near_window:
        return min(score, 4), "UNMATCHED"
    return score, "MATCHED" if score == 8 else ("POSSIBLE_MATCH" if score >= 5 else "UNMATCHED")


class AzureExecutionService:
    """Azure-native post-implementation correlation over synthetic evidence."""

    def __init__(self, repository: AzureRepository | None = None) -> None:
        self.repository = repository or AzureRepository()
        self.access_service = AzureValidationService(self.repository)

    def scenarios(self) -> list[dict[str, Any]]:
        return self._v1_scenarios() + self.repository.execution_scenarios()

    def _v1_scenarios(self) -> list[dict[str, Any]]:
        """Expose the five original V1 Stage 3 demos without altering evidence files."""
        catalog_path = self.repository.root.parent / "demo_catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        finding_map = {
            "S3-MATCH": ["COMPLIANT_EXECUTION"],
            "S3-TIMING": ["WRONG_TARGET_RESOURCE", "ROLE_OR_SCOPE_MISMATCH", "EXPECTED_OPERATION_MISSING"],
            "S3-UNEXPECTED-ACTOR": ["EXECUTED_OUTSIDE_WINDOW"],
            "S3-UNEXPECTED-RESOURCE": ["UNAUTHORIZED_IMPLEMENTER", "ROLE_OR_SCOPE_MISMATCH"],
            "S3-NO-EVIDENCE": ["NO_EXECUTION_EVIDENCE", "EXPECTED_OPERATION_MISSING"],
        }
        event_map = {
            "S3-MATCH": ["az-event-0001"], "S3-TIMING": ["az-event-0007"],
            "S3-UNEXPECTED-ACTOR": ["az-event-0008"], "S3-UNEXPECTED-RESOURCE": ["az-event-0009"],
            "S3-NO-EVIDENCE": [],
        }
        scenarios = []
        for item in catalog:
            if item.get("provider") != "azure" or item.get("feature") != "stage3":
                continue
            scenarios.append({
                "scenario_id": item["scenario_id"], "scenario_name": item["name"], "mode": "change",
                "change_id": item["associated_change_number"], "user_identity": item.get("user_identity") or None,
                "evaluation_timestamp": "2026-10-27T00:00:00Z", "window_days": 10,
                "event_data_ids": event_map[item["scenario_id"]],
                "expected_findings": finding_map[item["scenario_id"]], "source": "v1",
                "description": item["explanation"], "expected_outcome": item["expected_outcome"],
            })
        return scenarios

    def _scenario(self, scenario_id: str | None, mode: str) -> dict[str, Any] | None:
        if not scenario_id:
            return None
        scenario = next((item for item in self.scenarios() if item["scenario_id"] == scenario_id), None)
        if scenario is None or scenario["mode"] != mode:
            raise AzureScenarioNotFound(scenario_id)
        return scenario

    def _change(self, change_id: str) -> dict[str, Any]:
        change = next((item for item in self.repository.changes() if item.get("change_id") == change_id), None)
        if change is None:
            raise AzureChangeNotFound(change_id)
        return change

    def _resolve_identity(self, identity: str) -> dict[str, Any]:
        identities: dict[str, dict[str, Any]] = {}
        candidates: list[dict[str, Any]] = []
        for change in self.repository.changes():
            candidates.extend(_authorized(change))
        for pim in self.repository.pim_requests():
            candidates.append({"principal_id": pim.get("principal_id"), "principal_name": pim.get("principal_name"), "principal_type": pim.get("principal_type")})
        for item in candidates:
            principal_id, principal_name = _norm(item.get("principal_id")), _norm(item.get("principal_name"))
            if not principal_id and not principal_name: continue
            key = principal_id or principal_name
            identities.setdefault(key, {"principal_id": item.get("principal_id"), "principal_name": item.get("principal_name"), "principal_type": item.get("principal_type") or "User"})
        needle = _norm(identity)
        matches = [item for item in identities.values() if needle in {_norm(item.get("principal_id")), _norm(item.get("principal_name"))}]
        unique = {(_norm(item.get("principal_id")), _norm(item.get("principal_name"))): item for item in matches}
        if not unique: raise AzureIdentityNotFound(identity)
        if len(unique) > 1: raise AzureIdentityAmbiguous(identity)
        return next(iter(unique.values()))

    def _scenario_events(self, scenario: dict[str, Any] | None) -> list[dict[str, Any]]:
        events = self.repository.activity_logs()
        if not scenario: return events
        ids = set(scenario["event_data_ids"])
        return [item for item in events if item.get("event_data_id") in ids]

    def _v1_assessment(self, change: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
        """Preserve V1's original Stage 3 correlation classifications verbatim."""
        rows: list[dict[str, Any]] = []
        signals: list[str] = []
        expected = change.get("expected") or []
        implementer = _norm((change.get("implementer") or {}).get("principal_id"))
        expected_resources = {_norm(item.get("resource_id")) for item in expected}
        start, end = parse_utc(change["start"]), parse_utc(change["end"])
        for event in events:
            operation, resource = _operation(event), str(event.get("resource_id") or "")
            occurred = parse_utc(event["event_timestamp"])
            relevant = (_norm(event.get("caller_principal_id")) == implementer or _norm(resource) in expected_resources) and start - timedelta(hours=2) <= occurred <= end + timedelta(hours=2)
            if _norm(_status(event)) != "succeeded" or _norm(operation).endswith("/read") or not relevant:
                continue
            reasons: list[str] = []
            if _norm(event.get("caller_principal_id")) != implementer: reasons.append("ACTOR_MISMATCH")
            if not start <= occurred <= end: reasons.append("OUTSIDE_WINDOW")
            if not any(_norm(item.get("operation")) == _norm(operation) and _norm(item.get("resource_id")) == _norm(resource) for item in expected):
                reasons.append("UNEXPECTED_OPERATION_OR_RESOURCE")
            rows.append({
                "event_id": event.get("event_data_id"), "correlation_id": event.get("correlation_id"),
                "timestamp": event.get("event_timestamp"), "operation": operation, "resource_id": resource,
                "status": "DEVIATION" if reasons else "POTENTIAL_MATCH", "reasons": reasons,
            })
            properties = event.get("properties") or {}
            affected = _norm(properties.get("affected_resource_id"))
            changed = {_norm(value) for value in properties.get("changed_settings") or []}
            signal = None
            if _norm(operation) == "microsoft.authorization/roleassignments/delete" and "/microsoft.storage/storageaccounts/" in affected:
                signal = "STORAGE_ACCESS_LOSS_POSSIBLY_RELATED_TO_ROLE_ASSIGNMENT_REMOVAL"
            elif _norm(operation) == "microsoft.storage/storageaccounts/write" and "networkacls" in changed:
                signal = "STORAGE_ACCESS_LOSS_POSSIBLY_RELATED_TO_FIREWALL_MODIFICATION"
            if signal and signal not in signals: signals.append(signal)
        matched = {(_norm(item["operation"]), _norm(item["resource_id"])) for item in rows if item["status"] == "POTENTIAL_MATCH"}
        missing = [item for item in expected if (_norm(item.get("operation")), _norm(item.get("resource_id"))) not in matched]
        status = "DEVIATION_DETECTED" if any(item["status"] == "DEVIATION" for item in rows) else "EVIDENCE_INCOMPLETE" if missing else "POTENTIAL_MATCH"
        return {
            "status": status, "events": rows, "missing_expected": missing, "impact_signals": signals,
            "warning": "A matching Activity Log operation is evidence of an attempted/succeeded control-plane request, not proof of intended resource state",
        }

    def _pim_support(self, event: dict[str, Any], change: dict[str, Any], access: dict[str, Any]) -> tuple[bool, bool]:
        principal = _norm(event.get("caller_principal_id"))
        signature = (_norm(_operation(event)), _norm(event.get("resource_id")))
        pim_by_id = {item.get("pim_request_id"): item for item in self.repository.pim_requests() if item.get("change_id") == change.get("change_id")}
        matching_assessments = []
        for assessment in access.get("pim_assessments") or []:
            pim = pim_by_id.get(assessment.get("pim_request_id"))
            if pim and _norm(pim.get("principal_id")) == principal:
                matching_assessments.append(assessment)
        if not matching_assessments:
            return False, False
        supported = any(
            signature in {(_norm(item.get("operation")), _norm(item.get("resource_id"))) for item in assessment.get("supported_operations") or []}
            for assessment in matching_assessments
        )
        complete = all(assessment.get("overall_status") not in {"NEED_MORE_INFO", "INSUFFICIENT_ACCESS"} for assessment in matching_assessments)
        return supported, complete

    def _assess_event(self, event: dict[str, Any], change: dict[str, Any], access: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        findings: list[dict[str, Any]] = []
        change_id = str(change["change_id"])
        operation, resource = _norm(_operation(event)), _norm(event.get("resource_id"))
        expected = change.get("expected") or []
        operation_matches = [item for item in expected if _norm(item.get("operation")) == operation]
        exact = next((item for item in operation_matches if _norm(item.get("resource_id")) == resource), None)

        if _norm(change.get("state")) != "approved":
            findings.append(_finding("UNAPPROVED_CHANGE", "The correlated change is not approved.", event, change_id=change_id, recommendation="Obtain change approval before executing infrastructure modifications."))
        try:
            occurred, start, end = parse_utc(event["event_timestamp"]), parse_utc(change["start"]), parse_utc(change["end"])
            if not start <= occurred <= end:
                findings.append(_finding("EXECUTED_OUTSIDE_WINDOW", "The activity occurred outside the approved maintenance window.", event, change_id=change_id, recommendation="Execute only within an approved change window."))
        except (KeyError, TypeError, ValueError):
            findings.append(_finding("INSUFFICIENT_AUDIT_EVIDENCE", "The observed or approved timestamp could not be validated.", event, severity="MEDIUM", confidence="insufficient", change_id=change_id, recommendation="Provide valid timezone-aware change and Activity Log timestamps."))

        allowed = _authorized(change)
        authorized_ids = {_norm(item.get("principal_id")) for item in allowed}
        if _norm(event.get("caller_principal_id")) not in authorized_ids:
            findings.append(_finding("UNAUTHORIZED_IMPLEMENTER", "The Activity Log principal is not an authorized implementer for the change.", event, change_id=change_id, recommendation="Confirm the actor's authorization or update the approved implementer list before execution."))
        if exact and exact.get("authorized_principal_id") and _norm(exact["authorized_principal_id"]) != _norm(event.get("caller_principal_id")):
            findings.append(_finding("UNAUTHORIZED_IMPLEMENTER", "The operation was assigned to a different authorized principal.", event, change_id=change_id, recommendation="Use the principal explicitly assigned to this operation."))

        if not operation_matches:
            findings.append(_finding("UNAPPROVED_OPERATION", "The observed Azure operation is not documented in the approved change.", event, change_id=change_id, recommendation="Investigate the operation and obtain approval before further modification."))
            findings.append(_finding("UNEXPECTED_ADDITIONAL_OPERATION", "Additional administrative activity was observed beyond approved intent.", event, change_id=change_id, recommendation="Reconcile the extra operation with the approved implementation plan."))
        elif exact is None:
            findings.append(_finding("WRONG_TARGET_RESOURCE", "The operation matched approved intent, but the Azure resource did not.", event, change_id=change_id, recommendation="Verify the target resource and correct the implementation or approved record."))

        if _norm(_status(event)) != "succeeded":
            findings.append(_finding("FAILED_EXECUTION", "The Azure operation did not complete successfully.", event, change_id=change_id, recommendation="Resolve the failure and collect successful execution evidence before closure."))

        authorization = event.get("authorization") or {}
        action, scope = authorization.get("action"), authorization.get("scope")
        if not action or not scope:
            findings.append(_finding("INSUFFICIENT_AUDIT_EVIDENCE", "Activity Log authorization action or scope is unavailable.", event, severity="MEDIUM", confidence="insufficient", change_id=change_id, recommendation="Review additional Azure authorization and assignment evidence."))
        elif _norm(action) != operation or not _scope_covers(str(scope), str(event.get("resource_id") or "")):
            findings.append(_finding("ROLE_OR_SCOPE_MISMATCH", "Activity Log authorization metadata does not support the observed operation and resource.", event, change_id=change_id, recommendation="Reconcile the authorization action and scope with the intended Azure resource."))

        pim_supported, pim_complete = self._pim_support(event, change, access)
        if not pim_supported:
            confidence = "insufficient" if not access.get("pim_assessments") else "confirmed"
            findings.append(_finding("ROLE_OR_SCOPE_MISMATCH", "Available PIM/RBAC evidence does not support this operation for the observed principal.", event, severity="MEDIUM" if confidence == "insufficient" else "HIGH", confidence=confidence, change_id=change_id, recommendation="Review the principal's PIM activation, effective role permissions, and resource scope."))
        elif not pim_complete or access.get("overall_status") in {"OVERPRIVILEGED", "MANUAL_REVIEW_REQUIRED"}:
            findings.append(_finding("ROLE_OR_SCOPE_MISMATCH", "PIM/RBAC evidence supports the operation but contains role, scope, or duration concerns.", event, severity="MEDIUM", confidence="possible", change_id=change_id, recommendation="Resolve the access-assurance findings before closing the change."))

        successful_exact = _norm(_status(event)) == "succeeded" and exact is not None
        if successful_exact and not findings:
            findings.append(_finding("COMPLIANT_EXECUTION", "The observed operation matches approved identity, operation, resource, window, and access evidence.", event, severity="INFO", change_id=change_id, recommendation="Retain the linked evidence with the change record."))
        return findings, successful_exact

    def _response(self, *, mode: str, evaluated: datetime, events: list[dict[str, Any]], findings: list[dict[str, Any]],
                  matches: dict[str, tuple[str | None, str]], change: dict[str, Any] | None = None,
                  user: dict[str, Any] | None = None, period_start: datetime | None = None) -> dict[str, Any]:
        adverse = [item for item in findings if item["severity"] == "HIGH" and item["confidence"] == "confirmed"]
        compliant = [item for item in findings if item["category"] == "COMPLIANT_EXECUTION"]
        uncertain = [item for item in findings if item["confidence"] in {"possible", "insufficient"}]
        overall = "MIXED" if adverse and compliant else "NON_COMPLIANT" if adverse else "REVIEW_REQUIRED" if uncertain else "COMPLIANT" if compliant else "NO_RELEVANT_ACTIVITY"
        timeline = []
        for event in sorted(events, key=lambda item: item.get("event_timestamp") or ""):
            linked, classification = matches.get(event["event_data_id"], (None, "UNMATCHED"))
            deviations = [item["category"] for item in findings if event["event_data_id"] in item["event_ids"]]
            timeline.append({
                "event_data_id": event.get("event_data_id"), "event_timestamp": event.get("event_timestamp"),
                "caller": event.get("caller"), "caller_principal_id": event.get("caller_principal_id"),
                "operation": _operation(event), "resource_id": event.get("resource_id"),
                "correlation_id": event.get("correlation_id"), "status": _status(event),
                "sub_status": (event.get("sub_status") or {}).get("value"),
                "change_id": linked, "change_match": classification, "deviations": deviations,
            })
        recommendations = list(dict.fromkeys(item["recommendation"] for item in findings))
        limitations = [
            "Azure Activity Logs evidence operations, not final resource configuration.",
            "Correlation IDs are treated as audit identifiers and not as ServiceNow change numbers.",
            "Synthetic evidence is read-only and does not represent a live Azure connection.",
        ]
        return {
            "schema_version": SCHEMA_VERSION, "investigation_id": f"AZ-EXEC-{uuid4().hex[:12].upper()}",
            "provider": "azure", "mode": mode, "change_id": change.get("change_id") if change else None,
            "user": user, "evaluation_timestamp": utc_text(evaluated),
            "period_start": utc_text(period_start) if period_start else None, "period_end": utc_text(evaluated),
            "overall_status": overall, "findings": findings,
            "event_ids": [item["event_data_id"] for item in events],
            "confidence": "limited" if uncertain else "high" if events else "none",
            "timeline": timeline, "expected_operations": (change or {}).get("expected", []),
            "observed_operations": timeline,
            "evidence": [{"event_data_id": item["event_data_id"], "correlation_id": item.get("correlation_id")} for item in events],
            "recommendations": recommendations, "limitations": limitations,
        }

    def assess_change(self, change_id: str, evaluation_timestamp: datetime | None = None, scenario_id: str | None = None) -> dict[str, Any]:
        scenario = self._scenario(scenario_id, "change")
        change = self._change(change_id)
        if scenario and scenario.get("change_id") != change_id: raise AzureScenarioNotFound(scenario_id or "")
        evaluated = (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
        candidates = self._scenario_events(scenario)
        if scenario is None:
            try:
                near_start, near_end = parse_utc(change["start"]) - timedelta(days=1), parse_utc(change["end"]) + timedelta(days=1)
                candidates = [event for event in candidates if near_start <= parse_utc(event["event_timestamp"]) <= near_end and _event_score(event, change)[0] >= 5]
            except (KeyError, TypeError, ValueError):
                candidates = []
        events = [item for item in candidates if parse_utc(item["event_timestamp"]) <= evaluated]
        access = self.access_service.validate_access(change_id)
        findings: list[dict[str, Any]] = []
        covered: set[tuple[str, str]] = set()
        matches: dict[str, tuple[str | None, str]] = {}
        for event in events:
            _, classification = _event_score(event, change)
            matches[event["event_data_id"]] = (change_id, classification)
            event_findings, successful = self._assess_event(event, change, access)
            findings.extend(event_findings)
            if successful: covered.add((_norm(_operation(event)), _norm(event.get("resource_id"))))
        for expected in change.get("expected") or []:
            signature = (_norm(expected.get("operation")), _norm(expected.get("resource_id")))
            if signature not in covered:
                findings.append(_finding("EXPECTED_OPERATION_MISSING", f"No successful matching Activity Log event was observed for {expected.get('operation')} on {expected.get('resource_id')}; this does not prove the operation was not performed.", severity="MEDIUM", confidence="insufficient", change_id=change_id, recommendation="Collect additional execution or state evidence before closing the change."))
        if not events:
            findings.insert(0, _finding("NO_EXECUTION_EVIDENCE", "No relevant Azure Activity Log event was found for the change; absence of evidence is not proof of non-execution.", severity="MEDIUM", confidence="insufficient", change_id=change_id, recommendation="Obtain Activity Log or provider state evidence for the approved window."))
        response = self._response(mode="change", evaluated=evaluated, events=events, findings=findings, matches=matches, change=change)
        if scenario and scenario.get("source") == "v1":
            response["v1_assessment"] = self._v1_assessment(change, events)
            response["overall_status"] = response["v1_assessment"]["status"]
        return response

    def assess_user(self, identity: str, window_days: int = 10, evaluation_timestamp: datetime | None = None, scenario_id: str | None = None) -> dict[str, Any]:
        scenario = self._scenario(scenario_id, "user")
        user = self._resolve_identity(identity)
        if scenario and _norm(scenario.get("user_identity")) not in {_norm(user.get("principal_id")), _norm(user.get("principal_name"))}:
            raise AzureScenarioNotFound(scenario_id or "")
        evaluated = (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
        period_start = evaluated - timedelta(days=window_days)
        events = [event for event in self._scenario_events(scenario) if _norm(event.get("caller_principal_id")) == _norm(user.get("principal_id")) and period_start <= parse_utc(event["event_timestamp"]) <= evaluated]
        changes = self.repository.changes()
        access_cache: dict[str, dict[str, Any]] = {}
        findings: list[dict[str, Any]] = []
        matches: dict[str, tuple[str | None, str]] = {}
        for event in events:
            scored = sorted(((_event_score(event, change)[0], change) for change in changes), key=lambda item: item[0], reverse=True)
            score, change = scored[0]
            _, classification = _event_score(event, change)
            if score >= 5:
                change_id = str(change["change_id"])
                matches[event["event_data_id"]] = (change_id, classification)
                access_cache.setdefault(change_id, self.access_service.validate_access(change_id))
                event_findings, _ = self._assess_event(event, change, access_cache[change_id])
                findings.extend(event_findings)
            else:
                matches[event["event_data_id"]] = (None, "UNMATCHED")
                if not _operation(event).casefold().endswith("/read"):
                    findings.append(_finding("POSSIBLE_UNAPPROVED_ACTIVITY", "Administrative activity has no sufficiently supported approved-change match and requires review.", event, severity="MEDIUM", confidence="possible", recommendation="Review the activity and link it to an approved change only when supported by evidence."))
        return self._response(mode="user", evaluated=evaluated, period_start=period_start, events=events, findings=findings, matches=matches, user=user)
