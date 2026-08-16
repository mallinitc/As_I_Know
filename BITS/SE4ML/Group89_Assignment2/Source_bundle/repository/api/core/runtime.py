"""Request identity, timing, and response metadata utilities."""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from api.core.config import ServiceSettings, get_settings
from api.core.errors import ServiceError
from api.schemas.common import APIErrorResponse, ModelVersions


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass
class RequestContext:
    """Identity and monotonic timer for one API request."""

    request_id: UUID = field(default_factory=uuid4)
    timestamp_utc: datetime = field(default_factory=utc_now)
    _started_at: float = field(
        default_factory=time.perf_counter,
        repr=False,
    )

    def elapsed_ms(self) -> float:
        """Return non-negative elapsed request time."""

        return max(
            0.0,
            (time.perf_counter() - self._started_at) * 1000.0,
        )


def build_model_versions(
    settings: ServiceSettings,
    include_language: bool = False,
    include_explainability: bool = False,
) -> ModelVersions:
    """Build endpoint-specific model lineage."""

    return ModelVersions(
        computer_vision=(settings.computer_vision_model_version),
        language=(settings.language_model_version if include_language else None),
        explainability_method=("LayerGradCam" if include_explainability else None),
    )


def build_success_metadata(
    context: RequestContext,
    *,
    settings: ServiceSettings | None = None,
    include_language: bool = False,
    include_explainability: bool = False,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build common successful response fields."""

    resolved_settings = settings or get_settings()

    return {
        "request_id": context.request_id,
        "timestamp_utc": (context.timestamp_utc),
        "api_version": (resolved_settings.api_version),
        "status": "success",
        "model_versions": (
            build_model_versions(
                resolved_settings,
                include_language=(include_language),
                include_explainability=(include_explainability),
            )
        ),
        "prompt_registry_version": (
            resolved_settings.prompt_registry_version if include_language else None
        ),
        "latency_ms": (context.elapsed_ms()),
        "warnings": warnings or [],
        "educational_use_only": True,
    }


def build_error_response(
    context: RequestContext,
    error: ServiceError,
    *,
    settings: ServiceSettings | None = None,
) -> APIErrorResponse:
    """Serialize a typed service error to the public schema."""

    resolved_settings = settings or get_settings()

    return APIErrorResponse(
        request_id=context.request_id,
        timestamp_utc=(context.timestamp_utc),
        api_version=(resolved_settings.api_version),
        status="error",
        error_code=error.error_code,
        message=error.message,
        details=error.details,
        latency_ms=context.elapsed_ms(),
        educational_use_only=True,
    )
