from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import data_path
from backend.errors import SnowflakeEvidenceError


class SnowflakeRepository:
    """Read-only access to V2's synthetic Snowflake evidence."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or data_path("snowflake")).resolve()

    def _read_array(self, filename: str) -> list[dict[str, Any]]:
        source = (self.root / filename).resolve()
        if source.parent != self.root or not source.is_file():
            raise SnowflakeEvidenceError(f"Required Snowflake evidence is missing: {filename}")
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SnowflakeEvidenceError(f"Snowflake evidence contains invalid JSON: {filename}") from exc
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise SnowflakeEvidenceError(f"Snowflake evidence must be an array of records: {filename}")
        return value

    def changes(self) -> list[dict[str, Any]]:
        return self._read_array("changes.json")

    def demo_scenarios(self) -> list[dict[str, Any]]:
        scenarios = self._read_array("demo_scenarios.json")
        change_ids = {item.get("change_id") for item in self.changes()}
        required = {
            "scenario_id", "scenario_name", "description", "change_id",
            "evaluation_timestamp", "expected_check_outcomes",
        }
        seen: set[str] = set()
        for scenario in scenarios:
            missing = required - scenario.keys()
            if missing:
                raise SnowflakeEvidenceError(
                    f"Snowflake scenario {scenario.get('scenario_id', '<unknown>')} is missing {sorted(missing)}"
                )
            if scenario["scenario_id"] in seen:
                raise SnowflakeEvidenceError("Snowflake demo scenario IDs must be unique")
            if scenario["change_id"] not in change_ids:
                raise SnowflakeEvidenceError(
                    f"Snowflake scenario {scenario['scenario_id']} references an unknown change"
                )
            seen.add(scenario["scenario_id"])
        return scenarios

    def validation_catalog(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "roles": self._read_array("roles.json"),
            "role_grants": self._read_array("role_grants.json"),
            "object_grants": self._read_array("object_grants.json"),
        }

    def query_history(self) -> list[dict[str, Any]]:
        return self._read_array("query_history.json")

    def access_history(self) -> list[dict[str, Any]]:
        return self._read_array("access_history.json")

    def users(self) -> list[dict[str, Any]]:
        return self._read_array("users.json")

    def post_implementation_scenarios(self) -> list[dict[str, Any]]:
        scenarios = self._read_array("post_implementation_scenarios.json")
        required = {
            "scenario_id", "scenario_name", "investigation_mode",
            "evaluation_timestamp", "evidence_query_ids", "window_days", "expected_findings",
        }
        query_ids = {item.get("query_id") for item in self.query_history()}
        change_ids = {item.get("change_id") for item in self.changes()}
        seen: set[str] = set()
        for scenario in scenarios:
            missing = required - scenario.keys()
            if missing:
                raise SnowflakeEvidenceError(
                    f"Snowflake post-implementation scenario {scenario.get('scenario_id', '<unknown>')} is missing {sorted(missing)}"
                )
            if scenario["scenario_id"] in seen:
                raise SnowflakeEvidenceError("Snowflake post-implementation scenario IDs must be unique")
            if scenario.get("change_id") and scenario["change_id"] not in change_ids:
                raise SnowflakeEvidenceError(f"Scenario {scenario['scenario_id']} references an unknown change")
            unknown_queries = set(scenario["evidence_query_ids"]) - query_ids
            if unknown_queries:
                raise SnowflakeEvidenceError(f"Scenario {scenario['scenario_id']} references unknown query evidence")
            seen.add(scenario["scenario_id"])
        return scenarios
