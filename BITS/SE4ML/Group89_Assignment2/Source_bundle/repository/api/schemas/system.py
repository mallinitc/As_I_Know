"""Health, model lineage, and metrics response schemas."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field

from api.schemas.common import StrictSchema, SuccessResponseBase

NonNegativeFloat = Annotated[
    float,
    Field(ge=0.0),
]
NonNegativeInt = Annotated[
    int,
    Field(ge=0),
]


class ComponentHealth(StrictSchema):
    """Runtime readiness of one service component."""

    status: Literal[
        "ready",
        "not_loaded",
        "degraded",
        "error",
    ]
    loaded: bool
    device: str | None = Field(
        default=None,
        max_length=100,
    )
    detail: str = Field(
        min_length=1,
        max_length=500,
    )


class HealthResponse(SuccessResponseBase):
    """API and component health response."""

    service_name: str = Field(
        min_length=1,
        max_length=200,
    )
    uptime_seconds: NonNegativeFloat
    components: dict[str, ComponentHealth]


class ModelInfoResponse(SuccessResponseBase):
    """Sanitized frozen model and prompt lineage."""

    computer_vision: dict[str, Any]
    language: dict[str, Any]
    explainability: dict[str, Any]
    limitations: list[str] = Field(
        min_length=1,
    )


class ModelMetricsResponse(SuccessResponseBase):
    """Frozen development and held-out evaluation metrics."""

    computer_vision_metrics: dict[
        str,
        NonNegativeFloat,
    ]
    language_metrics: dict[
        str,
        NonNegativeFloat,
    ]
    guardrail_metrics: dict[
        str,
        NonNegativeFloat,
    ]


class OperationalMetricsResponse(SuccessResponseBase):
    """Aggregate in-process request and guardrail measurements."""

    service_started_at_utc: datetime
    total_requests: NonNegativeInt
    successful_requests: NonNegativeInt
    failed_requests: NonNegativeInt
    endpoint_request_counts: dict[
        str,
        NonNegativeInt,
    ]
    endpoint_average_latency_ms: dict[
        str,
        NonNegativeFloat,
    ]
    language_generation_requests: NonNegativeInt
    guardrail_action_counts: dict[
        str,
        NonNegativeInt,
    ]
