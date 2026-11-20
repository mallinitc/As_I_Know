from __future__ import annotations

from datetime import timedelta
from fnmatch import fnmatchcase
from typing import Any

from backend.errors import AwsChangeNotFound
from backend.repositories.aws import AwsRepository
from backend.services.timestamps import parse_utc


SCHEMA_VERSION = 1
EVENT_TO_ACTION = {
    "PutBucketPolicy": "s3:PutBucketPolicy", "GetObject": "s3:GetObject",
    "PutObject": "s3:PutObject", "ListBucket": "s3:ListBucket",
    "TerminateInstances": "ec2:TerminateInstances", "StartInstances": "ec2:StartInstances",
    "StopInstances": "ec2:StopInstances", "RebootInstances": "ec2:RebootInstances",
    "CreateTags": "ec2:CreateTags",
}
RESOURCE_SCOPED_ACTIONS = set(EVENT_TO_ACTION.values())


def _finding(category: str, field: str, explanation: str, *, actual: Any = None,
             expected: Any = None, recommendation: str, severity: str = "ERROR",
             evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "category": category, "field": field, "severity": severity,
        "explanation": explanation, "actual": actual, "expected": expected,
        "recommendation": recommendation, "evidence_ids": evidence_ids or [],
    }


def _list(value: Any) -> list[Any]:
    if value is None: return []
    return value if isinstance(value, list) else [value]


def _action_matches(required: str, pattern: str) -> bool:
    return fnmatchcase(required.casefold(), pattern.casefold())


def _resource_matches(required: str, pattern: str) -> bool:
    return fnmatchcase(required, pattern)


def _statement_applies(statement: dict[str, Any], action: str, resource: str) -> bool:
    actions = [str(item) for item in _list(statement.get("Action"))]
    not_actions = [str(item) for item in _list(statement.get("NotAction"))]
    action_match = any(_action_matches(action, item) for item in actions) if actions else not any(_action_matches(action, item) for item in not_actions)
    resources = [str(item) for item in _list(statement.get("Resource"))]
    not_resources = [str(item) for item in _list(statement.get("NotResource"))]
    resource_match = any(_resource_matches(resource, item) for item in resources) if resources else not any(_resource_matches(resource, item) for item in not_resources)
    return action_match and resource_match


def validate_change_quality(change: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    required = {
        "change_id": change.get("change_id"), "description": change.get("description"),
        "implementer": change.get("actor"), "environment": change.get("environment"),
        "start": change.get("start"), "end": change.get("end"), "expected": change.get("expected"),
    }
    for field, value in required.items():
        if value in (None, "", []):
            findings.append(_finding("MISSING_MANDATORY_FIELD", field, f"The {field.replace('_', ' ')} is missing.", actual=value, expected="A documented value", recommendation=f"Add the {field.replace('_', ' ')} before implementation."))
    if "state" in change and str(change.get("state") or "").casefold() != "approved":
        findings.append(_finding("CHANGE_NOT_APPROVED", "state", "The represented approval state is not approved.", actual=change.get("state"), expected="approved", recommendation="Obtain formal change approval before implementation."))
    start = end = None
    for field in ("start", "end"):
        if change.get(field):
            try:
                parsed = parse_utc(change[field])
                if field == "start": start = parsed
                else: end = parsed
            except (TypeError, ValueError):
                findings.append(_finding("INVALID_TIMESTAMP", field, "The timestamp is invalid or lacks a timezone.", actual=change[field], expected="ISO 8601 with explicit timezone", recommendation=f"Provide a valid timezone-aware {field} timestamp."))
    if start and end and start >= end:
        findings.append(_finding("INVALID_CHANGE_WINDOW", "change_window", "The maintenance window ends before or at its start.", actual={"start": change.get("start"), "end": change.get("end")}, expected="end later than start", recommendation="Correct the approved maintenance-window timestamps."))
    for index, operation in enumerate(change.get("expected") or []):
        if not operation.get("eventName"):
            findings.append(_finding("MISSING_EXPECTED_OPERATION", f"expected[{index}].eventName", "An expected operation name is missing.", recommendation="Document the AWS operation."))
        if not operation.get("resource"):
            findings.append(_finding("MISSING_TARGET_RESOURCE", f"expected[{index}].resource", "An expected operation is missing its target ARN.", recommendation="Document the full target AWS ARN."))
    missing = list(dict.fromkeys(item["field"] for item in findings if item["category"].startswith("MISSING_")))
    if any(item["category"] == "INVALID_CHANGE_WINDOW" for item in findings): status = "INCONSISTENT"
    elif missing: status = "INCOMPLETE"
    elif findings: status = "MANUAL_REVIEW_REQUIRED"
    else: status = "VALID"
    return {
        "schema_version": SCHEMA_VERSION, "provider": "aws", "stage": "change",
        "change_id": change.get("change_id") or "UNKNOWN", "overall_status": status,
        "findings": findings, "missing_information": missing,
        "recommendations": list(dict.fromkeys(item["recommendation"] for item in findings)),
        "evidence": [{"type": "change", "evidence_id": change.get("change_id")}], "change": change,
    }


class AwsValidationService:
    def __init__(self, repository: AwsRepository | None = None) -> None:
        self.repository = repository or AwsRepository()

    def list_changes(self) -> list[dict[str, Any]]:
        return self.repository.changes()

    def list_demo_scenarios(self) -> list[dict[str, Any]]:
        return self.repository.demo_scenarios()

    def _change(self, change_id: str) -> dict[str, Any]:
        change = next((item for item in self.repository.changes() if item.get("change_id") == change_id), None)
        if change is None: raise AwsChangeNotFound(change_id)
        return change

    def validate_change(self, change_id: str) -> dict[str, Any]:
        return validate_change_quality(self._change(change_id))

    def _policies_for(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        policy_ids = set(request.get("policy_ids") or [])
        policies = [item for item in self.repository.policy_evidence() if item.get("policy_id") in policy_ids]
        if policies or policy_ids:
            return policies
        actions, resources = request.get("actions") or [], request.get("resources") or []
        if not actions or not resources:
            return []
        return [{
            "policy_id": f"aws-inline-{request.get('change_id')}", "change_id": request.get("change_id"),
            "policy_type": "identity", "document": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": actions, "Resource": resources}]},
        }]

    def validate_access(self, change_id: str) -> dict[str, Any]:
        change = self._change(change_id)
        required_actions = {
            action.casefold() for item in (change.get("expected") or [])
            if (action := EVENT_TO_ACTION.get(str(item.get("eventName") or "")))
        }
        request = next((item for item in self.repository.access_requests() if item.get("change_id") == change_id), None)
        findings: list[dict[str, Any]] = []
        evaluations: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = [{"type": "change", "evidence_id": change_id}]
        policies = self._policies_for(request or {}) if request else []
        if request:
            evidence.append({"type": "access_request", "evidence_id": request.get("request_id") or f"access-{change_id}"})
        if not request:
            findings.append(_finding("MISSING_ACCESS_REQUEST", "access_request", "No AWS access request is linked to the change.", expected=change_id, recommendation="Provide the access request and requested IAM evidence."))
        if not policies:
            findings.append(_finding("MISSING_POLICY_EVIDENCE", "policy_evidence", "No IAM policy document is available for deterministic evaluation.", expected="Identity-based policy evidence", recommendation="Provide the exact IAM policy documents and attachment evidence."))
        for policy in policies:
            evidence.append({"type": policy.get("policy_type"), "evidence_id": policy.get("policy_id")})

        identity_policies = [item for item in policies if item.get("policy_type") == "identity"]
        boundaries = [item for item in policies if item.get("policy_type") == "permissions_boundary"]
        unknown_action = False
        denied = False
        insufficient = False
        manual = False
        broad = False

        for expected in change.get("expected") or []:
            event_name, resource = str(expected.get("eventName") or ""), str(expected.get("resource") or "")
            action = EVENT_TO_ACTION.get(event_name)
            if not action:
                unknown_action = manual = True
                findings.append(_finding("UNKNOWN_IAM_ACTION", "expected_operation", "The AWS operation is not present in the supported deterministic action catalog.", actual=event_name, expected="Supported operation-to-IAM-action mapping", recommendation="Perform manual IAM review and add a verified mapping before automation."))
                evaluations.append({"event_name": event_name, "iam_action": None, "resource": resource or None, "decision": "MANUAL_REVIEW", "allow_evidence": [], "deny_evidence": []})
                continue
            if not resource:
                insufficient = True
                evaluations.append({"event_name": event_name, "iam_action": action, "resource": None, "decision": "NEED_MORE_INFO", "allow_evidence": [], "deny_evidence": []})
                continue

            allow_ids: list[str] = []
            deny_ids: list[str] = []
            unsupported_ids: list[str] = []
            for policy in policies:
                policy_id = str(policy.get("policy_id"))
                for statement in _list((policy.get("document") or {}).get("Statement")):
                    if not isinstance(statement, dict) or not _statement_applies(statement, action, resource): continue
                    if statement.get("Condition"):
                        unsupported_ids.append(policy_id)
                        continue
                    if str(statement.get("Effect") or "").casefold() == "deny": deny_ids.append(policy_id)
                    elif str(statement.get("Effect") or "").casefold() == "allow" and policy.get("policy_type") == "identity": allow_ids.append(policy_id)
            if unsupported_ids:
                manual = True
                findings.append(_finding("UNSUPPORTED_POLICY_CONDITION", "Condition", "A matching policy statement uses condition context not supported by the deterministic evaluator.", actual=unsupported_ids, expected="Supported and supplied condition context", recommendation="Perform manual review of condition operators, keys, and request context.", severity="REVIEW", evidence_ids=unsupported_ids))
            if deny_ids:
                denied = True
                decision = "EXPLICIT_DENY"
                findings.append(_finding("EXPLICIT_DENY", "policy", "An applicable explicit Deny overrides matching Allow evidence.", actual=deny_ids, expected="No applicable explicit Deny", recommendation="Do not proceed unless the deny is intentionally and safely revised through governance.", evidence_ids=deny_ids))
            elif unsupported_ids and not allow_ids:
                decision = "MANUAL_REVIEW"
            elif not allow_ids:
                insufficient = True
                decision = "IMPLICIT_DENY"
                findings.append(_finding("INSUFFICIENT_PERMISSION", "Action", "No supported identity-based Allow covers the required action and resource.", actual={"action": action, "resource": resource}, expected="Matching Allow statement", recommendation="Add only the required action on the documented ARN.", evidence_ids=[]))
            else:
                boundary_allows = True
                if boundaries:
                    boundary_allows = False
                    for boundary in boundaries:
                        for statement in _list((boundary.get("document") or {}).get("Statement")):
                            if isinstance(statement, dict) and not statement.get("Condition") and str(statement.get("Effect") or "").casefold() == "allow" and _statement_applies(statement, action, resource):
                                boundary_allows = True
                if not boundary_allows:
                    insufficient = True
                    decision = "BOUNDARY_IMPLICIT_DENY"
                    ids = [str(item.get("policy_id")) for item in boundaries]
                    findings.append(_finding("PERMISSION_BOUNDARY_CONSTRAINT", "permissions_boundary", "The permissions boundary does not allow the required action and resource.", actual=ids, expected={"action": action, "resource": resource}, recommendation="Keep the boundary restriction or revise approved access requirements; identity Allow alone is insufficient.", evidence_ids=ids))
                elif unsupported_ids:
                    decision = "MANUAL_REVIEW"
                else:
                    decision = "ALLOWED_BY_AVAILABLE_IDENTITY_EVIDENCE"

            evaluations.append({"event_name": event_name, "iam_action": action, "resource": resource, "decision": decision, "allow_evidence": list(dict.fromkeys(allow_ids)), "deny_evidence": list(dict.fromkeys(deny_ids))})

            for policy in identity_policies:
                policy_id = str(policy.get("policy_id"))
                for statement in _list((policy.get("document") or {}).get("Statement")):
                    if not isinstance(statement, dict) or str(statement.get("Effect") or "").casefold() != "allow": continue
                    if not _statement_applies(statement, action, resource): continue
                    action_patterns = [str(item) for item in _list(statement.get("Action"))]
                    resource_patterns = [str(item) for item in _list(statement.get("Resource"))]
                    wild_actions = [item for item in action_patterns if "*" in item and item.casefold() != action.casefold()]
                    wild_resources = [item for item in resource_patterns if "*" in item and item != resource]
                    if wild_actions:
                        broad = True
                        findings.append(_finding("ACTION_WILDCARD", "Action", "The Allow statement uses an IAM action wildcard broader than documented intent.", actual=wild_actions, expected=action, recommendation="Replace the wildcard with the required IAM action where supported.", severity="WARNING", evidence_ids=[policy_id]))
                    if wild_resources and action in RESOURCE_SCOPED_ACTIONS:
                        broad = True
                        findings.append(_finding("RESOURCE_WILDCARD", "Resource", "The Allow statement uses a resource wildcard broader than the target ARN.", actual=wild_resources, expected=resource, recommendation="Scope the policy to the documented ARN where the action supports resource restrictions.", severity="WARNING", evidence_ids=[policy_id]))
                    extra_actions = [item for item in action_patterns if "*" not in item and item.casefold() not in required_actions]
                    if extra_actions:
                        broad = True
                        findings.append(_finding("EXCESSIVE_PERMISSION", "Action", "The policy includes permissions beyond this documented operation.", actual=extra_actions, expected=action, recommendation="Remove unrelated actions unless separately justified.", severity="WARNING", evidence_ids=[policy_id]))

        if request and change.get("start") and change.get("end") and request.get("duration_minutes") is not None:
            try:
                approved_minutes = int((parse_utc(change["end"]) - parse_utc(change["start"])) / timedelta(minutes=1))
                if int(request["duration_minutes"]) > approved_minutes:
                    broad = True
                    findings.append(_finding("EXCESSIVE_ACCESS_DURATION", "duration_minutes", "Requested access lasts longer than the approved change window.", actual=request["duration_minutes"], expected=approved_minutes, recommendation="Limit temporary access to the approved maintenance window.", severity="WARNING"))
            except (TypeError, ValueError):
                manual = True

        limitations = [
            "Identity-based policy evidence is not a complete AWS effective-permissions calculation.",
            "Service control policies, resource policies, session policies, trust policies, and request condition context are not fully represented unless explicitly supplied.",
        ]
        missing = list(dict.fromkeys(item["field"] for item in findings if item["category"].startswith("MISSING_")))
        if not request or not policies: overall = "NEED_MORE_INFO"
        elif denied: overall = "EXPLICITLY_DENIED"
        elif insufficient: overall = "INSUFFICIENT_ACCESS"
        elif unknown_action or manual: overall = "MANUAL_REVIEW_REQUIRED"
        elif broad: overall = "OVERPRIVILEGED"
        else: overall = "APPROPRIATE_WITH_LIMITATIONS"
        return {
            "schema_version": SCHEMA_VERSION, "provider": "aws", "stage": "access",
            "change_id": change_id, "overall_status": overall,
            "permission_evaluations": evaluations, "findings": findings,
            "missing_information": missing,
            "recommendations": list(dict.fromkeys(item["recommendation"] for item in findings)),
            "evidence": evidence, "limitations": limitations, "change": change, "access_request": request,
        }
