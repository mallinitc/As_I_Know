"""V1-compatible, read-only Azure investigation tools for Ask ARCA."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.repositories.azure import AzureRepository
from backend.services.timestamps import parse_utc, utc_text


def _result(tool: str, items: list[dict[str, Any]], **query: Any) -> dict[str, Any]:
    return {"tool": tool, "count": len(items), "query": query, "items": items}


def _in_window(value: str, start: str | None, end: str | None) -> bool:
    stamp = parse_utc(value)
    return (not start or stamp >= parse_utc(start)) and (not end or stamp <= parse_utc(end))


def _scope_covers(scope: str, resource_id: str) -> bool:
    left, right = scope.rstrip("/").casefold(), resource_id.rstrip("/").casefold()
    return right == left or right.startswith(left + "/")


class AzureInvestigationTools:
    """Side-effect-free facade over V2's local synthetic Azure evidence."""

    def __init__(self, repository: AzureRepository | None = None) -> None:
        self.repository = repository or AzureRepository()

    @property
    def evidence_as_of(self) -> str:
        return utc_text(max(parse_utc(item["event_timestamp"]) for item in self.repository.activity_logs()))

    def find_resources(self, query: str = "", subscription_id: str | None = None,
                       resource_group: str | None = None, resource_type: str | None = None,
                       environment: str | None = None) -> dict[str, Any]:
        needle = query.strip().casefold()
        items = [item for item in self.repository.resources()
                 if (not needle or needle in str(item.get("name") or "").casefold() or needle in str(item.get("resource_id") or "").casefold())
                 and (not subscription_id or str(item.get("subscription_id") or "").casefold() == subscription_id.casefold())
                 and (not resource_group or str(item.get("resource_group") or "").casefold() == resource_group.casefold())
                 and (not resource_type or resource_type.casefold() in str(item.get("type") or "").casefold())
                 and (not environment or str(item.get("environment") or "").casefold() == environment.casefold())]
        return _result("find_resources", items, query=query, subscription_id=subscription_id,
                       resource_group=resource_group, resource_type=resource_type, environment=environment)

    def get_resource_details(self, resource_id: str) -> dict[str, Any]:
        items = [item for item in self.repository.resources() if str(item.get("resource_id") or "").casefold() == resource_id.casefold()]
        return _result("get_resource_details", items, resource_id=resource_id)

    def get_activity_logs(self, resource_id: str | None = None, identity: str | None = None,
                          start: str | None = None, end: str | None = None,
                          modifications_only: bool = False, successful_only: bool = True) -> dict[str, Any]:
        items = []
        for event in self.repository.activity_logs():
            operation = str((event.get("operation_name") or {}).get("value") or "")
            affected = str((event.get("properties") or {}).get("affected_resource_id") or "")
            if resource_id and str(event.get("resource_id") or "").casefold() != resource_id.casefold() and affected.casefold() != resource_id.casefold(): continue
            if identity and identity.casefold() not in {str(event.get("caller") or "").casefold(), str(event.get("caller_principal_id") or "").casefold()}: continue
            if not _in_window(event["event_timestamp"], start, end): continue
            if modifications_only and operation.casefold().endswith("/read"): continue
            if successful_only and str((event.get("status") or {}).get("value") or "").casefold() != "succeeded": continue
            items.append(event)
        items.sort(key=lambda item: parse_utc(item["event_timestamp"]), reverse=True)
        return _result("get_activity_logs", items, resource_id=resource_id, identity=identity, start=start, end=end,
                       modifications_only=modifications_only, successful_only=successful_only)

    def get_role_assignments(self, resource_id: str | None = None, identity: str | None = None,
                             active_at: str | None = None) -> dict[str, Any]:
        names = {str(item.get("principal_id") or "").casefold(): str(item.get("principal_name") or "").casefold()
                 for item in self.repository.pim_requests()}
        items = []
        for assignment in self.repository.rbac_assignments():
            principal = str(assignment.get("principal_id") or "").casefold()
            if resource_id and not _scope_covers(str(assignment.get("scope") or ""), resource_id): continue
            if identity and identity.casefold() not in {principal, names.get(principal, "")}: continue
            if active_at and not (parse_utc(assignment["valid_from"]) <= parse_utc(active_at) <= parse_utc(assignment["valid_to"])): continue
            items.append(assignment)
        return _result("get_role_assignments", items, resource_id=resource_id, identity=identity, active_at=active_at)

    def get_pim_requests(self, resource_id: str | None = None, identity: str | None = None,
                         role: str | None = None, scope: str | None = None,
                         start: str | None = None, end: str | None = None) -> dict[str, Any]:
        items = []
        for request in self.repository.pim_requests():
            schedule = request.get("schedule") or {}
            request_scope = str(request.get("scope") or "").rstrip("/")
            if resource_id and not _scope_covers(request_scope, resource_id): continue
            if identity and identity.casefold() not in {str(request.get("principal_id") or "").casefold(), str(request.get("principal_name") or "").casefold()}: continue
            if role and role.casefold() not in str(request.get("role_name") or "").casefold(): continue
            if scope:
                if scope in {"subscription", "/subscriptions/"} and (request_scope.casefold().count("/") != 2 or not request_scope.casefold().startswith("/subscriptions/")): continue
                if scope not in {"subscription", "/subscriptions/"} and scope.casefold() not in request_scope.casefold(): continue
            if start and parse_utc(schedule["end"]) < parse_utc(start): continue
            if end and parse_utc(schedule["start"]) > parse_utc(end): continue
            items.append(request)
        items.sort(key=lambda item: parse_utc(item["schedule"]["start"]), reverse=True)
        return _result("get_pim_requests", items, resource_id=resource_id, identity=identity, role=role, scope=scope, start=start, end=end)

    def get_change_records(self, resource_id: str | None = None, identity: str | None = None,
                           start: str | None = None, end: str | None = None,
                           change_id: str | None = None) -> dict[str, Any]:
        items = []
        for change in self.repository.changes():
            expected = change.get("expected") or []
            implementer = change.get("implementer") or {}
            if resource_id and not any(str(item.get("resource_id") or "").casefold() == resource_id.casefold() for item in expected): continue
            if identity and identity.casefold() not in {str(implementer.get("principal_id") or "").casefold(), str(implementer.get("principal_name") or "").casefold()}: continue
            if change_id and str(change.get("change_id") or "").casefold() != change_id.casefold(): continue
            if start and parse_utc(change["end"]) < parse_utc(start): continue
            if end and parse_utc(change["start"]) > parse_utc(end): continue
            items.append(change)
        items.sort(key=lambda item: parse_utc(item["start"]), reverse=True)
        return _result("get_change_records", items, resource_id=resource_id, identity=identity, start=start, end=end, change_id=change_id)

    def correlate_approved_changes(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        rows = []
        for event in events:
            matches = []
            operation = str((event.get("operation_name") or {}).get("value") or "")
            for change in self.repository.changes():
                implementer = change.get("implementer") or {}
                if parse_utc(change["start"]) <= parse_utc(event["event_timestamp"]) <= parse_utc(change["end"]) \
                   and implementer.get("principal_id") == event.get("caller_principal_id") \
                   and any(str(item.get("operation") or "").casefold() == operation.casefold()
                           and str(item.get("resource_id") or "").casefold() == str(event.get("resource_id") or "").casefold()
                           for item in change.get("expected") or []):
                    matches.append(change["change_id"])
            rows.append({"event_id": event.get("event_data_id"), "change_ids": matches,
                         "classification": "MATCHED_APPROVED_CHANGE" if matches else "UNMATCHED_IN_AVAILABLE_RECORDS",
                         "warning": None if matches else "Unmatched does not mean unauthorized"})
        return _result("correlate_approved_changes", rows)

    def find_undocumented_changes(self, start: str | None = None, end: str | None = None,
                                  environment: str = "production") -> dict[str, Any]:
        events = self.get_activity_logs(start=start, end=end, modifications_only=True)["items"]
        correlations = self.correlate_approved_changes(events)["items"]
        resources = {str(item.get("resource_id") or "").casefold(): item for item in self.repository.resources()}
        by_id = {item["event_id"]: item for item in correlations}
        items = []
        for event in events:
            resource = resources.get(str(event.get("resource_id") or "").casefold())
            correlation = by_id[event["event_data_id"]]
            if environment and (not resource or str(resource.get("environment") or "").casefold() != environment.casefold()): continue
            if correlation["classification"] == "MATCHED_APPROVED_CHANGE": continue
            items.append({"event_id": event["event_data_id"], "timestamp": event["event_timestamp"],
                          "operation": (event.get("operation_name") or {}).get("value"), "resource_id": event.get("resource_id"),
                          "actor": event.get("caller"), "actor_principal_id": event.get("caller_principal_id"),
                          **correlation})
        return _result("find_undocumented_changes", items, start=start, end=end, environment=environment)

