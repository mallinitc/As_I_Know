from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import aws_evidence_source, aws_live_path, data_path
from backend.errors import AwsEvidenceError
from backend.repositories.aws_live import AwsLiveSource


class AwsRepository:
    """Read-only access to V2 AWS change and IAM evidence.

    Synthetic JSON fixtures are the default. With ARCA_AWS_EVIDENCE_SOURCE=live
    and no explicit root, the same records come from the real-AWS testbed:
    CloudTrail events and IAM policies are read from the account.
    """

    def __init__(self, root: Path | None = None, live: AwsLiveSource | None = None) -> None:
        self.root = (root or data_path("aws")).resolve()
        if live is None and root is None and aws_evidence_source() == "live":
            live = AwsLiveSource(aws_live_path())
        self.live = live

    @property
    def synthetic(self) -> bool:
        return self.live is None

    def _read_array(self, filename: str) -> list[dict[str, Any]]:
        if self.live is not None:
            value = self.live.read(filename)
            if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                raise AwsEvidenceError(f"AWS evidence must be an array of records: {filename}")
            return value
        source = (self.root / filename).resolve()
        if source.parent != self.root or not source.is_file():
            raise AwsEvidenceError(f"Required AWS evidence is missing: {filename}")
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AwsEvidenceError(f"AWS evidence contains invalid JSON: {filename}") from exc
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise AwsEvidenceError(f"AWS evidence must be an array of records: {filename}")
        return value

    def changes(self) -> list[dict[str, Any]]:
        return self._read_array("changes.json")

    def access_requests(self) -> list[dict[str, Any]]:
        return self._read_array("access_requests.json")

    def policy_evidence(self) -> list[dict[str, Any]]:
        return self._read_array("policy_evidence.json")

    def events(self) -> list[dict[str, Any]]:
        return self._read_array("events.json")

    def execution_events(self) -> list[dict[str, Any]]:
        return self.events() + self._read_array("execution_events.json")

    def execution_scenarios(self) -> list[dict[str, Any]]:
        return self._read_array("execution_scenarios.json")

    def demo_scenarios(self) -> list[dict[str, Any]]:
        scenarios = self._read_array("demo_scenarios.json")
        changes = {item.get("change_id") for item in self.changes()}
        required = {"scenario_id", "scenario_name", "stage", "change_id"}
        seen: set[str] = set()
        for scenario in scenarios:
            if required - scenario.keys():
                raise AwsEvidenceError(f"AWS demo scenario {scenario.get('scenario_id')} is incomplete")
            if scenario["scenario_id"] in seen:
                raise AwsEvidenceError("AWS demo scenario IDs must be unique")
            if scenario["stage"] not in {"change", "access"}:
                raise AwsEvidenceError(f"AWS demo scenario {scenario['scenario_id']} has an invalid stage")
            if scenario["change_id"] not in changes:
                raise AwsEvidenceError(f"AWS demo scenario {scenario['scenario_id']} references an unknown change")
            seen.add(scenario["scenario_id"])
        return scenarios
