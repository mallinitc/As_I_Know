from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.schemas.change_draft import ChangeDraftRequest, ChangeDraftResponse
from backend.services.change_draft import ChangeDraftNotFound, ChangeDraftService


router = APIRouter(prefix="/api/v1/agents/change-quality", tags=["Agent 1 Change Quality"])
service = ChangeDraftService()
logger = logging.getLogger("arca.api")


@router.post("/improve-draft", response_model=ChangeDraftResponse)
def improve_draft(request: ChangeDraftRequest) -> ChangeDraftResponse:
    try:
        return ChangeDraftResponse.model_validate(service.improve(request.provider, request.change_id, request.execution_mode))
    except ChangeDraftNotFound:
        raise HTTPException(status_code=404, detail="The selected change record was not found.") from None
    except Exception:
        logger.exception("Change draft generation failed for provider=%s change_id=%s", request.provider, request.change_id)
        raise HTTPException(status_code=500, detail="The improved draft could not be prepared.") from None
