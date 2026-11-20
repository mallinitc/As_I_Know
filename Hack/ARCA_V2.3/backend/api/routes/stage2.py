from __future__ import annotations

import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException

from backend.schemas.stage2 import Stage2AssessmentRequest, Stage2AssessmentResponse, Stage2ScenariosResponse
from backend.services.stage2 import Stage2Service
from backend.services.llm_assistance import attach_ai_analysis

router = APIRouter(prefix="/api/v1/agents/access-intelligence/stage2", tags=["Agent 2 Stage 2"])
service = Stage2Service()
logger = logging.getLogger("arca.api")


@router.get("/demo-scenarios", response_model=Stage2ScenariosResponse)
def demo_scenarios() -> Stage2ScenariosResponse:
    items = service.scenarios()
    return Stage2ScenariosResponse(count=len(items), items=items)


@router.get("/scenario-records")
def scenario_records(request_ids: str) -> dict[str, str]:
    ids = [value.strip() for value in request_ids.split(",") if value.strip()]
    return {"records_text": service.scenario_records(ids)}


@router.post("/assess", response_model=Stage2AssessmentResponse)
def assess(request: Stage2AssessmentRequest) -> Stage2AssessmentResponse:
    started = perf_counter()
    if request.mode == "change" and not request.change_id:
        raise HTTPException(status_code=422, detail="A change number is required.")
    if request.mode == "user" and not request.user_identity:
        raise HTTPException(status_code=422, detail="An Azure UPN or Entra object ID is required.")
    if request.mode == "paste" and not request.records_text.strip():
        raise HTTPException(status_code=422, detail="One or more PIM records are required.")
    try:
        result = service.assess(request.mode, request.change_id, request.user_identity, request.access_state, request.records_text, request.evaluation_timestamp)
        return Stage2AssessmentResponse.model_validate(attach_ai_analysis(result, "access_intelligence", request.execution_mode, started_at=started))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        logger.exception("Stage 2 assessment failed mode=%s", request.mode)
        raise HTTPException(status_code=500, detail="The Stage 2 access assessment could not be completed.") from None
