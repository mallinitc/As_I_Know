"""V1 Stage 2 retrieval and input compatibility over the native Azure evaluator."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any

from backend.config import PROJECT_ROOT
from backend.repositories.azure import AzureRepository
from backend.services.azure_validation import AzureValidationService
from backend.services.timestamps import parse_utc

CATALOG_PATH = PROJECT_ROOT / "data" / "demo_catalog.json"
CHANGE_REFERENCE = re.compile(r"\bCHG(?:-[A-Z]+-\d+|\d+)\b", re.I)
LABELS = {"pim request id":"pim_request_id","request id":"pim_request_id","change number":"change_id","change id":"change_id","principal id":"principal_id","object id":"principal_id","upn":"principal_name","principal":"principal_name","role":"role_name","role name":"role_name","role definition id":"role_definition_id","scope":"scope","justification":"justification","requested start":"requested_start","start":"requested_start","requested end":"requested_end","end":"requested_end","request status":"status","status":"status","activation status":"activation_status"}


def _reference(value: str) -> str:
    match = CHANGE_REFERENCE.search(value or "")
    return match.group(0).upper() if match else ""


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    schedule = raw.get("schedule") or {}
    ticket = raw.get("ticket") or {}
    change_id = str(ticket.get("number") or raw.get("change_id") or _reference(str(raw.get("justification") or ""))).upper()
    item = dict(raw)
    item.update({
        "pim_request_id": raw.get("pim_request_id") or raw.get("request_id") or "",
        "change_id": change_id, "principal_id": raw.get("principal_id") or raw.get("object_id") or "",
        "principal_name": raw.get("principal_name") or raw.get("upn") or raw.get("user_principal_name") or "",
        "role_definition_id": raw.get("role_definition_id") or "", "role_name": raw.get("role_name") or raw.get("role") or "",
        "scope": raw.get("scope") or "", "justification": raw.get("justification") or "",
        "status": raw.get("status") or raw.get("request_status") or "",
        "schedule": {"start": raw.get("requested_start") or raw.get("start") or schedule.get("start") or "", "end": raw.get("requested_end") or raw.get("end") or schedule.get("end") or ""},
        "reference_source": "ticket" if ticket.get("number") else "structured" if raw.get("change_id") else "justification" if change_id else "",
    })
    references = list(dict.fromkeys(x.upper() for x in CHANGE_REFERENCE.findall(str(raw.get("justification") or ""))))
    ambiguities: list[str] = []
    if len(references) > 1: ambiguities.append("Multiple change references appear in the justification.")
    if item["reference_source"] == "ticket" and references and change_id not in references: ambiguities.append("Structured change reference conflicts with justification.")
    item["reference_ambiguities"] = ambiguities
    return item


def parse_records(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
        if isinstance(payload, dict): return [_normalize(payload)]
        if isinstance(payload, list) and all(isinstance(item, dict) for item in payload): return [_normalize(item) for item in payload]
        raise ValueError("PIM JSON must be an object or array of objects")
    except json.JSONDecodeError:
        values: dict[str, Any] = {}
        seen: dict[str, list[str]] = {}
        for line in text.splitlines():
            match = re.match(r"^\s*([^:]+):\s*(.*?)\s*$", line)
            if not match: continue
            key = LABELS.get(match.group(1).strip().lower())
            if key:
                seen.setdefault(key, []).append(match.group(2).strip())
                values[key] = match.group(2).strip()
        if not values: raise ValueError("No supported PIM fields were identified")
        item = _normalize(values)
        item["reference_ambiguities"].extend(f"Multiple values supplied for {key}." for key, entries in seen.items() if len(set(entries)) > 1)
        return [item]


def activation_state(request: dict[str, Any], assignments: list[dict[str, Any]], reference_time: datetime) -> str:
    related = [item for item in assignments if item.get("pim_request_id") == request.get("pim_request_id")]
    for item in related:
        try:
            if str(item.get("assignment_type") or "").lower() == "active" and parse_utc(item["valid_from"]) <= reference_time <= parse_utc(item["valid_to"]): return "Active"
        except (KeyError, TypeError, ValueError):
            continue
    try:
        if parse_utc((request.get("schedule") or {})["start"]) > reference_time: return "Scheduled"
    except (KeyError, TypeError, ValueError):
        pass
    if str(request.get("status") or "").lower() in {"pending", "pendingapproval", "submitted"}: return "Pending"
    return "Inactive"


class _SelectedRepository(AzureRepository):
    def __init__(self, selected: list[dict[str, Any]]):
        super().__init__()
        self.selected = selected

    def pim_requests(self) -> list[dict[str, Any]]:
        return self.selected


class Stage2Service:
    def __init__(self, repository: AzureRepository | None = None) -> None:
        self.repository = repository or AzureRepository()

    def scenarios(self) -> list[dict[str, Any]]:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        modes = {"stage2_change":"change", "stage2_user":"user", "stage2_paste":"paste"}
        return [{"scenario_id": item["scenario_id"], "name": item["name"], "mode": modes[item["feature"]],
                 "change_id": item.get("associated_change_number") or "", "pim_request_ids": item.get("pim_request_ids") or [],
                 "user_identity": item.get("user_identity") or "", "expected_outcome": item["expected_outcome"],
                 "explanation": item["explanation"], "access_state": item.get("inputs", {}).get("access_state", "All")}
                for item in catalog if item.get("provider", "azure") == "azure" and item.get("feature") in modes]

    def scenario_records(self, request_ids: list[str]) -> str:
        wanted = set(request_ids)
        return json.dumps([item for item in self.repository.pim_requests() if item.get("pim_request_id") in wanted], indent=2)

    def assess(self, mode: str, change_id: str = "", user_identity: str = "", access_state: str = "All", records_text: str = "", evaluation_timestamp: datetime | None = None) -> dict[str, Any]:
        reference = (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
        source = self.repository.pim_requests()
        if mode == "change":
            selected = [_normalize(item) for item in source if _normalize(item)["change_id"] == change_id]
        elif mode == "user":
            identity = user_identity.strip().casefold()
            selected = [_normalize(item) for item in source if identity in {str(item.get("principal_id") or "").casefold(), str(item.get("principal_name") or "").casefold()}]
            if change_id: selected = [item for item in selected if item["change_id"] == change_id]
        else:
            selected = parse_records(records_text)
            if change_id:
                for item in selected:
                    if not item.get("change_id"): item["change_id"] = change_id
        assignments = self.repository.rbac_assignments()
        for item in selected:
            item["activation_status"] = activation_state(item, assignments, reference)
        if access_state != "All": selected = [item for item in selected if item["activation_status"] == access_state]
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in selected: groups.setdefault(str(item.get("change_id") or change_id), []).append(item)
        assessments: list[dict[str, Any]] = []
        for linked_change, records in groups.items():
            if not linked_change: continue
            try:
                native = AzureValidationService(_SelectedRepository(records)).validate_access(linked_change)
            except Exception:
                continue
            categories = {finding.get("category") for finding in native["findings"]}
            if native["overall_status"] == "MANUAL_REVIEW_REQUIRED" and categories & {"EXCESSIVE_SCOPE", "EXCESSIVE_ACCESS_DURATION"}:
                native["overall_status"] = "OVERPRIVILEGED"
            for record in records:
                if record.get("reference_ambiguities"):
                    native["overall_status"] = "MANUAL_REVIEW_REQUIRED"
                    for message in record["reference_ambiguities"]:
                        native["findings"].append({"category":"AMBIGUOUS_CHANGE_REFERENCE","field":"change_reference","severity":"REVIEW","message":message,"actual":record.get("justification"),"expected":linked_change,"recommendation":"Resolve the conflicting change reference before access activation.","evidence_ids":[record.get("pim_request_id")]})
            assessments.append(native)
        statuses = {item["overall_status"] for item in assessments}
        if not selected or not assessments: overall = "NEED_MORE_INFO"
        elif "INSUFFICIENT_ACCESS" in statuses: overall = "INSUFFICIENT_ACCESS"
        elif "OVERPRIVILEGED" in statuses: overall = "OVERPRIVILEGED"
        elif "MANUAL_REVIEW_REQUIRED" in statuses: overall = "MANUAL_REVIEW_REQUIRED"
        elif statuses == {"APPROVE_RECOMMENDED"}: overall = "APPROVE_RECOMMENDED"
        else: overall = "NEED_MORE_INFO"
        risk = "LOW" if overall == "APPROVE_RECOMMENDED" else "HIGH" if overall in {"OVERPRIVILEGED", "INSUFFICIENT_ACCESS"} else "MODERATE"
        findings = [finding for item in assessments for finding in item["findings"]]
        missing = list(dict.fromkeys(value for item in assessments for value in item["missing_information"]))
        if not selected: missing.append("matching_pim_request")
        evidence = [entry for item in assessments for entry in item["evidence"]]
        recommendations = list(dict.fromkeys(value for item in assessments for value in item["recommendations"]))
        return {"provider":"azure","mode":mode,"evaluation_timestamp":reference,"overall_assessment":overall,"risk_classification":risk,
                "records":selected,"assessments":assessments,"findings":findings,"missing_information":missing,
                "recommendations":recommendations,"evidence":evidence}
