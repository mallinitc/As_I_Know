from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.schemas.stage1 import (
    DraftImproveRequest, DraftImproveResponse, DraftValidationRequest, DraftValidationResult,
    Stage1ScenariosResponse, StructuredDraftValidationRequest,
)
from backend.services.stage1 import draft_to_extracted, extract_change, improve, scenarios, validate_draft

router = APIRouter(prefix="/api/v1/agents/change-quality/stage1", tags=["Agent 1 Stage 1"])
logger = logging.getLogger("arca.api")


@router.get("/demo-scenarios", response_model=Stage1ScenariosResponse)
def demo_scenarios(provider: str = "azure") -> Stage1ScenariosResponse:
    if provider not in {"azure", "aws"}:
        raise HTTPException(status_code=422, detail="Stage 1 draft validation supports Azure and AWS.")
    items = scenarios(provider)
    return Stage1ScenariosResponse(provider=provider, count=len(items), items=items)


@router.post("/validate-draft", response_model=DraftValidationResult)
def validate_text(request: DraftValidationRequest) -> DraftValidationResult:
    try:
        return validate_draft(extract_change(request.text, request.provider, request.overrides))
    except Exception:
        logger.exception("Stage 1 pasted-draft validation failed for provider=%s", request.provider)
        raise HTTPException(status_code=500, detail="The pasted change draft could not be validated.") from None


@router.post("/revalidate-draft", response_model=DraftValidationResult)
def revalidate(request: StructuredDraftValidationRequest) -> DraftValidationResult:
    return validate_draft(draft_to_extracted(request.draft))


@router.post("/improve-draft", response_model=DraftImproveResponse)
def improve_draft(request: DraftImproveRequest) -> DraftImproveResponse:
    try:
        return DraftImproveResponse.model_validate(improve(request.extracted_change, request.execution_mode))
    except Exception:
        logger.exception("Stage 1 pasted-draft improvement failed for provider=%s", request.extracted_change.provider)
        raise HTTPException(status_code=500, detail="The improved draft could not be prepared.") from None
