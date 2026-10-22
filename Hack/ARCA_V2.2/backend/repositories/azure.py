from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import data_path
from backend.errors import AzureEvidenceError


class AzureRepository:
    """Read-only access to V2's synthetic Azure assurance evidence."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or data_path("azure")).resolve()

    def _read_array(self, filename: str) -> list[dict[str, Any]]:
        source = (self.root / filename).resolve()
        if source.parent != self.root or not source.is_file():
            raise AzureEvidenceError(f"Required Azure evidence is missing: {filename}")
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AzureEvidenceError(f"Azure evidence contains invalid JSON: {filename}") from exc
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise AzureEvidenceError(f"Azure evidence must be an array of records: {filename}")
        return value

    def changes(self) -> list[dict[str, Any]]:
        return self._read_array("servicenow_changes.json")

    def pim_requests(self) -> list[dict[str, Any]]:
        return self._read_array("pim_requests.json")

    def rbac_assignments(self) -> list[dict[str, Any]]:
        return self._read_array("rbac_assignments.json")

    def role_definitions(self) -> list[dict[str, Any]]:
        return self._read_array("role_definitions.json")

    def resources(self) -> list[dict[str, Any]]:
        return self._read_array("resources.json")

    def activity_logs(self) -> list[dict[str, Any]]:
        return self._read_array("activity_logs.json")

    def execution_scenarios(self) -> list[dict[str, Any]]:
        scenarios = self._read_array("execution_scenarios.json")
        event_ids = {item.get("event_data_id") for item in self.activity_logs()}
        change_ids = {item.get("change_id") for item in self.changes()}
        required = {"scenario_id", "scenario_name", "mode", "evaluation_timestamp", "window_days", "event_data_ids", "expected_findings"}
        seen: set[str] = set()
        for scenario in scenarios:
            if required - scenario.keys():
                raise AzureEvidenceError(f"Azure execution scenario {scenario.get('scenario_id')} is incomplete")
            if scenario["scenario_id"] in seen:
                raise AzureEvidenceError("Azure execution scenario IDs must be unique")
            if scenario["mode"] not in {"change", "user"}:
                raise AzureEvidenceError(f"Azure execution scenario {scenario['scenario_id']} has an invalid mode")
            if scenario.get("change_id") and scenario["change_id"] not in change_ids:
                raise AzureEvidenceError(f"Azure execution scenario {scenario['scenario_id']} references an unknown change")
            if set(scenario["event_data_ids"]) - event_ids:
                raise AzureEvidenceError(f"Azure execution scenario {scenario['scenario_id']} references unknown events")
            seen.add(scenario["scenario_id"])
        return scenarios

    def demo_scenarios(self) -> list[dict[str, Any]]:
        scenarios: list[dict[str, Any]] = []
        for index, change in enumerate(self.changes(), start=1):
            scenario = str(change.get("scenario") or "VALID_APPROVED_CHANGE")
            title = scenario.replace("_", " ").title()
            scenarios.append({
                "scenario_id": f"AZ-CHANGE-{index:02d}",
                "scenario_name": f"Stage 1 - {title}",
                "stage": "change",
                "change_id": change["change_id"],
                "description": f"Validate change quality for {change['change_id']} using existing synthetic evidence.",
                "source_scenario": scenario,
            })
            scenarios.append({
                "scenario_id": f"AZ-ACCESS-{index:02d}",
                "scenario_name": f"Stage 2 - {title}",
                "stage": "access",
                "change_id": change["change_id"],
                "description": f"Validate PIM and RBAC consistency for {change['change_id']} using existing synthetic evidence.",
                "source_scenario": scenario,
            })
        return scenarios
