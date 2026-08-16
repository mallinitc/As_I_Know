
"""Health, model, evaluation, and operational FastAPI routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
)

from api.core.dependencies import (
    ServiceContainer,
    get_service_container,
)
from api.core.runtime import (
    RequestContext,
    build_success_metadata,
)
from api.schemas import (
    HealthResponse,
    ModelInfoResponse,
    ModelMetricsResponse,
    OperationalMetricsResponse,
)


_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "system_response_templates.json"
)


def _load_templates() -> dict:
    with _TEMPLATE_PATH.open(
        "r",
        encoding="utf-8",
    ) as template_file:
        return json.load(
            template_file
        )


SYSTEM_TEMPLATES = _load_templates()


health_router = APIRouter(
    tags=["health"],
)

system_router = APIRouter(
    prefix="/api/v1",
    tags=["system"],
)


@health_router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check service readiness",
)
async def health(
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> HealthResponse:
    """Return service readiness without running model inference."""

    request_context = RequestContext()

    runtime_snapshot = (
        services.operational_metrics_service
        .snapshot()
    )

    response_metadata = build_success_metadata(
        request_context,
        include_language=True,
        include_explainability=True,
    )

    return HealthResponse.model_validate(
        {
            **response_metadata,
            **SYSTEM_TEMPLATES[
                "health"
            ],
            "uptime_seconds": (
                runtime_snapshot
                .uptime_seconds
            ),
        }
    )


@system_router.get(
    "/model/info",
    response_model=ModelInfoResponse,
    summary="Return versioned model information",
)
async def model_info(
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> ModelInfoResponse:
    """Return sanitized computer-vision and language lineage."""

    request_context = RequestContext()

    response_metadata = build_success_metadata(
        request_context,
        include_language=True,
        include_explainability=True,
    )

    return ModelInfoResponse.model_validate(
        {
            **response_metadata,
            **SYSTEM_TEMPLATES[
                "model_info"
            ],
        }
    )


@system_router.get(
    "/model/metrics",
    response_model=ModelMetricsResponse,
    summary="Return frozen model evaluation metrics",
)
async def model_metrics(
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> ModelMetricsResponse:
    """Return frozen evaluation and guardrail measurements."""

    request_context = RequestContext()

    response_metadata = build_success_metadata(
        request_context,
        include_language=True,
        include_explainability=True,
    )

    return ModelMetricsResponse.model_validate(
        {
            **response_metadata,
            **SYSTEM_TEMPLATES[
                "model_metrics"
            ],
        }
    )


@system_router.get(
    "/llmops/metrics",
    response_model=OperationalMetricsResponse,
    summary="Return API operational metrics",
)
async def llmops_metrics(
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> OperationalMetricsResponse:
    """Return aggregate operational data without request content."""

    request_context = RequestContext()

    runtime_snapshot = (
        services.operational_metrics_service
        .api_snapshot()
    )

    response_metadata = build_success_metadata(
        request_context,
        include_language=True,
        include_explainability=True,
    )

    return OperationalMetricsResponse.model_validate(
        {
            **response_metadata,
            **SYSTEM_TEMPLATES[
                "operational_static"
            ],
            "service_started_at_utc": (
                runtime_snapshot
                .service_started_at_utc
            ),
            "total_requests": (
                runtime_snapshot
                .total_requests
            ),
            "successful_requests": (
                runtime_snapshot
                .successful_requests
            ),
            "failed_requests": (
                runtime_snapshot
                .failed_requests
            ),
            "endpoint_request_counts": (
                runtime_snapshot
                .endpoint_request_counts
            ),
            "endpoint_average_latency_ms": (
                runtime_snapshot
                .endpoint_average_latency_ms
            ),
            "language_generation_requests": (
                runtime_snapshot
                .language_generation_requests
            ),
            "guardrail_action_counts": (
                runtime_snapshot
                .guardrail_action_counts
            ),
        }
    )
