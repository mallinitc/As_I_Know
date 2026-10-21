from __future__ import annotations
import logging
from fastapi import APIRouter,HTTPException
from backend.schemas.ask_arca import AskArcaRequest,AskArcaResponse,AskCapabilitiesResponse,AskScenariosResponse
from backend.services.ask_arca import AgentConfigurationError,AskArcaService
router=APIRouter(prefix="/api/v1/agents/ask-arca",tags=["Ask ARCA"]); service=AskArcaService(); logger=logging.getLogger("arca.api")
@router.get("/scenarios",response_model=AskScenariosResponse)
def scenarios()->AskScenariosResponse:
 items=service.scenarios(); return AskScenariosResponse(count=len(items),items=items)
@router.get("/capabilities",response_model=AskCapabilitiesResponse)
def capabilities()->AskCapabilitiesResponse:return AskCapabilitiesResponse.model_validate(service.capabilities())
@router.post("",response_model=AskArcaResponse)
def ask(request:AskArcaRequest)->AskArcaResponse:
 try:return AskArcaResponse.model_validate(service.ask(**request.model_dump()))
 except AgentConfigurationError as exc:raise HTTPException(status_code=503,detail=str(exc)) from None
 except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc)) from None
 except Exception:
  logger.exception("Ask ARCA investigation failed"); raise HTTPException(status_code=500,detail="Ask ARCA could not complete the investigation.") from None
