"""Complete-analysis and stored-prediction FastAPI routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from api.core.dependencies import ServiceContainer, get_service_container
from api.core.runtime import RequestContext, build_success_metadata
from api.routes.workflows import _validate_upload
from api.schemas import (
    CompleteAnalysisOptions,
    CompleteAnalysisResponse,
    StoredPredictionResponse,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["complete-analysis"],
)


@router.post(
    "/analyze-complete",
    response_model=CompleteAnalysisResponse,
    summary="Run the complete chest X-ray analysis workflow",
)
async def analyze_complete(
    image: UploadFile = File(...),
    question: str | None = Form(default=None),
    services: ServiceContainer = Depends(get_service_container),
) -> CompleteAnalysisResponse:
    """Run classification, Grad-CAM, and guarded language generation."""

    request_context = RequestContext()

    options = CompleteAnalysisOptions(question=question)

    validated_image = await _validate_upload(
        upload=image,
        services=services,
    )

    execution = await run_in_threadpool(
        services.complete_analysis_workflow.analyze_complete,
        validated_image=validated_image,
        request_context=request_context,
        question=options.question,
    )

    return execution.response


@router.get(
    "/predictions/{prediction_id}",
    response_model=StoredPredictionResponse,
    summary="Retrieve one stored prediction",
)
async def get_prediction(
    prediction_id: UUID,
    services: ServiceContainer = Depends(get_service_container),
) -> StoredPredictionResponse:
    """Return one stored prediction and its attached outputs."""

    request_context = RequestContext()

    stored_record = await run_in_threadpool(
        services.prediction_store_service.get,
        prediction_id,
    )

    services.operational_metrics_service.record_service_invocation("prediction_store")

    include_language = bool(stored_record.language_outputs)

    include_explainability = stored_record.explainability is not None

    response_metadata = build_success_metadata(
        request_context,
        include_language=include_language,
        include_explainability=(include_explainability),
    )

    return await run_in_threadpool(
        services.prediction_store_service.build_response,
        prediction_id=prediction_id,
        response_metadata=response_metadata,
    )
