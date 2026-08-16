
"""Standalone construction of all FastAPI runtime services."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import torch
import yaml

from api.core.config import (
    get_settings,
)
from api.core.dependencies import (
    ServiceContainer,
    configure_service_container,
    get_service_container,
    service_container_is_configured,
)
from api.core.runtime import (
    build_success_metadata,
)
from api.core.telemetry import (
    EndpointTelemetryAdapter,
)
from api.schemas import (
    ExplainabilityContract,
    GradCAMEvidence,
)
from src.services.complete_workflow_service import (
    CompleteAnalysisWorkflow,
)
from src.services.computer_vision_service import (
    ComputerVisionService,
)
from src.services.gradcam_service import (
    GradCAMService,
)
from src.services.grounding_service import (
    GroundedInputSerializer,
    TASK_PREFIXES,
)
from src.services.image_service import (
    ImageValidationService,
)
from src.services.image_workflow_service import (
    ImageAnalysisWorkflow,
)
from src.services.language_guardrail_service import (
    DeterministicLanguageGuardrail,
)
from src.services.language_model_service import (
    GroundedLanguageModelService,
)
from src.services.language_workflow_service import (
    StoredPredictionLanguageWorkflow,
)
from src.services.operational_metrics_service import (
    OperationalMetricsService,
)
from src.services.prediction_store_service import (
    PredictionStoreService,
)


REGISTERED_ENDPOINTS = (
    "GET /health",
    "GET /api/v1/model/info",
    "GET /api/v1/model/metrics",
    "POST /api/v1/image/classify",
    "POST /api/v1/image/analyze",
    "POST /api/v1/report/generate",
    "POST /api/v1/explanation/generate",
    "POST /api/v1/question/answer",
    "POST /api/v1/follow-up/recommend",
    "POST /api/v1/analyze-complete",
    "GET /api/v1/predictions/{prediction_id}",
    "GET /api/v1/llmops/metrics",
)


_factory_lock = threading.RLock()


def _load_yaml(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as yaml_file:
        loaded_value = yaml.safe_load(
            yaml_file
        )

    if not isinstance(
        loaded_value,
        dict,
    ):
        raise ValueError(
            "A required YAML configuration is invalid."
        )

    return loaded_value


def _load_json(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as json_file:
        loaded_value = json.load(
            json_file
        )

    if not isinstance(
        loaded_value,
        dict,
    ):
        raise ValueError(
            "A required JSON configuration is invalid."
        )

    return loaded_value


def _find_named_text(
    value: Any,
    required_terms: tuple[str, ...],
    path: tuple[str, ...] = (),
) -> str | None:
    """Resolve controlled text across nested configuration versions."""

    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = "".join(
                character.lower()
                for character in str(key)
                if character.isalnum()
            )

            current_path = (
                *path,
                normalized_key,
            )

            path_text = "".join(
                current_path
            )

            if (
                all(
                    term in path_text
                    for term in required_terms
                )
                and isinstance(
                    nested_value,
                    str,
                )
                and nested_value.strip()
            ):
                return nested_value.strip()

            located_value = _find_named_text(
                nested_value,
                required_terms,
                current_path,
            )

            if located_value is not None:
                return located_value

    elif isinstance(value, list):
        for item in value:
            located_value = _find_named_text(
                item,
                required_terms,
                path,
            )

            if located_value is not None:
                return located_value

    elif (
        isinstance(value, str)
        and value.strip()
        and all(
            term in "".join(path)
            for term in required_terms
        )
    ):
        return value.strip()

    return None


def _resolve_path(
    settings: Any,
    *,
    attribute_names: tuple[str, ...],
    fallback: Path,
) -> Path:
    for attribute_name in attribute_names:
        value = getattr(
            settings,
            attribute_name,
            None,
        )

        if value is not None:
            return Path(
                value
            )

    return fallback


def build_default_service_container(
    *,
    replace: bool = False,
) -> ServiceContainer:
    """Construct every service from frozen versioned artifacts."""

    with _factory_lock:
        if (
            service_container_is_configured()
            and not replace
        ):
            return get_service_container()

        settings = get_settings()

        solution_root = Path(
            settings.solution_root
        )

        data_root = Path(
            settings.data_root
        )

        finding_contract_path = (
            solution_root
            / "configs"
            / "finding_contract.yaml"
        )

        prompt_registry_path = (
            solution_root
            / "configs"
            / "prompt_registry.yaml"
        )

        explainability_template_path = (
            solution_root
            / "configs"
            / "explainability_response_templates.json"
        )

        language_model_directory = (
            _resolve_path(
                settings,
                attribute_names=(
                    "language_model_directory",
                    "language_model_path",
                ),
                fallback=(
                    data_root
                    / "models"
                    / settings.language_model_version
                ),
            )
        )

        finding_contract = _load_yaml(
            finding_contract_path
        )

        prompt_registry = _load_yaml(
            prompt_registry_path
        )

        explainability_templates = (
            _load_json(
                explainability_template_path
            )
        )

        educational_limitation = (
            _find_named_text(
                finding_contract,
                (
                    "educational",
                    "limitation",
                ),
            )
        )

        gradcam_limitation = (
            _find_named_text(
                finding_contract,
                (
                    "gradcam",
                    "limitation",
                ),
            )
            or _find_named_text(
                finding_contract,
                (
                    "gradcam",
                    "boundary",
                ),
            )
        )

        professional_review_guidance = (
            _find_named_text(
                finding_contract,
                (
                    "professional",
                    "review",
                ),
            )
        )

        optional_value_marker = (
            _find_named_text(
                prompt_registry,
                (
                    "optional",
                    "marker",
                ),
            )
            or "not_applicable"
        )

        if educational_limitation is None:
            raise KeyError(
                "The educational limitation is unavailable."
            )

        if gradcam_limitation is None:
            raise KeyError(
                "The Grad-CAM limitation is unavailable."
            )

        if professional_review_guidance is None:
            raise KeyError(
                "Professional-review guidance is unavailable."
            )

        image_validation_service = (
            ImageValidationService(
                settings=settings
            )
        )

        computer_vision_service = (
            ComputerVisionService(
                settings=settings,
                device=None,
            )
        )

        prediction_store_service = (
            PredictionStoreService(
                maximum_records=1000,
                retention_hours=24,
            )
        )

        gradcam_service = GradCAMService(
            model=(
                computer_vision_service.model
            ),
            device=(
                computer_vision_service.device
            ),
            limitation=(
                gradcam_limitation
            ),
            image_size=224,
            overlay_alpha=0.40,
        )

        grounding_serializer = (
            GroundedInputSerializer(
                language_model_version=(
                    settings
                    .language_model_version
                ),
                limitation_boundary=(
                    educational_limitation
                ),
                optional_value_marker=(
                    optional_value_marker
                ),
                task_prefixes=(
                    TASK_PREFIXES
                ),
            )
        )

        language_model_service = (
            GroundedLanguageModelService(
                model_directory=(
                    language_model_directory
                ),
                model_version=(
                    settings
                    .language_model_version
                ),
                device=(
                    "cuda"
                    if torch.cuda.is_available()
                    else "cpu"
                ),
                use_bfloat16=True,
            )
        )

        language_guardrail_service = (
            DeterministicLanguageGuardrail(
                educational_limitation=(
                    educational_limitation
                ),
                gradcam_limitation=(
                    gradcam_limitation
                ),
                professional_review_guidance=(
                    professional_review_guidance
                ),
            )
        )

        base_operational_metrics = (
            OperationalMetricsService(
                registered_endpoints=(
                    REGISTERED_ENDPOINTS
                ),
                maximum_latency_samples=10_000,
            )
        )

        operational_metrics_service = (
            EndpointTelemetryAdapter(
                base_operational_metrics
            )
        )

        explainability_contract = (
            ExplainabilityContract
            .model_validate(
                explainability_templates[
                    "contract"
                ]
            )
        )

        evidence_template = (
            GradCAMEvidence.model_validate(
                explainability_templates[
                    "evidence"
                ]
            )
        )

        image_analysis_workflow = (
            ImageAnalysisWorkflow(
                computer_vision_service=(
                    computer_vision_service
                ),
                gradcam_service=(
                    gradcam_service
                ),
                prediction_store=(
                    prediction_store_service
                ),
                operational_metrics=(
                    operational_metrics_service
                ),
                metadata_builder=(
                    build_success_metadata
                ),
                explainability_contract=(
                    explainability_contract
                ),
                evidence_template=(
                    evidence_template
                ),
            )
        )

        language_workflow = (
            StoredPredictionLanguageWorkflow(
                prediction_store=(
                    prediction_store_service
                ),
                grounding_serializer=(
                    grounding_serializer
                ),
                language_model_service=(
                    language_model_service
                ),
                language_guardrail=(
                    language_guardrail_service
                ),
                operational_metrics=(
                    operational_metrics_service
                ),
                metadata_builder=(
                    build_success_metadata
                ),
            )
        )

        complete_analysis_workflow = (
            CompleteAnalysisWorkflow(
                image_workflow=(
                    image_analysis_workflow
                ),
                language_workflow=(
                    language_workflow
                ),
                prediction_store=(
                    prediction_store_service
                ),
                operational_metrics=(
                    operational_metrics_service
                ),
                metadata_builder=(
                    build_success_metadata
                ),
            )
        )

        container = ServiceContainer(
            image_validation_service=(
                image_validation_service
            ),
            computer_vision_service=(
                computer_vision_service
            ),
            prediction_store_service=(
                prediction_store_service
            ),
            gradcam_service=(
                gradcam_service
            ),
            grounding_serializer=(
                grounding_serializer
            ),
            language_model_service=(
                language_model_service
            ),
            language_guardrail_service=(
                language_guardrail_service
            ),
            operational_metrics_service=(
                operational_metrics_service
            ),
            image_analysis_workflow=(
                image_analysis_workflow
            ),
            language_workflow=(
                language_workflow
            ),
            complete_analysis_workflow=(
                complete_analysis_workflow
            ),
        )

        return configure_service_container(
            container,
            replace=replace,
        )


def ensure_default_service_container() -> ServiceContainer:
    """Return the configured container or construct it once."""

    if service_container_is_configured():
        return get_service_container()

    return build_default_service_container()
