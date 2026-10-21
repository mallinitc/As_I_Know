from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException
from backend.schemas.investigation import RiskInvestigationRequest,RiskInvestigationResponse,RiskScenariosResponse
from backend.services.risk_investigation import RiskInvestigationService
from backend.services.llm_assistance import attach_ai_analysis

router=APIRouter(prefix="/api/v1/investigations/risk",tags=["Risk Investigations"]); service=RiskInvestigationService(); logger=logging.getLogger("arca.api")
@router.get("/scenarios",response_model=RiskScenariosResponse)
def scenarios()->RiskScenariosResponse:
    items=service.scenarios(); return RiskScenariosResponse(count=len(items),items=items)
@router.post("",response_model=RiskInvestigationResponse)
def investigate(request:RiskInvestigationRequest)->RiskInvestigationResponse:
    try:
        payload=request.model_dump(exclude={"execution_mode"})
        result=attach_ai_analysis(service.investigate(**payload),"risk_investigation",request.execution_mode)
        return RiskInvestigationResponse.model_validate(result)
    except ValueError as exc: raise HTTPException(status_code=404,detail=str(exc)) from None
    except Exception:
        logger.exception("Risk investigation failed")
        raise HTTPException(status_code=500,detail="Risk investigation could not be completed.") from None
