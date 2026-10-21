from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.errors import SnowflakeChangeNotFound
from backend.repositories.snowflake import SnowflakeRepository
from backend.services.snowflake_validation import validate_change


class SnowflakeValidationService:
    """Thin API adapter over the existing read-only Snowflake provider."""

    def __init__(self, repository: SnowflakeRepository | None = None) -> None:
        self.repository = repository or SnowflakeRepository()

    def list_changes(self) -> list[dict[str, Any]]:
        return self.repository.changes()

    def list_demo_scenarios(self) -> list[dict[str, Any]]:
        return self.repository.demo_scenarios()

    def validate(self, change_id: str, evaluation_timestamp: datetime | None = None) -> dict[str, Any]:
        change = next((item for item in self.repository.changes() if item.get("change_id") == change_id), None)
        if change is None:
            raise SnowflakeChangeNotFound(change_id)
        return validate_change(change, self.repository.validation_catalog(), evaluation_timestamp)
