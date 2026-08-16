
"""FastAPI application for the ChestMNIST educational assistant."""

from __future__ import annotations

import inspect
import time
from typing import Any

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.exceptions import (
    RequestValidationError,
)
from fastapi.responses import (
    JSONResponse,
)

from api.core.config import (
    get_settings,
)
from api.core.dependencies import (
    get_service_container,
)
from api.core.factory import (
    ensure_default_service_container,
)
from api.core.errors import (
    ServiceError,
    ServiceExecutionError,
)
from api.core.runtime import (
    RequestContext,
    build_error_response,
    utc_now,
)
from api.routes import (
    aggregate_router,
    health_router,
    system_router,
    workflow_router,
)
from api.schemas import (
    APIErrorResponse,
)


settings = get_settings()

ensure_default_service_container()


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=(
        "Educational decision-support API for frozen ChestMNIST "
        "classification, visual evidence, and grounded language "
        "generation. This service is not a diagnostic system."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


app.include_router(
    health_router
)

app.include_router(
    system_router
)

app.include_router(
    workflow_router
)

app.include_router(
    aggregate_router
)


def _request_context(
    request: Request,
) -> RequestContext:
    context = getattr(
        request.state,
        "request_context",
        None,
    )

    if context is None:
        context = RequestContext()
        request.state.request_context = (
            context
        )

    return context


def _context_latency_ms(
    context: RequestContext,
) -> float:
    for method_name in (
        "elapsed_ms",
        "latency_ms",
    ):
        method = getattr(
            context,
            method_name,
            None,
        )

        if callable(method):
            return max(
                0.0,
                float(
                    method()
                ),
            )

    return 0.0


def _serialize_service_error(
    *,
    context: RequestContext,
    error: ServiceError,
) -> APIErrorResponse:
    """Serialize a controlled service exception directly."""

    error_message = getattr(
        error,
        "message",
        None,
    )

    if not isinstance(
        error_message,
        str,
    ) or not error_message.strip():
        error_message = str(
            error
        ).strip()

    if not error_message:
        error_message = (
            "The service could not complete the request."
        )

    error_details = getattr(
        error,
        "details",
        {},
    )

    if not isinstance(
        error_details,
        dict,
    ):
        error_details = {}

    return APIErrorResponse(
        request_id=context.request_id,
        timestamp_utc=utc_now(),
        api_version=settings.api_version,
        status="error",
        error_code=str(
            error.error_code
        ),
        message=error_message,
        details=error_details,
        latency_ms=(
            _context_latency_ms(
                context
            )
        ),
        educational_use_only=True,
    )


def _safe_validation_details(
    error: RequestValidationError,
) -> dict[str, Any]:
    """Retain only safe validation locations, types, and messages."""

    issues = []

    for issue in error.errors():
        issues.append(
            {
                "location": [
                    str(value)
                    for value
                    in issue.get(
                        "loc",
                        ()
                    )
                ],
                "type": str(
                    issue.get(
                        "type",
                        "validation_error",
                    )
                ),
                "message": str(
                    issue.get(
                        "msg",
                        "Request validation failed.",
                    )
                ),
            }
        )

    return {
        "issues": issues
    }


@app.middleware(
    "http"
)
async def request_context_and_metrics(
    request: Request,
    call_next,
):
    """Attach request identity and record aggregate endpoint telemetry."""

    context = RequestContext()
    request.state.request_context = (
        context
    )

    started_at = time.perf_counter()

    response = await call_next(
        request
    )

    latency_ms = (
        time.perf_counter()
        - started_at
    ) * 1000.0

    route = request.scope.get(
        "route"
    )

    route_path = getattr(
        route,
        "path",
        request.url.path,
    )

    endpoint_key = (
        f"{request.method.upper()} "
        f"{route_path}"
    )

    error_code = getattr(
        request.state,
        "error_code",
        None,
    )

    try:
        services = get_service_container()

        if (
            endpoint_key
            in services
            .operational_metrics_service
            .registered_endpoints
        ):
            services.operational_metrics_service.record_request(
                endpoint=endpoint_key,
                status_code=response.status_code,
                latency_ms=latency_ms,
                error_code=error_code,
            )
    except Exception:
        # Metrics must never replace the endpoint response.
        pass

    return response


@app.exception_handler(
    ServiceError
)
async def service_error_handler(
    request: Request,
    error: ServiceError,
) -> JSONResponse:
    """Serialize controlled service exceptions."""

    context = _request_context(
        request
    )

    request.state.error_code = (
        error.error_code
    )

    error_response = (
        _serialize_service_error(
            context=context,
            error=error,
        )
    )

    return JSONResponse(
        status_code=error.status_code,
        content=error_response.model_dump(
            mode="json"
        ),
    )


@app.exception_handler(
    RequestValidationError
)
async def request_validation_error_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    """Return sanitized request-validation information."""

    context = _request_context(
        request
    )

    request.state.error_code = (
        "REQUEST_VALIDATION_ERROR"
    )

    error_response = APIErrorResponse(
        request_id=context.request_id,
        timestamp_utc=utc_now(),
        api_version=settings.api_version,
        status="error",
        error_code=(
            "REQUEST_VALIDATION_ERROR"
        ),
        message=(
            "The request did not satisfy the API contract."
        ),
        details=(
            _safe_validation_details(
                error
            )
        ),
        latency_ms=(
            _context_latency_ms(
                context
            )
        ),
        educational_use_only=True,
    )

    return JSONResponse(
        status_code=422,
        content=error_response.model_dump(
            mode="json"
        ),
    )


@app.exception_handler(
    Exception
)
async def unexpected_error_handler(
    request: Request,
    error: Exception,
) -> JSONResponse:
    """Convert unexpected failures into a non-sensitive response."""

    context = _request_context(
        request
    )

    controlled_error = (
        ServiceExecutionError()
    )

    request.state.error_code = (
        controlled_error.error_code
    )

    error_response = (
        _serialize_service_error(
            context=context,
            error=controlled_error,
        )
    )

    return JSONResponse(
        status_code=(
            controlled_error.status_code
        ),
        content=error_response.model_dump(
            mode="json"
        ),
    )
