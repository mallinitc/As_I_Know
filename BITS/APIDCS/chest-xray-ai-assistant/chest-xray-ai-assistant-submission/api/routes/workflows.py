
"""Image and grounded-language FastAPI workflow routes."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
)
from starlette.concurrency import (
    run_in_threadpool,
)

from api.core.config import (
    get_settings,
)
from api.core.dependencies import (
    ServiceContainer,
    get_service_container,
)
from api.core.runtime import (
    RequestContext,
)
from api.schemas import (
    ClassificationResponse,
    GroundedGenerationRequest,
    GroundedQuestionRequest,
    ImageAnalysisResponse,
    LanguageGenerationResponse,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["analysis"],
)


async def _read_bounded_upload(
    upload: UploadFile,
) -> bytes:
    """Read at most one byte beyond the configured upload limit."""

    settings = get_settings()

    content = await upload.read(
        settings.maximum_upload_bytes
        + 1
    )

    return content


async def _validate_upload(
    *,
    upload: UploadFile,
    services: ServiceContainer,
):
    """Read, validate, and decode one uploaded image."""

    content = await _read_bounded_upload(
        upload
    )

    return await run_in_threadpool(
        services.image_validation_service
        .validate_and_decode,
        filename=(
            upload.filename
            or "uploaded-image"
        ),
        media_type=(
            upload.content_type
            or ""
        ),
        content=content,
    )


@router.post(
    "/image/classify",
    response_model=ClassificationResponse,
    summary="Classify a chest X-ray image",
)
async def classify_image(
    image: UploadFile = File(...),
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> ClassificationResponse:
    """Run frozen multilabel classification and store the prediction."""

    request_context = RequestContext()

    validated_image = await _validate_upload(
        upload=image,
        services=services,
    )

    execution = await run_in_threadpool(
        services.image_analysis_workflow
        .classify,
        validated_image=validated_image,
        request_context=request_context,
    )

    return execution.response


@router.post(
    "/image/analyze",
    response_model=ImageAnalysisResponse,
    summary="Classify an image and generate visual evidence",
)
async def analyze_image(
    image: UploadFile = File(...),
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> ImageAnalysisResponse:
    """Run classification and threshold-controlled Grad-CAM."""

    request_context = RequestContext()

    validated_image = await _validate_upload(
        upload=image,
        services=services,
    )

    execution = await run_in_threadpool(
        services.image_analysis_workflow
        .analyze,
        validated_image=validated_image,
        request_context=request_context,
    )

    return execution.response


@router.post(
    "/report/generate",
    response_model=LanguageGenerationResponse,
    summary="Generate a grounded preliminary model report",
)
async def generate_report(
    request: GroundedGenerationRequest,
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> LanguageGenerationResponse:
    """Generate a guarded structured report from a stored prediction."""

    request_context = RequestContext()

    execution = await run_in_threadpool(
        services.language_workflow.generate,
        prediction_id=(
            request.prediction_id
        ),
        task_type="structured_report",
        request_context=request_context,
        question=None,
    )

    return execution.response


@router.post(
    "/explanation/generate",
    response_model=LanguageGenerationResponse,
    summary="Generate a grounded plain-language explanation",
)
async def generate_explanation(
    request: GroundedGenerationRequest,
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> LanguageGenerationResponse:
    """Explain stored model output using guarded simple language."""

    request_context = RequestContext()

    execution = await run_in_threadpool(
        services.language_workflow.generate,
        prediction_id=(
            request.prediction_id
        ),
        task_type=(
            "plain_language_explanation"
        ),
        request_context=request_context,
        question=None,
    )

    return execution.response


@router.post(
    "/question/answer",
    response_model=LanguageGenerationResponse,
    summary="Answer a question using stored model output",
)
async def answer_grounded_question(
    request: GroundedQuestionRequest,
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> LanguageGenerationResponse:
    """Answer only from server-controlled stored grounding values."""

    request_context = RequestContext()

    execution = await run_in_threadpool(
        services.language_workflow.generate,
        prediction_id=(
            request.prediction_id
        ),
        task_type=(
            "grounded_question_answering"
        ),
        request_context=request_context,
        question=request.question,
    )

    return execution.response


@router.post(
    "/follow-up/recommend",
    response_model=LanguageGenerationResponse,
    summary="Generate controlled educational follow-up",
)
async def recommend_follow_up(
    request: GroundedGenerationRequest,
    services: ServiceContainer = Depends(
        get_service_container
    ),
) -> LanguageGenerationResponse:
    """Generate non-diagnostic educational follow-up guidance."""

    request_context = RequestContext()

    execution = await run_in_threadpool(
        services.language_workflow.generate,
        prediction_id=(
            request.prediction_id
        ),
        task_type="educational_follow_up",
        request_context=request_context,
        question=None,
    )

    return execution.response
