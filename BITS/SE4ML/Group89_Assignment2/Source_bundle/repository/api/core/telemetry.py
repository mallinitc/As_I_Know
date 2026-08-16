"""Endpoint-level telemetry adapter for public API metrics."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class APIOperationalSnapshot:
    """Public operational values required by the API schema."""

    service_started_at_utc: Any
    total_requests: int
    successful_requests: int
    failed_requests: int
    endpoint_request_counts: dict[str, int]
    endpoint_average_latency_ms: dict[str, float]
    language_generation_requests: int
    guardrail_action_counts: dict[str, int]


class EndpointTelemetryAdapter:
    """Add endpoint-specific latency metrics to the base service."""

    def __init__(
        self,
        base_metrics_service: Any,
    ) -> None:
        self.base_metrics_service = base_metrics_service

        self._lock = threading.RLock()

        registered_endpoints = tuple(base_metrics_service.registered_endpoints)

        self._endpoint_latency_total = {
            endpoint: 0.0 for endpoint in registered_endpoints
        }

        self._endpoint_latency_count = {
            endpoint: 0 for endpoint in registered_endpoints
        }

    @property
    def registered_endpoints(
        self,
    ) -> tuple[str, ...]:
        return tuple(self.base_metrics_service.registered_endpoints)

    def record_request(
        self,
        *,
        endpoint: str,
        status_code: int,
        latency_ms: float,
        error_code: str | None = None,
    ) -> None:
        normalized_latency = float(latency_ms)

        if not math.isfinite(normalized_latency) or normalized_latency < 0.0:
            raise ValueError("Request latency must be finite and non-negative.")

        self.base_metrics_service.record_request(
            endpoint=endpoint,
            status_code=status_code,
            latency_ms=normalized_latency,
            error_code=error_code,
        )

        with self._lock:
            self._endpoint_latency_total[endpoint] += normalized_latency

            self._endpoint_latency_count[endpoint] += 1

    def record_service_invocation(
        self,
        service_name: str,
        count: int = 1,
    ) -> None:
        self.base_metrics_service.record_service_invocation(
            service_name,
            count,
        )

    def record_language_action(
        self,
        action: str,
        count: int = 1,
    ) -> None:
        self.base_metrics_service.record_language_action(
            action,
            count,
        )

    def snapshot(
        self,
    ):
        return self.base_metrics_service.snapshot()

    def endpoint_average_latency_ms(
        self,
    ) -> dict[str, float]:
        with self._lock:
            averages = {}

            for endpoint in self.registered_endpoints:
                request_count = self._endpoint_latency_count[endpoint]

                if request_count:
                    average = self._endpoint_latency_total[endpoint] / request_count
                else:
                    average = 0.0

                averages[endpoint] = float(average)

        return averages

    def api_snapshot(
        self,
    ) -> APIOperationalSnapshot:
        base_snapshot = self.base_metrics_service.snapshot()

        accepted_count = base_snapshot.accepted_model_generations

        fallback_count = base_snapshot.safe_template_fallbacks

        return APIOperationalSnapshot(
            service_started_at_utc=(base_snapshot.service_started_at_utc),
            total_requests=(base_snapshot.total_requests),
            successful_requests=(base_snapshot.successful_requests),
            failed_requests=(base_snapshot.failed_requests),
            endpoint_request_counts=dict(base_snapshot.endpoint_request_counts),
            endpoint_average_latency_ms=(self.endpoint_average_latency_ms()),
            language_generation_requests=(accepted_count + fallback_count),
            guardrail_action_counts={
                "accepted_model_generation": (accepted_count),
                "safe_template_fallback": (fallback_count),
            },
        )
