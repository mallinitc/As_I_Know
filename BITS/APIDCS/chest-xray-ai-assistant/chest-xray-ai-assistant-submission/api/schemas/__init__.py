"""Canonical Pydantic schema exports for the API."""

from api.schemas.aggregate import (
    CompleteAnalysisResponse,
    EmbeddedLanguageOutput,
    StoredPredictionResponse,
)
from api.schemas.common import (
    APIErrorResponse,
    ModelVersions,
    StrictSchema,
    SuccessResponseBase,
)
from api.schemas.explainability import (
    ExplainabilityContract,
    GradCAMEvidence,
    ImageAnalysisResponse,
)
from api.schemas.language import (
    LanguageGenerationResponse,
)
from api.schemas.prediction import (
    ClassificationResponse,
    FindingEvidence,
    ImageMetadata,
)
from api.schemas.requests import (
    CompleteAnalysisOptions,
    GroundedGenerationRequest,
    GroundedQuestionRequest,
)
from api.schemas.system import (
    ComponentHealth,
    HealthResponse,
    ModelInfoResponse,
    ModelMetricsResponse,
    OperationalMetricsResponse,
)

__all__ = [
    "APIErrorResponse",
    "ClassificationResponse",
    "CompleteAnalysisOptions",
    "CompleteAnalysisResponse",
    "ComponentHealth",
    "EmbeddedLanguageOutput",
    "ExplainabilityContract",
    "FindingEvidence",
    "GradCAMEvidence",
    "GroundedGenerationRequest",
    "GroundedQuestionRequest",
    "HealthResponse",
    "ImageAnalysisResponse",
    "ImageMetadata",
    "LanguageGenerationResponse",
    "ModelInfoResponse",
    "ModelMetricsResponse",
    "ModelVersions",
    "OperationalMetricsResponse",
    "StoredPredictionResponse",
    "StrictSchema",
    "SuccessResponseBase",
]
