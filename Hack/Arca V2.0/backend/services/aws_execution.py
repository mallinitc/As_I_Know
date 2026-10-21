from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from backend.errors import AwsChangeNotFound, AwsIdentityNotFound, AwsScenarioNotFound
from backend.repositories.aws import AwsRepository
from backend.services.timestamps import parse_utc, utc_text

SCHEMA_VERSION = 1

def _norm(value: Any) -> str: return str(value or "").strip().casefold()
def _identity(event: dict[str, Any]) -> dict[str, Any]: return event.get("userIdentity") or {"userName": event.get("actor"), "email": event.get("actor")}
def _aliases(event: dict[str, Any]) -> set[str]:
    identity = _identity(event); session = identity.get("sessionContext") or {}; issuer = session.get("sessionIssuer") or {}
    values = [identity.get("principalId"), identity.get("arn"), identity.get("userName"), identity.get("email"), session.get("sourceIdentity"), issuer.get("principalId"), issuer.get("arn"), issuer.get("userName"), event.get("actor")]
    return {_norm(item) for item in values if item}
def _actor(event: dict[str, Any]) -> str:
    identity = _identity(event); session = identity.get("sessionContext") or {}
    return str(session.get("sourceIdentity") or identity.get("email") or identity.get("userName") or identity.get("arn") or event.get("actor") or "Unknown")
def _resources(event: dict[str, Any]) -> list[str]:
    result = [str(item.get("ARN")) if isinstance(item, dict) else str(item) for item in (event.get("resources") or []) if (item.get("ARN") if isinstance(item, dict) else item)]
    policy = (event.get("requestParameters") or {}).get("policyArn")
    if policy and str(policy).startswith("arn:"): result.append(str(policy))
    return list(dict.fromkeys(result))
def _explicit_change(event: dict[str, Any]) -> str | None:
    value = (event.get("additionalEventData") or {}).get("changeId") or event.get("changeId")
    return str(value).upper() if value else None
def _finding(category: str, message: str, event: dict[str, Any] | None = None, *, severity: str = "HIGH", confidence: str = "confirmed", change_id: str | None = None, recommendation: str) -> dict[str, Any]:
    return {"category": category, "severity": severity, "confidence": confidence, "message": message, "event_ids": [event["eventID"]] if event else [], "change_id": change_id, "recommendation": recommendation}

class AwsExecutionService:
    def __init__(self, repository: AwsRepository | None = None) -> None: self.repository = repository or AwsRepository()
    def scenarios(self) -> list[dict[str, Any]]: return self.repository.execution_scenarios()
    def _scenario(self, scenario_id: str | None, mode: str) -> dict[str, Any] | None:
        if not scenario_id: return None
        item = next((x for x in self.scenarios() if x.get("scenario_id") == scenario_id and x.get("mode") == mode), None)
        if not item: raise AwsScenarioNotFound(scenario_id)
        return item
    def _change(self, change_id: str) -> dict[str, Any]:
        item = next((x for x in self.repository.changes() if x.get("change_id") == change_id), None)
        if not item: raise AwsChangeNotFound(change_id)
        return item
    def _events(self, scenario: dict[str, Any] | None) -> list[dict[str, Any]]:
        items = self.repository.execution_events()
        if not scenario: return items
        ids = set(scenario.get("event_ids") or [])
        return [x for x in items if x.get("eventID") in ids]
    def _resolve(self, value: str) -> dict[str, Any]:
        needle = _norm(value); matches = [e for e in self.repository.execution_events() if needle in _aliases(e)]
        if not matches: raise AwsIdentityNotFound(value)
        first = _identity(matches[0]); session = first.get("sessionContext") or {}; issuer = session.get("sessionIssuer") or {}
        return {"query": value, "principal_id": first.get("principalId"), "arn": first.get("arn"), "username": first.get("userName"), "email": first.get("email"), "issuer_arn": issuer.get("arn"), "source_identity": session.get("sourceIdentity"), "aliases": sorted(set().union(*(_aliases(e) for e in matches)))}
    def _classification(self, event: dict[str, Any], change: dict[str, Any]) -> str:
        explicit = _explicit_change(event)
        if explicit: return "MATCHED" if explicit == change.get("change_id") else "UNMATCHED"
        expected = change.get("expected") or []; resources = {_norm(x) for x in _resources(event)}
        actor = _norm(change.get("actor")) in _aliases(event); operation = any(_norm(x.get("eventName")) == _norm(event.get("eventName")) for x in expected); resource = any(_norm(x.get("resource")) in resources for x in expected if x.get("resource"))
        in_window = False
        try: in_window = parse_utc(change["start"]) <= parse_utc(event["eventTime"]) <= parse_utc(change["end"])
        except (KeyError, TypeError, ValueError): pass
        score = sum((actor, operation, resource, in_window))
        return "MATCHED" if score == 4 else "POSSIBLE_MATCH" if score >= 3 else "UNMATCHED"
    def _assess(self, event: dict[str, Any], change: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        findings: list[dict[str, Any]] = []; cid = str(change["change_id"]); expected = change.get("expected") or []; resources = _resources(event); event_name = _norm(event.get("eventName")); resource_norms = {_norm(x) for x in resources}
        operation_matches = [x for x in expected if _norm(x.get("eventName")) == event_name]
        exact = next((x for x in operation_matches if _norm(x.get("resource")) in resource_norms), None)
        try:
            if not parse_utc(change["start"]) <= parse_utc(event["eventTime"]) <= parse_utc(change["end"]): findings.append(_finding("EXECUTED_OUTSIDE_WINDOW", "The API activity occurred outside the approved UTC maintenance window.", event, change_id=cid, recommendation="Execute only during the approved change window."))
        except (KeyError, TypeError, ValueError): findings.append(_finding("INSUFFICIENT_AUDIT_EVIDENCE", "Execution timing could not be validated.", event, severity="MEDIUM", confidence="insufficient", change_id=cid, recommendation="Provide timezone-aware change and CloudTrail timestamps."))
        if _norm(change.get("actor")) not in _aliases(event): findings.append(_finding("UNAUTHORIZED_IMPLEMENTER", "The CloudTrail principal is not the approved implementer.", event, change_id=cid, recommendation="Confirm the principal and assumed-role source identity before closure."))
        identity = _identity(event); arn = str(identity.get("arn") or ""); recipient = str(event.get("recipientAccountId") or "")
        if arn.startswith("arn:") and recipient and f"::{recipient}:" not in arn and ":sts::" in arn: findings.append(_finding("ROLE_OR_PRINCIPAL_MISMATCH", "The session originated from a different AWS account.", event, change_id=cid, recommendation="Review cross-account trust and approved principal evidence."))
        if not resources: findings.append(_finding("INSUFFICIENT_AUDIT_EVIDENCE", "No reliable target resource ARN is present in CloudTrail resources or request parameters.", event, severity="MEDIUM", confidence="insufficient", change_id=cid, recommendation="Collect resource-level CloudTrail or service audit evidence."))
        if not operation_matches:
            findings += [_finding("UNAPPROVED_OPERATION", "The API operation is not documented in the approved change.", event, change_id=cid, recommendation="Investigate and obtain approval for additional operations."), _finding("UNEXPECTED_ADDITIONAL_OPERATION", "Additional API activity exceeded the approved implementation plan.", event, change_id=cid, recommendation="Reconcile the additional operation with change intent.")]
        elif resources and exact is None: findings.append(_finding("WRONG_TARGET_RESOURCE", "The operation matched, but its resource ARN did not.", event, change_id=cid, recommendation="Verify account, Region, and target ARN before execution."))
        failed = bool(event.get("errorCode") or event.get("errorMessage"))
        if failed: findings.append(_finding("FAILED_EXECUTION", "CloudTrail records an API error; this is not successful implementation evidence.", event, change_id=cid, recommendation="Resolve the API failure and capture successful evidence."))
        successful = bool(exact and not failed)
        adverse = [x for x in findings if x["severity"] == "HIGH"]
        if successful and not adverse: findings.append(_finding("COMPLIANT_EXECUTION", "The successful API event matches approved actor, operation, target, and window.", event, severity="INFO", change_id=cid, recommendation="Retain this evidence; separately verify final resource state."))
        return findings, successful
    def _response(self, mode: str, evaluated: datetime, events: list[dict[str, Any]], findings: list[dict[str, Any]], matches: dict[str, tuple[str | None, str]], change: dict[str, Any] | None = None, user: dict[str, Any] | None = None, period_start: datetime | None = None) -> dict[str, Any]:
        adverse = any(x["severity"] == "HIGH" and x["confidence"] == "confirmed" for x in findings); compliant = any(x["category"] == "COMPLIANT_EXECUTION" for x in findings); uncertain = any(x["confidence"] != "confirmed" for x in findings)
        overall = "MIXED" if adverse and compliant else "NON_COMPLIANT" if adverse else "REVIEW_REQUIRED" if uncertain else "COMPLIANT" if compliant else "NO_RELEVANT_ACTIVITY"
        timeline = []
        for event in sorted(events, key=lambda x: x.get("eventTime") or ""):
            cid, classification = matches.get(str(event.get("eventID")), (None, "UNMATCHED")); resources = _resources(event)
            timeline.append({"event_id": event.get("eventID"), "event_time": event.get("eventTime"), "event_source": event.get("eventSource"), "operation": event.get("eventName"), "actor": _actor(event), "principal_arn": _identity(event).get("arn"), "resources": resources, "aws_region": event.get("awsRegion"), "account_id": event.get("recipientAccountId"), "status": "FAILED" if event.get("errorCode") or event.get("errorMessage") else "SUCCESS", "change_id": cid, "change_match": classification, "deviations": [x["category"] for x in findings if event.get("eventID") in x["event_ids"]]})
        return {"schema_version": SCHEMA_VERSION, "investigation_id": f"AWS-EXEC-{uuid4().hex[:12].upper()}", "provider": "aws", "mode": mode, "change_id": change.get("change_id") if change else None, "user": user, "evaluation_timestamp": utc_text(evaluated), "period_start": utc_text(period_start) if period_start else None, "period_end": utc_text(evaluated), "overall_status": overall, "findings": findings, "event_ids": [str(x.get("eventID")) for x in events], "confidence": "limited" if uncertain else "high" if events else "none", "timeline": timeline, "expected_operations": (change or {}).get("expected", []), "observed_operations": timeline, "evidence": [{"eventID": x.get("eventID"), "eventTime": x.get("eventTime")} for x in events], "recommendations": list(dict.fromkeys(x["recommendation"] for x in findings)), "limitations": ["CloudTrail API success does not verify final AWS resource state.", "CloudTrail does not inherently contain ServiceNow change IDs; explicit synthetic links are used only when present.", "Missing events are insufficient proof that an operation never occurred."]}
    def assess_change(self, change_id: str, evaluation_timestamp: datetime | None = None, scenario_id: str | None = None) -> dict[str, Any]:
        scenario = self._scenario(scenario_id, "change"); change = self._change(change_id)
        if scenario and scenario.get("change_id") != change_id: raise AwsScenarioNotFound(scenario_id or "")
        evaluated = parse_utc(evaluation_timestamp) if isinstance(evaluation_timestamp, str) else (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc); candidates = self._events(scenario)
        if not scenario:
            candidates = [e for e in candidates if self._classification(e, change) != "UNMATCHED"]
        events = [e for e in candidates if parse_utc(e["eventTime"]) <= evaluated]; findings: list[dict[str, Any]] = []; matches = {}; covered: set[tuple[str, str]] = set()
        for event in events:
            classification = self._classification(event, change); matches[event["eventID"]] = (change_id, classification); event_findings, successful = self._assess(event, change); findings.extend(event_findings)
            if successful:
                for expected in change.get("expected") or []:
                    if _norm(expected.get("eventName")) == _norm(event.get("eventName")) and _norm(expected.get("resource")) in {_norm(x) for x in _resources(event)}: covered.add((_norm(expected.get("eventName")), _norm(expected.get("resource"))))
        for expected in change.get("expected") or []:
            key = (_norm(expected.get("eventName")), _norm(expected.get("resource")))
            if key not in covered: findings.append(_finding("EXPECTED_OPERATION_MISSING", "No successful CloudTrail evidence covers an expected operation and target; absence is not proof it never occurred.", change_id=change_id, confidence="insufficient", severity="MEDIUM", recommendation="Collect additional service and resource-state evidence."))
        if not events: findings.append(_finding("NO_EXECUTION_EVIDENCE", "No relevant CloudTrail evidence was found.", change_id=change_id, confidence="insufficient", severity="MEDIUM", recommendation="Verify CloudTrail coverage and collect service audit evidence."))
        return self._response("change", evaluated, events, findings, matches, change=change)
    def assess_user(self, identity: str, window_days: int = 10, evaluation_timestamp: datetime | None = None, scenario_id: str | None = None) -> dict[str, Any]:
        scenario = self._scenario(scenario_id, "user"); user = self._resolve(identity); evaluated = parse_utc(evaluation_timestamp) if isinstance(evaluation_timestamp, str) else (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc); start = evaluated - timedelta(days=window_days); candidates = self._events(scenario)
        events = [e for e in candidates if _norm(identity) in _aliases(e) and start <= parse_utc(e["eventTime"]) <= evaluated]; findings: list[dict[str, Any]] = []; matches = {}
        for event in events:
            explicit = _explicit_change(event); change = next((x for x in self.repository.changes() if x.get("change_id") == explicit), None) if explicit else None
            if not change:
                candidates_for_event = [(x, self._classification(event, x)) for x in self.repository.changes()]; change = next((x for x, c in candidates_for_event if c in {"MATCHED", "POSSIBLE_MATCH"}), None)
            if change:
                classification = self._classification(event, change); matches[event["eventID"]] = (change["change_id"], classification); event_findings, _ = self._assess(event, change); findings.extend(event_findings)
            else:
                matches[event["eventID"]] = (None, "UNMATCHED")
                if not event.get("readOnly"): findings.append(_finding("POSSIBLE_UNAPPROVED_ACTIVITY", "Administrative activity has no supported approved-change match.", event, severity="MEDIUM", confidence="possible", recommendation="Investigate the activity and link it only with supporting evidence."))
        return self._response("user", evaluated, events, findings, matches, user=user, period_start=start)
