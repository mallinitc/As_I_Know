"""Structured, read-only tools over the synthetic Azure evidence corpus."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from arca.providers import azure
from arca.providers import get_provider
from arca.time_filters import evidence_reference_time


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _in_window(value: str, start: str | None, end: str | None) -> bool:
    stamp = _at(value)
    return (not start or stamp >= _at(start)) and (not end or stamp <= _at(end))


def _result(tool: str, items: list[dict], **query: Any) -> dict:
    return {"tool": tool, "count": len(items), "query": query, "items": items}


class InvestigationTools:
    """Evidence lookup facade. Every method is side-effect free."""

    def __init__(self, bundle: dict | None = None, provider: str = "azure", evidence_mode: str = "demonstration"):
        self.provider = provider.lower()
        self.evidence_mode = evidence_mode
        self.adapter = get_provider(self.provider)
        self.bundle = bundle or self.adapter.load_bundle()

    @property
    def evidence_as_of(self) -> str:
        return evidence_reference_time(self.provider, self.bundle["events"], self.evidence_mode).isoformat(timespec="seconds").replace("+00:00", "Z")

    def find_resources(self, query: str = "", subscription_id: str | None = None,
                       resource_group: str | None = None, resource_type: str | None = None,
                       environment: str | None = None) -> dict:
        needle = query.lower().strip()
        items = [resource for resource in self.bundle["resources"]
                 if (not needle or needle in resource["name"].lower() or needle in resource["resource_id"].lower())
                 and (not subscription_id or resource["subscription_id"].lower() == subscription_id.lower())
                 and (not resource_group or resource["resource_group"].lower() == resource_group.lower())
                 and (not resource_type or resource_type.lower() in resource["type"].lower())
                 and (not environment or resource.get("environment", "").lower() == environment.lower())]
        return _result("find_resources", items, query=query, subscription_id=subscription_id,
                       resource_group=resource_group, resource_type=resource_type, environment=environment)

    def get_resource_details(self, resource_id: str) -> dict:
        items = [resource for resource in self.bundle["resources"] if resource["resource_id"].lower() == resource_id.lower()]
        return _result("get_resource_details", items, resource_id=resource_id)

    def get_activity_logs(self, resource_id: str | None = None, identity: str | None = None,
                          start: str | None = None, end: str | None = None,
                          modifications_only: bool = False, successful_only: bool = True) -> dict:
        items = []
        for event in self.bundle["events"]:
            operation = event["operation_name"]["value"]
            affected = event.get("properties", {}).get("affected_resource_id", "")
            if resource_id and event["resource_id"].lower() != resource_id.lower() and affected.lower() != resource_id.lower(): continue
            if identity and identity.lower() not in {event.get("caller", "").lower(), event.get("caller_principal_id", "").lower()}: continue
            if not _in_window(event["event_timestamp"], start, end): continue
            if modifications_only and operation.lower().endswith("/read"): continue
            if successful_only and event.get("status", {}).get("value", "").lower() != "succeeded": continue
            items.append(event)
        items.sort(key=lambda item: _at(item["event_timestamp"]), reverse=True)
        return _result("get_activity_logs", items, resource_id=resource_id, identity=identity,
                       start=start, end=end, modifications_only=modifications_only, successful_only=successful_only)

    def get_role_assignments(self, resource_id: str | None = None, identity: str | None = None,
                             active_at: str | None = None) -> dict:
        items = []
        principal_names = {request["principal_id"].lower(): request.get("principal_name", "").lower()
                           for request in self.bundle["access_requests"]}
        for assignment in self.bundle["rbac_assignments"]:
            if resource_id and not azure._scope_covers(assignment["scope"], resource_id): continue
            if identity and identity.lower() not in {assignment.get("principal_id", "").lower(), principal_names.get(assignment.get("principal_id", "").lower(), "")}: continue
            if active_at and not (_at(assignment["valid_from"]) <= _at(active_at) <= _at(assignment["valid_to"])): continue
            items.append(assignment)
        return _result("get_role_assignments", items, resource_id=resource_id, identity=identity, active_at=active_at)

    def get_pim_requests(self, resource_id: str | None = None, identity: str | None = None,
                         role: str | None = None, scope: str | None = None,
                         start: str | None = None, end: str | None = None) -> dict:
        if self.provider == "aws":
            changes = {change["change_id"]: change for change in self.bundle["changes"]}
            items = []
            for request in self.bundle["access_requests"]:
                change = changes.get(request.get("change_id"), {})
                if resource_id and resource_id not in request.get("resources", []): continue
                if identity and identity.lower() != change.get("actor", "").lower(): continue
                if role and role.lower() not in request.get("role", "").lower(): continue
                if scope and not any(scope.lower() in value.lower() for value in request.get("resources", [])): continue
                if start and change and _at(change["end"]) < _at(start): continue
                if end and change and _at(change["start"]) > _at(end): continue
                items.append(request)
            return _result("get_pim_requests", items, resource_id=resource_id, identity=identity,
                           role=role, scope=scope, start=start, end=end, provider="aws")
        items = []
        for request in self.bundle["access_requests"]:
            request_start = request["schedule"]["start"]
            request_end = request["schedule"]["end"]
            if resource_id and not azure._scope_covers(request["scope"], resource_id): continue
            if identity and identity.lower() not in {request.get("principal_id", "").lower(), request.get("principal_name", "").lower()}: continue
            if role and role.lower() not in request.get("role_name", "").lower(): continue
            if scope:
                request_scope = request.get("scope", "").rstrip("/")
                if scope in {"subscription", "/subscriptions/"}:
                    if request_scope.lower().count("/") != 2 or not request_scope.lower().startswith("/subscriptions/"): continue
                elif scope.lower() not in request_scope.lower(): continue
            if start and _at(request_end) < _at(start): continue
            if end and _at(request_start) > _at(end): continue
            items.append(request)
        items.sort(key=lambda item: _at(item["schedule"]["start"]), reverse=True)
        return _result("get_pim_requests", items, resource_id=resource_id, identity=identity,
                       role=role, scope=scope, start=start, end=end)

    def get_change_records(self, resource_id: str | None = None, identity: str | None = None,
                           start: str | None = None, end: str | None = None,
                           change_id: str | None = None) -> dict:
        items = []
        for change in self.bundle["changes"]:
            if resource_id and not any(expected["resource_id"].lower() == resource_id.lower() for expected in change.get("expected", [])): continue
            implementer = change.get("implementer", {})
            if identity and identity.lower() not in {implementer.get("principal_id", "").lower(), implementer.get("principal_name", "").lower()}: continue
            if change_id and change.get("change_id", "").lower() != change_id.lower(): continue
            if start and _at(change["end"]) < _at(start): continue
            if end and _at(change["start"]) > _at(end): continue
            items.append(change)
        items.sort(key=lambda item: _at(item["start"]), reverse=True)
        return _result("get_change_records", items, resource_id=resource_id, identity=identity,
                       start=start, end=end, change_id=change_id)

    def find_undocumented_changes(self, start: str | None = None, end: str | None = None,
                                  environment: str = "production", resource_id: str | None = None) -> dict:
        event_key = "event_timestamp" if self.provider == "azure" else "eventTime"
        filtered_events = [event for event in self.bundle["events"] if _in_window(event[event_key], start, end)]
        filtered_changes = [change for change in self.bundle["changes"]
                            if (not start or _at(change["end"]) >= _at(start)) and (not end or _at(change["start"]) <= _at(end))]
        unmatched = self.adapter.find_unmatched(filtered_changes, filtered_events, self.bundle)
        if self.provider == "azure":
            resources = {item["resource_id"].lower(): item for item in self.bundle["resources"]}
        else:
            resources = {}
        items = []
        for finding in unmatched:
            finding_resource = finding.get("resource_id", "")
            resource = resources.get(finding_resource.lower()) if finding_resource else None
            if resource_id and finding_resource.lower() != resource_id.lower(): continue
            if self.provider == "azure" and environment and (not resource or resource.get("environment", "").lower() != environment.lower()): continue
            if self.provider == "aws" and environment:
                source_event = next((event for event in filtered_events if event["eventID"] == finding["event_id"]), None)
                related = [change for change in self.bundle["changes"] if source_event and any(r in source_event.get("resources", []) for r in [x["resource"] for x in change.get("expected", [])])]
                if related and not any(change.get("environment", "").lower() == environment.lower() for change in related): continue
            items.append(finding)
        timestamp_by_id = {(event["event_data_id"] if self.provider == "azure" else event["eventID"]): event[event_key] for event in filtered_events}
        items.sort(key=lambda item: _at(item.get("timestamp") or timestamp_by_id[item["event_id"]]), reverse=True)
        return _result("find_undocumented_changes", items, start=start, end=end,
                       environment=environment, resource_id=resource_id)


# Functional entry points make the tools reusable outside the agent.
def find_resources(bundle=None, **kwargs): return InvestigationTools(bundle).find_resources(**kwargs)
def get_resource_details(resource_id, bundle=None): return InvestigationTools(bundle).get_resource_details(resource_id)
def get_activity_logs(bundle=None, **kwargs): return InvestigationTools(bundle).get_activity_logs(**kwargs)
def get_role_assignments(bundle=None, **kwargs): return InvestigationTools(bundle).get_role_assignments(**kwargs)
def get_pim_requests(bundle=None, **kwargs): return InvestigationTools(bundle).get_pim_requests(**kwargs)
def get_change_records(bundle=None, **kwargs): return InvestigationTools(bundle).get_change_records(**kwargs)
def find_undocumented_changes(bundle=None, **kwargs): return InvestigationTools(bundle).find_undocumented_changes(**kwargs)
