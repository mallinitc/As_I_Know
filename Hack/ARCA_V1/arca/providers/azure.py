"""Azure PIM/RBAC and Activity Log adapter for fully synthetic evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatchcase
import json

from arca.evidence import ActivityEvidence, ChangeEvidence, PrivilegeEvidence, ResourceEvidence
from arca.paths import data_dir

DISPLAY_NAME = "Azure"
EVIDENCE_SOURCE = "Synthetic ServiceNow, PIM, RBAC, Azure Resource and Activity Log evidence"
DATA = data_dir("azure")


def _load(filename):
    return json.loads((DATA / filename).read_text(encoding="utf-8"))


def _at(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_bundle():
    return {
        "changes": _load("servicenow_changes.json"),
        "access_requests": _load("pim_requests.json"),
        "rbac_assignments": _load("rbac_assignments.json"),
        "role_definitions": _load("role_definitions.json"),
        "resources": _load("resources.json"),
        "events": _load("activity_logs.json"),
    }


def access_for_change(bundle, change_id):
    return next((x for x in bundle["access_requests"] if x.get("change_id") == change_id), {})


def normalize_change(change) -> ChangeEvidence:
    actor = change.get("implementer", {})
    return {"provider": "azure", "evidence_id": change.get("sys_id", change.get("change_id", "")),
            "change_id": change.get("change_id", ""), "environment": change.get("environment", ""),
            "actor_id": actor.get("principal_id", ""), "actor_name": actor.get("principal_name", ""),
            "window_start": change.get("start", ""), "window_end": change.get("end", ""),
            "description": change.get("description", ""),
            "expected": [{"operation": x.get("operation", ""), "resource_id": x.get("resource_id", "")} for x in change.get("expected", [])],
            "raw": change}


def normalize_activity(event) -> ActivityEvidence:
    status = event.get("status", {}).get("value", "")
    operation = event.get("operation_name", {}).get("value", "")
    return {"provider": "azure", "evidence_id": event.get("event_data_id", ""),
            "correlation_id": event.get("correlation_id", ""), "timestamp": event.get("event_timestamp", ""),
            "actor_id": event.get("caller_principal_id", ""), "actor_name": event.get("caller", ""),
            "operation": operation, "resource_ids": [event.get("resource_id", "")],
            "successful": status.lower() == "succeeded", "read_only": operation.lower().endswith("/read"), "raw": event}


def normalize_resource(resource) -> ResourceEvidence:
    return {"provider": "azure", "resource_id": resource["resource_id"], "resource_type": resource["type"],
            "environment": resource.get("environment", ""), "raw": resource}


def _role_actions(role_definition):
    actions = []
    for permission in role_definition.get("permissions", []):
        actions.extend(permission.get("actions", []))
    return actions


def normalize_privilege(request, context) -> PrivilegeEvidence:
    role = next((x for x in context.get("role_definitions", []) if x["role_definition_id"].lower() == request.get("role_definition_id", "").lower()), {})
    schedule = request.get("schedule", {})
    return {"provider": "azure", "evidence_id": request.get("pim_request_id", ""),
            "change_id": request.get("change_id", ""), "principal_id": request.get("principal_id", ""),
            "principal_name": request.get("principal_name", ""), "role_definition_id": request.get("role_definition_id", ""),
            "role_name": role.get("role_name", request.get("role_name", "")), "actions": _role_actions(role),
            "scopes": [request.get("scope", "")], "valid_from": schedule.get("start", ""),
            "valid_to": schedule.get("end", ""), "raw": request}


def evaluate_stage1(change, context=None):
    normalized = normalize_change(change)
    missing = [name for name, value in (("change_id", normalized["change_id"]), ("description", normalized["description"]),
               ("environment", normalized["environment"]), ("implementer", normalized["actor_id"]),
               ("start", normalized["window_start"]), ("end", normalized["window_end"]), ("expected", normalized["expected"])) if not value]
    if normalized["window_start"] and normalized["window_end"] and _at(normalized["window_start"]) >= _at(normalized["window_end"]):
        missing.append("valid_change_window")
    return {"status": "VALID" if not missing else "NEEDS_INFO", "missing": missing,
            "expected": change.get("expected", []), "provider": "azure", "evidence_id": normalized["evidence_id"]}


def _action_allowed(required, patterns):
    return any(fnmatchcase(required.lower(), pattern.lower()) for pattern in patterns)


def _scope_covers(scope, resource_id):
    left, right = scope.rstrip("/").lower(), resource_id.rstrip("/").lower()
    return right == left or right.startswith(left + "/")


def evaluate_stage2(change, request, context=None):
    context = context or {}
    if not request:
        return {"status": "MANUAL_REVIEW", "reason": "Missing PIM request", "provider": "azure"}
    privilege = normalize_privilege(request, context)
    assignments = [x for x in context.get("rbac_assignments", []) if x.get("pim_request_id") == request.get("pim_request_id")]
    findings = []
    if request.get("status") != "Approved": findings.append("PIM_NOT_APPROVED")
    if not assignments: findings.append("NO_ACTIVE_RBAC_ASSIGNMENT")
    missing_actions = [x["operation"] for x in change.get("expected", []) if not _action_allowed(x["operation"], privilege["actions"])]
    missing_scopes = [x["resource_id"] for x in change.get("expected", []) if not any(_scope_covers(scope, x["resource_id"]) for scope in privilege["scopes"])]
    subscription_scope = any(scope.lower().count("/") == 2 and scope.lower().startswith("/subscriptions/") for scope in privilege["scopes"])
    if subscription_scope and any(not x["resource_id"].lower().startswith(privilege["scopes"][0].lower() + "/providers/microsoft.authorization") for x in change.get("expected", [])):
        findings.append("EXCESSIVE_SUBSCRIPTION_SCOPE")
    if privilege["valid_from"] and privilege["valid_to"]:
        if _at(privilege["valid_from"]) < _at(change["start"]) or _at(privilege["valid_to"]) > _at(change["end"]):
            findings.append("PIM_EXTENDS_BEYOND_CHANGE_WINDOW")
    broad_role = privilege["role_name"] in {"Owner", "Contributor", "User Access Administrator"} or any(x == "*" for x in privilege["actions"])
    if broad_role: findings.append("ROLE_BROADER_THAN_REQUIRED")
    if missing_actions or missing_scopes or "NO_ACTIVE_RBAC_ASSIGNMENT" in findings or "PIM_NOT_APPROVED" in findings:
        status = "INSUFFICIENT"
    elif findings:
        status = "OVERPRIVILEGED"
    else:
        status = "APPROPRIATE"
    return {"status": status, "role": privilege["role_name"], "scope": privilege["scopes"][0],
            "findings": findings, "missing_actions": missing_actions, "missing_resources": missing_scopes,
            "pim_request_id": privilege["evidence_id"], "provider": "azure",
            "warning": "Illustrative Azure RBAC/PIM comparison; not an effective-access evaluation"}


def _is_relevant(activity, change):
    resource_ids = [x["resource_id"].lower() for x in change.get("expected", [])]
    event_resource = activity["resource_ids"][0].lower()
    actor_match = activity["actor_id"] == change.get("implementer", {}).get("principal_id")
    resource_match = event_resource in resource_ids
    stamp = _at(activity["timestamp"]).timestamp()
    return (actor_match or resource_match) and _at(change["start"]).timestamp() - 7200 <= stamp <= _at(change["end"]).timestamp() + 7200


def _impact_signal(event):
    props = event.get("properties", {})
    affected = props.get("affected_resource_id", "").lower()
    if event.get("operation_name", {}).get("value", "").lower() == "microsoft.authorization/roleassignments/delete" and "/microsoft.storage/storageaccounts/" in affected:
        return "STORAGE_ACCESS_LOSS_POSSIBLY_RELATED_TO_ROLE_ASSIGNMENT_REMOVAL"
    changed = [x.lower() for x in props.get("changed_settings", [])]
    if event.get("operation_name", {}).get("value", "").lower() == "microsoft.storage/storageaccounts/write" and "networkacls" in changed:
        return "STORAGE_ACCESS_LOSS_POSSIBLY_RELATED_TO_FIREWALL_MODIFICATION"
    return None


def evaluate_stage3(change, events, context=None):
    rows, signals = [], []
    expected = change.get("expected", [])
    for raw in events:
        event = normalize_activity(raw)
        if not event["successful"] or event["read_only"] or not _is_relevant(event, change): continue
        reasons = []
        if event["actor_id"] != change.get("implementer", {}).get("principal_id"): reasons.append("ACTOR_MISMATCH")
        if not (_at(change["start"]) <= _at(event["timestamp"]) <= _at(change["end"])): reasons.append("OUTSIDE_WINDOW")
        if not any(x["operation"].lower() == event["operation"].lower() and x["resource_id"].lower() == event["resource_ids"][0].lower() for x in expected):
            reasons.append("UNEXPECTED_OPERATION_OR_RESOURCE")
        rows.append({"event_id": event["evidence_id"], "correlation_id": event["correlation_id"], "timestamp": event["timestamp"],
                     "operation": event["operation"], "resource_id": event["resource_ids"][0],
                     "status": "DEVIATION" if reasons else "POTENTIAL_MATCH", "reasons": reasons})
        signal = _impact_signal(raw)
        if signal and signal not in signals: signals.append(signal)
    matched = {(x["operation"].lower(), x["resource_id"].lower()) for x in rows if x["status"] == "POTENTIAL_MATCH"}
    missing = [x for x in expected if (x["operation"].lower(), x["resource_id"].lower()) not in matched]
    status = "DEVIATION_DETECTED" if any(x["status"] == "DEVIATION" for x in rows) else ("EVIDENCE_INCOMPLETE" if missing else "POTENTIAL_MATCH")
    return {"status": status, "events": rows, "missing_expected": missing, "impact_signals": signals, "provider": "azure",
            "warning": "A matching Activity Log operation is evidence of an attempted/succeeded control-plane request, not proof of intended resource state"}


def find_unmatched(changes, events, context=None):
    output = []
    for raw in events:
        event = normalize_activity(raw)
        if not event["successful"] or event["read_only"]: continue
        matched = any(_at(change["start"]) <= _at(event["timestamp"]) <= _at(change["end"])
                      and event["actor_id"] == change.get("implementer", {}).get("principal_id")
                      and any(x["operation"].lower() == event["operation"].lower() and x["resource_id"].lower() == event["resource_ids"][0].lower() for x in change.get("expected", []))
                      for change in changes if change.get("start") and change.get("end"))
        if not matched:
            output.append({"event_id": event["evidence_id"], "timestamp": event["timestamp"], "operation": event["operation"],
                           "resource_id": event["resource_ids"][0], "classification": "UNMATCHED_IN_AVAILABLE_RECORDS",
                           "impact_signal": _impact_signal(raw),
                           "warning": "Unmatched does not establish that activity was unauthorized"})
    return output
