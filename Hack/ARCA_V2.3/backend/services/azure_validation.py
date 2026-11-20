from __future__ import annotations

from fnmatch import fnmatchcase
import re
from typing import Any

from backend.errors import AzureChangeNotFound
from backend.repositories.azure import AzureRepository
from backend.services.timestamps import parse_utc


SCHEMA_VERSION = 1
CHANGE_REFERENCE = re.compile(r"\bCHG-AZ-\d+\b", re.IGNORECASE)


def _finding(category: str, field: str, message: str, *, actual: Any = None,
             expected: Any = None, recommendation: str,
             severity: str = "ERROR", evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "category": category, "field": field, "severity": severity,
        "message": message, "actual": actual, "expected": expected,
        "recommendation": recommendation, "evidence_ids": evidence_ids or [],
    }


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold().rstrip("/")


def _pattern_matches(operation: str, pattern: str) -> bool:
    return fnmatchcase(_norm(operation), _norm(pattern))


def _permission_allows(role: dict[str, Any], operation: str) -> tuple[bool, str | None]:
    for permission in role.get("permissions") or []:
        actions = permission.get("actions") or []
        exclusions = permission.get("not_actions") or permission.get("notActions") or []
        if any(_pattern_matches(operation, pattern) for pattern in actions):
            if not any(_pattern_matches(operation, pattern) for pattern in exclusions):
                return True, "management"
        data_actions = permission.get("data_actions") or permission.get("dataActions") or []
        data_exclusions = permission.get("not_data_actions") or permission.get("notDataActions") or []
        if any(_pattern_matches(operation, pattern) for pattern in data_actions):
            if not any(_pattern_matches(operation, pattern) for pattern in data_exclusions):
                return True, "data"
    return False, None


def _scope_covers(scope: str, resource_id: str) -> bool:
    normalized_scope, normalized_resource = _norm(scope), _norm(resource_id)
    return normalized_resource == normalized_scope or normalized_resource.startswith(normalized_scope + "/")


def _role_breadth(role: dict[str, Any]) -> tuple[int, int]:
    patterns = [
        pattern for permission in role.get("permissions") or []
        for key in ("actions", "data_actions", "dataActions") for pattern in permission.get(key) or []
    ]
    return (sum(pattern == "*" for pattern in patterns), sum(pattern.count("*") for pattern in patterns) + len(patterns))


def validate_change_quality(change: dict[str, Any], resources: list[dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    evidence = [{"type": "servicenow_change", "evidence_id": change.get("sys_id")}]
    mandatory = {
        "change_id": change.get("change_id"), "description": change.get("description"),
        "environment": change.get("environment"), "implementer": (change.get("implementer") or {}).get("principal_id"),
        "start": change.get("start"), "end": change.get("end"), "expected": change.get("expected"),
    }
    labels = {
        "change_id": "change ID", "description": "description", "environment": "environment",
        "implementer": "implementer", "start": "start timestamp", "end": "end timestamp",
        "expected": "expected operations",
    }
    for field, value in mandatory.items():
        if value in (None, "", []):
            findings.append(_finding("MISSING_MANDATORY_FIELD", field, f"The {labels[field]} is missing.", actual=value, expected="A documented value", recommendation=f"Add the {labels[field]} before implementation."))

    if _norm(change.get("state")) != "approved":
        findings.append(_finding("CHANGE_NOT_APPROVED", "state", "The change is not approved for implementation.", actual=change.get("state"), expected="approved", recommendation="Obtain formal change approval before implementation."))

    start = end = None
    for field in ("start", "end"):
        if change.get(field):
            try:
                parsed = parse_utc(change[field])
                if field == "start": start = parsed
                else: end = parsed
            except (TypeError, ValueError):
                findings.append(_finding("INVALID_TIMESTAMP", field, f"The {field} timestamp is invalid or lacks a timezone.", actual=change[field], expected="ISO 8601 with explicit timezone", recommendation=f"Provide a valid UTC or timezone-aware {field} timestamp."))
    if start and end and start >= end:
        findings.append(_finding("INVALID_CHANGE_WINDOW", "change_window", "The maintenance window ends before or at its start.", actual={"start": change.get("start"), "end": change.get("end")}, expected="end later than start", recommendation="Correct the approved maintenance-window timestamps."))

    resource_ids = {_norm(item.get("resource_id")) for item in resources}
    for index, expected in enumerate(change.get("expected") or []):
        if not expected.get("operation"):
            findings.append(_finding("MISSING_EXPECTED_OPERATION", f"expected[{index}].operation", "An expected operation is missing its Azure action.", recommendation="Document the exact Azure Resource Manager operation."))
        target = expected.get("resource_id")
        if not target:
            findings.append(_finding("MISSING_TARGET_RESOURCE", f"expected[{index}].resource_id", "An expected operation is missing its target resource.", recommendation="Document the full Azure resource ID."))
        elif _norm(target) not in resource_ids:
            findings.append(_finding("UNKNOWN_TARGET_RESOURCE", f"expected[{index}].resource_id", "The target is not present in the available Azure resource catalog.", actual=target, expected="Known Azure resource ID", recommendation="Verify the resource ID or provide authoritative inventory evidence.", severity="REVIEW"))

    missing = list(dict.fromkeys(item["field"] for item in findings if item["category"].startswith("MISSING_")))
    if any(item["category"] == "INVALID_CHANGE_WINDOW" for item in findings): status = "INCONSISTENT"
    elif missing: status = "INCOMPLETE"
    elif findings: status = "MANUAL_REVIEW_REQUIRED"
    else: status = "VALID"
    return {
        "schema_version": SCHEMA_VERSION, "provider": "azure", "stage": "change",
        "change_id": change.get("change_id") or "UNKNOWN", "overall_status": status,
        "findings": findings, "missing_information": missing, "evidence": evidence,
        "recommendations": list(dict.fromkeys(item["recommendation"] for item in findings)),
        "change": change,
    }


class AzureValidationService:
    def __init__(self, repository: AzureRepository | None = None) -> None:
        self.repository = repository or AzureRepository()

    def list_changes(self) -> list[dict[str, Any]]:
        return self.repository.changes()

    def list_demo_scenarios(self) -> list[dict[str, Any]]:
        return self.repository.demo_scenarios()

    def _change(self, change_id: str) -> dict[str, Any]:
        change = next((item for item in self.repository.changes() if item.get("change_id") == change_id), None)
        if change is None:
            raise AzureChangeNotFound(change_id)
        return change

    def validate_change(self, change_id: str) -> dict[str, Any]:
        return validate_change_quality(self._change(change_id), self.repository.resources())

    def validate_access(self, change_id: str, pim_request_id: str | None = None) -> dict[str, Any]:
        change = self._change(change_id)
        pims = [item for item in self.repository.pim_requests() if item.get("change_id") == change_id]
        if pim_request_id:
            pims = [item for item in pims if item.get("pim_request_id") == pim_request_id]
        roles = self.repository.role_definitions()
        role_by_id = {_norm(item.get("role_definition_id")): item for item in roles}
        assignments = self.repository.rbac_assignments()
        expected = change.get("expected") or []
        authorized = change.get("authorized_implementers") or [change.get("implementer") or {}]
        authorized_ids = {_norm(item.get("principal_id")) for item in authorized if item.get("principal_id")}
        authorized_names = {_norm(item.get("principal_name")) for item in authorized if item.get("principal_name")}
        assessments: list[dict[str, Any]] = []
        all_findings: list[dict[str, Any]] = []
        covered_signatures: set[tuple[str, str]] = set()
        evidence: list[dict[str, Any]] = [{"type": "servicenow_change", "evidence_id": change.get("sys_id")}]

        if not pims:
            all_findings.append(_finding("MISSING_PIM_REQUEST", "pim_request", "No PIM request is linked to the selected change.", actual=pim_request_id, expected=change_id, recommendation="Link an approved PIM request containing the required least-privilege access."))

        try:
            change_start, change_end = parse_utc(change["start"]), parse_utc(change["end"])
        except (KeyError, TypeError, ValueError):
            change_start = change_end = None

        for pim in pims:
            request_id = str(pim.get("pim_request_id") or "UNKNOWN")
            findings: list[dict[str, Any]] = []
            supported: list[dict[str, Any]] = []
            ids = [request_id]
            evidence.append({"type": "pim_request", "evidence_id": request_id})

            ticket = (pim.get("ticket") or {}).get("number")
            references = {item.upper() for item in CHANGE_REFERENCE.findall(str(pim.get("justification") or ""))}
            if pim.get("change_id") != change_id or ticket != change_id:
                findings.append(_finding("CHANGE_REFERENCE_MISMATCH", "change_reference", "The structured PIM change reference does not match the selected change.", actual={"change_id": pim.get("change_id"), "ticket": ticket}, expected=change_id, recommendation="Correct the structured ticket reference before access activation.", evidence_ids=ids))
            if references and change_id not in references:
                findings.append(_finding("JUSTIFICATION_CONTRADICTION", "justification", "The PIM justification references a different change.", actual=sorted(references), expected=change_id, recommendation="Correct the justification so it consistently references the approved change.", evidence_ids=ids, severity="REVIEW"))

            principal_id, principal_name = _norm(pim.get("principal_id")), _norm(pim.get("principal_name"))
            if principal_id not in authorized_ids and principal_name not in authorized_names:
                findings.append(_finding("IMPLEMENTER_MISMATCH", "principal", "The PIM principal is not an authorized implementer.", actual={"principal_id": pim.get("principal_id"), "principal_name": pim.get("principal_name")}, expected=authorized, recommendation="Use an explicitly authorized implementer identity or update the approved change.", evidence_ids=ids))

            role = role_by_id.get(_norm(pim.get("role_definition_id")))
            if role is None:
                findings.append(_finding("UNKNOWN_ROLE_DEFINITION", "role_definition_id", "The requested role definition is absent from the evidence catalog.", actual=pim.get("role_definition_id"), expected="Known role definition", recommendation="Provide the authoritative Azure role definition before assessing permissions.", evidence_ids=ids))
            elif _norm(role.get("role_name")) != _norm(pim.get("role_name")):
                findings.append(_finding("ROLE_DEFINITION_CONTRADICTION", "role_name", "The role name conflicts with the referenced role definition.", actual=pim.get("role_name"), expected=role.get("role_name"), recommendation="Correct the PIM role metadata.", evidence_ids=ids))

            if role:
                for operation in expected:
                    allowed, plane = _permission_allows(role, str(operation.get("operation") or ""))
                    in_scope = _scope_covers(str(pim.get("scope") or ""), str(operation.get("resource_id") or ""))
                    intended_principal = _norm(operation.get("authorized_principal_id"))
                    identity_applies = not intended_principal or intended_principal == principal_id
                    if allowed and in_scope and identity_applies:
                        supported.append({**operation, "permission_plane": plane})
                        covered_signatures.add((_norm(operation.get("operation")), _norm(operation.get("resource_id"))))
                if not supported:
                    findings.append(_finding("INSUFFICIENT_PRIVILEGES", "role_permissions", "The requested role and scope do not cover a documented operation for this principal.", actual=pim.get("role_name"), expected=expected, recommendation="Request a catalog role whose allowed actions cover the intended operation at the required resource scope.", evidence_ids=ids))

                narrower = []
                for candidate in roles:
                    if _norm(candidate.get("role_definition_id")) == _norm(role.get("role_definition_id")): continue
                    if all(_permission_allows(candidate, str(item.get("operation") or ""))[0] for item in supported) and _role_breadth(candidate) < _role_breadth(role):
                        narrower.append(candidate)
                if supported and narrower:
                    recommendation = min(narrower, key=_role_breadth)
                    findings.append(_finding("OVERPRIVILEGED_ROLE", "role_definition_id", "A narrower catalog role covers the supported documented operations.", actual=role.get("role_name"), expected=recommendation.get("role_name"), recommendation=f"Use {recommendation.get('role_name')} if its scope and full evidence remain applicable.", evidence_ids=ids, severity="WARNING"))

            scope = str(pim.get("scope") or "")
            relevant_targets = [item["resource_id"] for item in supported] or [item.get("resource_id") for item in expected if item.get("resource_id")]
            if relevant_targets and all(_scope_covers(scope, target) for target in relevant_targets) and all(_norm(scope) != _norm(target) for target in relevant_targets):
                findings.append(_finding("EXCESSIVE_SCOPE", "scope", "The requested scope is broader than the documented target resource.", actual=scope, expected=relevant_targets, recommendation="Narrow the access scope to the required Azure resource where supported.", evidence_ids=ids, severity="WARNING"))

            schedule = pim.get("schedule") or {}
            try:
                pim_start, pim_end = parse_utc(schedule["start"]), parse_utc(schedule["end"])
                if change_start and change_end and (pim_start < change_start or pim_end > change_end):
                    findings.append(_finding("EXCESSIVE_ACCESS_DURATION", "schedule", "The PIM activation extends outside the approved change window.", actual={"start": schedule.get("start"), "end": schedule.get("end")}, expected={"start": change.get("start"), "end": change.get("end")}, recommendation="Restrict activation to the approved maintenance window.", evidence_ids=ids, severity="WARNING"))
            except (KeyError, TypeError, ValueError):
                findings.append(_finding("INVALID_PIM_WINDOW", "schedule", "The PIM schedule is missing, invalid, or timezone-free.", actual=schedule, expected="Valid timezone-aware start and end", recommendation="Provide a valid PIM activation schedule.", evidence_ids=ids))

            if _norm(pim.get("status")) != "approved":
                findings.append(_finding("PIM_NOT_APPROVED", "status", "The PIM request is not approved.", actual=pim.get("status"), expected="Approved", recommendation="Obtain PIM approval before implementation.", evidence_ids=ids))

            assignment = next((item for item in assignments if item.get("pim_request_id") == request_id), None)
            if assignment is None:
                findings.append(_finding("MISSING_RBAC_ASSIGNMENT", "rbac_assignment", "No activation or assignment evidence is linked to the PIM request.", expected=request_id, recommendation="Provide RBAC/PIM activation evidence before confirming effective access.", evidence_ids=ids, severity="REVIEW"))
            else:
                ids.append(str(assignment.get("assignment_id")))
                evidence.append({"type": "rbac_assignment", "evidence_id": assignment.get("assignment_id")})
                contradictions = [key for key in ("principal_id", "role_definition_id", "scope") if _norm(assignment.get(key)) != _norm(pim.get(key))]
                if contradictions:
                    findings.append(_finding("RBAC_ASSIGNMENT_CONTRADICTION", "rbac_assignment", "Assignment evidence conflicts with the PIM request.", actual=contradictions, expected="Matching principal, role, and scope", recommendation="Reconcile the PIM request with actual assignment evidence.", evidence_ids=ids))

            if any(item["category"] in {"UNKNOWN_ROLE_DEFINITION", "MISSING_RBAC_ASSIGNMENT"} for item in findings): status = "NEED_MORE_INFO"
            elif any(item["category"] == "INSUFFICIENT_PRIVILEGES" for item in findings): status = "INSUFFICIENT_ACCESS"
            elif any(item["category"] == "OVERPRIVILEGED_ROLE" for item in findings): status = "OVERPRIVILEGED"
            elif findings: status = "MANUAL_REVIEW_REQUIRED"
            else: status = "APPROVE_RECOMMENDED"
            assessments.append({"pim_request_id": request_id, "overall_status": status, "supported_operations": supported, "findings": findings, "evidence_ids": ids})
            all_findings.extend(findings)

        missing_operations = [item for item in expected if (_norm(item.get("operation")), _norm(item.get("resource_id"))) not in covered_signatures]
        if missing_operations:
            all_findings.append(_finding("MISSING_PERMISSION_COVERAGE", "expected_operations", "Aggregate PIM access does not cover every documented operation.", actual=missing_operations, expected="Full operation coverage", recommendation="Add only the missing least-privilege access required for these operations."))

        missing = list(dict.fromkeys(item["field"] for item in all_findings if item["category"].startswith(("MISSING_", "UNKNOWN_", "INVALID_"))))
        if any(item["category"] in {"MISSING_PIM_REQUEST", "UNKNOWN_ROLE_DEFINITION", "MISSING_RBAC_ASSIGNMENT"} for item in all_findings): overall = "NEED_MORE_INFO"
        elif missing_operations or any(item["category"] == "INSUFFICIENT_PRIVILEGES" for item in all_findings): overall = "INSUFFICIENT_ACCESS"
        elif any(item["category"] == "OVERPRIVILEGED_ROLE" for item in all_findings): overall = "OVERPRIVILEGED"
        elif all_findings: overall = "MANUAL_REVIEW_REQUIRED"
        else: overall = "APPROVE_RECOMMENDED"
        return {
            "schema_version": SCHEMA_VERSION, "provider": "azure", "stage": "access",
            "change_id": change_id, "overall_status": overall, "pim_assessments": assessments,
            "covered_operations": [item for item in expected if (_norm(item.get("operation")), _norm(item.get("resource_id"))) in covered_signatures],
            "missing_operations": missing_operations, "findings": all_findings,
            "missing_information": missing,
            "recommendations": list(dict.fromkeys(item["recommendation"] for item in all_findings)),
            "evidence": evidence, "change": change,
        }
