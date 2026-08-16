"""Common Pydantic contracts for versioned API responses."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    """Forbid undeclared request and response fields."""

    model_config = ConfigDict(extra="forbid")


class ModelVersions(StrictSchema):
    """Version lineage for the models contributing to a response."""

    computer_vision: str
    language: str | None = None
    explainability_method: str | None = None


class SuccessResponseBase(StrictSchema):
    """Shared top-level fields for successful API responses."""

    request_id: UUID
    timestamp_utc: datetime
    api_version: Literal["v1"] = "v1"
    status: Literal["success"] = "success"
    model_versions: ModelVersions
    prompt_registry_version: str | None = None
    latency_ms: float = Field(ge=0.0)
    warnings: list[str] = Field(default_factory=list)
    educational_use_only: Literal[True] = True


class APIErrorResponse(StrictSchema):
    """Controlled client-safe error response."""

    request_id: UUID
    timestamp_utc: datetime
    api_version: Literal["v1"] = "v1"
    status: Literal["error"] = "error"
    error_code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = Field(ge=0.0)
    educational_use_only: Literal[True] = True
