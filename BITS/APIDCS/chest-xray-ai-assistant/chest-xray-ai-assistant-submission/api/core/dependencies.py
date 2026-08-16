
"""Thread-safe application service dependency container."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from api.core.errors import (
    ModelNotReadyError,
)


@dataclass(frozen=True)
class ServiceContainer:
    """Validated runtime services shared by FastAPI routes."""

    image_validation_service: Any
    computer_vision_service: Any
    prediction_store_service: Any
    gradcam_service: Any
    grounding_serializer: Any
    language_model_service: Any
    language_guardrail_service: Any
    operational_metrics_service: Any
    image_analysis_workflow: Any
    language_workflow: Any
    complete_analysis_workflow: Any

    def readiness(self) -> dict[str, bool]:
        """Return internal component readiness without sensitive values."""

        cv_model = getattr(
            self.computer_vision_service,
            "model",
            None,
        )

        language_model = getattr(
            self.language_model_service,
            "model",
            None,
        )

        return {
            "image_validation": (
                self.image_validation_service
                is not None
            ),
            "computer_vision": (
                cv_model is not None
                and not cv_model.training
            ),
            "prediction_store": (
                self.prediction_store_service
                is not None
            ),
            "gradcam": (
                self.gradcam_service
                is not None
            ),
            "grounding_serializer": (
                self.grounding_serializer
                is not None
            ),
            "grounded_language": (
                language_model is not None
                and not language_model.training
            ),
            "language_guardrail": (
                self.language_guardrail_service
                is not None
            ),
            "operational_metrics": (
                self.operational_metrics_service
                is not None
            ),
            "image_workflow": (
                self.image_analysis_workflow
                is not None
            ),
            "language_workflow": (
                self.language_workflow
                is not None
            ),
            "complete_workflow": (
                self.complete_analysis_workflow
                is not None
            ),
        }

    @property
    def ready(self) -> bool:
        """Return true only when every registered component is ready."""

        return all(
            self.readiness().values()
        )


_container_lock = threading.RLock()
_service_container: ServiceContainer | None = None


def configure_service_container(
    container: ServiceContainer,
    *,
    replace: bool = False,
) -> ServiceContainer:
    """Register one complete service container."""

    if not isinstance(
        container,
        ServiceContainer,
    ):
        raise TypeError(
            "The application dependency must be a ServiceContainer."
        )

    if not container.ready:
        failed_components = [
            component_name
            for component_name, ready
            in container.readiness().items()
            if not ready
        ]

        raise ModelNotReadyError(
            details={
                "components": (
                    failed_components
                )
            }
        )

    global _service_container

    with _container_lock:
        if (
            _service_container is not None
            and not replace
        ):
            raise RuntimeError(
                "The service container is already configured."
            )

        _service_container = container

    return container


def get_service_container() -> ServiceContainer:
    """FastAPI dependency that returns the configured services."""

    with _container_lock:
        container = _service_container

    if container is None:
        raise ModelNotReadyError(
            details={
                "component": (
                    "service_container"
                )
            }
        )

    if not container.ready:
        failed_components = [
            component_name
            for component_name, ready
            in container.readiness().items()
            if not ready
        ]

        raise ModelNotReadyError(
            details={
                "components": (
                    failed_components
                )
            }
        )

    return container


def service_container_is_configured() -> bool:
    """Return the non-sensitive configuration state."""

    with _container_lock:
        return (
            _service_container is not None
            and _service_container.ready
        )


def clear_service_container() -> None:
    """Remove the container for controlled test isolation."""

    global _service_container

    with _container_lock:
        _service_container = None
