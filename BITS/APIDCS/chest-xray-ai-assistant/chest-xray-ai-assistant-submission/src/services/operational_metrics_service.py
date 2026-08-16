
"""Thread-safe, privacy-preserving operational API metrics."""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class OperationalMetricsSnapshot:
    """Immutable snapshot of API operational metrics."""

    service_started_at_utc: datetime
    captured_at_utc: datetime
    uptime_seconds: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_latency_ms: float
    p95_latency_ms: float
    maximum_latency_ms: float
    endpoint_request_counts: dict[str, int]
    status_code_counts: dict[str, int]
    error_code_counts: dict[str, int]
    service_invocation_counts: dict[str, int]
    accepted_model_generations: int
    safe_template_fallbacks: int
    raw_generation_acceptance_rate: float
    safe_fallback_rate: float


class OperationalMetricsService:
    """Collect bounded operational measurements without request content."""

    REGISTERED_SERVICES = (
        "computer_vision",
        "gradcam",
        "grounded_language",
        "language_guardrail",
        "prediction_store",
    )

    LANGUAGE_ACTIONS = (
        "accepted_model_generation",
        "safe_template_fallback",
    )

    def __init__(
        self,
        *,
        registered_endpoints: Iterable[str],
        maximum_latency_samples: int = 10_000,
    ) -> None:
        endpoints = tuple(
            dict.fromkeys(
                str(endpoint).strip()
                for endpoint in registered_endpoints
                if str(endpoint).strip()
            )
        )

        if not endpoints:
            raise ValueError(
                "At least one registered endpoint is required."
            )

        if maximum_latency_samples <= 0:
            raise ValueError(
                "Maximum latency samples must be positive."
            )

        self.registered_endpoints = endpoints
        self.maximum_latency_samples = int(
            maximum_latency_samples
        )

        self._lock = threading.RLock()
        self._started_at_utc = datetime.now(
            timezone.utc
        )
        self._started_at_monotonic = (
            time.monotonic()
        )

        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0

        self._endpoint_counts = Counter(
            {
                endpoint: 0
                for endpoint in endpoints
            }
        )

        self._status_code_counts = Counter()
        self._error_code_counts = Counter()

        self._service_invocation_counts = Counter(
            {
                service_name: 0
                for service_name
                in self.REGISTERED_SERVICES
            }
        )

        self._language_action_counts = Counter(
            {
                action: 0
                for action
                in self.LANGUAGE_ACTIONS
            }
        )

        self._latency_samples = deque(
            maxlen=self.maximum_latency_samples
        )

    def _validate_endpoint(
        self,
        endpoint: str,
    ) -> str:
        normalized_endpoint = str(
            endpoint
        ).strip()

        if normalized_endpoint not in self.registered_endpoints:
            raise ValueError(
                f"Unregistered endpoint metric: "
                f"{normalized_endpoint}"
            )

        return normalized_endpoint

    @staticmethod
    def _validate_latency(
        latency_ms: float,
    ) -> float:
        normalized_latency = float(
            latency_ms
        )

        if (
            not math.isfinite(
                normalized_latency
            )
            or normalized_latency < 0.0
        ):
            raise ValueError(
                "Request latency must be finite and non-negative."
            )

        return normalized_latency

    def record_request(
        self,
        *,
        endpoint: str,
        status_code: int,
        latency_ms: float,
        error_code: str | None = None,
    ) -> None:
        """Record one completed API request."""

        normalized_endpoint = (
            self._validate_endpoint(
                endpoint
            )
        )

        normalized_status_code = int(
            status_code
        )

        if not 100 <= normalized_status_code <= 599:
            raise ValueError(
                "HTTP status code must be between 100 and 599."
            )

        normalized_latency = (
            self._validate_latency(
                latency_ms
            )
        )

        if error_code is not None:
            normalized_error_code = str(
                error_code
            ).strip()

            if not normalized_error_code:
                raise ValueError(
                    "Error code cannot be blank."
                )
        else:
            normalized_error_code = None

        with self._lock:
            self._total_requests += 1
            self._endpoint_counts[
                normalized_endpoint
            ] += 1
            self._status_code_counts[
                str(normalized_status_code)
            ] += 1
            self._latency_samples.append(
                normalized_latency
            )

            if 200 <= normalized_status_code < 400:
                self._successful_requests += 1
            else:
                self._failed_requests += 1

                if normalized_error_code is not None:
                    self._error_code_counts[
                        normalized_error_code
                    ] += 1

    def record_service_invocation(
        self,
        service_name: str,
        count: int = 1,
    ) -> None:
        """Record calls to one controlled internal service."""

        normalized_service_name = str(
            service_name
        ).strip()

        if (
            normalized_service_name
            not in self.REGISTERED_SERVICES
        ):
            raise ValueError(
                f"Unregistered service metric: "
                f"{normalized_service_name}"
            )

        normalized_count = int(
            count
        )

        if normalized_count <= 0:
            raise ValueError(
                "Service invocation count must be positive."
            )

        with self._lock:
            self._service_invocation_counts[
                normalized_service_name
            ] += normalized_count

    def record_language_action(
        self,
        action: str,
        count: int = 1,
    ) -> None:
        """Record accepted generations and safe fallbacks."""

        normalized_action = str(
            action
        ).strip()

        if normalized_action not in self.LANGUAGE_ACTIONS:
            raise ValueError(
                f"Unsupported language guardrail action: "
                f"{normalized_action}"
            )

        normalized_count = int(
            count
        )

        if normalized_count <= 0:
            raise ValueError(
                "Language action count must be positive."
            )

        with self._lock:
            self._language_action_counts[
                normalized_action
            ] += normalized_count

    @staticmethod
    def _percentile_95(
        values: tuple[float, ...],
    ) -> float:
        if not values:
            return 0.0

        ordered_values = sorted(
            values
        )

        rank = max(
            0,
            math.ceil(
                0.95
                * len(ordered_values)
            )
            - 1,
        )

        return float(
            ordered_values[rank]
        )

    def snapshot(
        self,
    ) -> OperationalMetricsSnapshot:
        """Return one internally consistent immutable snapshot."""

        with self._lock:
            total_requests = int(
                self._total_requests
            )
            successful_requests = int(
                self._successful_requests
            )
            failed_requests = int(
                self._failed_requests
            )

            latency_values = tuple(
                self._latency_samples
            )

            endpoint_counts = {
                endpoint: int(
                    self._endpoint_counts[
                        endpoint
                    ]
                )
                for endpoint
                in self.registered_endpoints
            }

            status_code_counts = {
                key: int(value)
                for key, value
                in sorted(
                    self._status_code_counts.items()
                )
            }

            error_code_counts = {
                key: int(value)
                for key, value
                in sorted(
                    self._error_code_counts.items()
                )
            }

            service_invocation_counts = {
                service_name: int(
                    self._service_invocation_counts[
                        service_name
                    ]
                )
                for service_name
                in self.REGISTERED_SERVICES
            }

            accepted_generations = int(
                self._language_action_counts[
                    "accepted_model_generation"
                ]
            )

            fallback_generations = int(
                self._language_action_counts[
                    "safe_template_fallback"
                ]
            )

        if latency_values:
            average_latency = (
                sum(latency_values)
                / len(latency_values)
            )
            maximum_latency = max(
                latency_values
            )
            p95_latency = self._percentile_95(
                latency_values
            )
        else:
            average_latency = 0.0
            maximum_latency = 0.0
            p95_latency = 0.0

        total_language_generations = (
            accepted_generations
            + fallback_generations
        )

        if total_language_generations:
            acceptance_rate = (
                accepted_generations
                / total_language_generations
            )
            fallback_rate = (
                fallback_generations
                / total_language_generations
            )
        else:
            acceptance_rate = 0.0
            fallback_rate = 0.0

        return OperationalMetricsSnapshot(
            service_started_at_utc=(
                self._started_at_utc
            ),
            captured_at_utc=datetime.now(
                timezone.utc
            ),
            uptime_seconds=max(
                0.0,
                time.monotonic()
                - self._started_at_monotonic,
            ),
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            average_latency_ms=float(
                average_latency
            ),
            p95_latency_ms=float(
                p95_latency
            ),
            maximum_latency_ms=float(
                maximum_latency
            ),
            endpoint_request_counts=endpoint_counts,
            status_code_counts=status_code_counts,
            error_code_counts=error_code_counts,
            service_invocation_counts=(
                service_invocation_counts
            ),
            accepted_model_generations=(
                accepted_generations
            ),
            safe_template_fallbacks=(
                fallback_generations
            ),
            raw_generation_acceptance_rate=float(
                acceptance_rate
            ),
            safe_fallback_rate=float(
                fallback_rate
            ),
        )
