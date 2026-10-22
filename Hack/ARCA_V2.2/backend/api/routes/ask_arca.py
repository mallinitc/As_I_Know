from __future__ import annotations
import logging
from fastapi import APIRouter,HTTPException,Request
from backend.auth import principal_from
from backend.schemas.ask_arca import AskArcaRequest,AskArcaResponse,AskCapabilitiesResponse,AskScenariosResponse
from backend.services.ask_arca import AgentConfigurationError,AskArcaService
router=APIRouter(prefix="/api/v1/agents/ask-arca",tags=["Ask ARCA"]); service=AskArcaService(); logger=logging.getLogger("arca.api")
@router.get("/scenarios",response_model=AskScenariosResponse)
def scenarios(request:Request)->AskScenariosResponse:
 principal=principal_from(request); items=service.scenarios() if principal.role=="arca_manager" else []
 return AskScenariosResponse(count=len(items),items=items)
@router.get("/capabilities",response_model=AskCapabilitiesResponse)
def capabilities(request:Request)->AskCapabilitiesResponse:
 principal=principal_from(request); value=service.capabilities()
 if principal.role=="arca_analyst": value={**value,"tools":[]}
 return AskCapabilitiesResponse.model_validate(value)
@router.post("",response_model=AskArcaResponse)
def ask(payload:AskArcaRequest,request:Request)->AskArcaResponse:
 principal=principal_from(request)
 intent=service.parse(payload.question,payload.conversation_context)
 if principal.role=="arca_analyst" and intent["investigation_type"] not in {"greeting","capabilities","unsupported","malformed"}:
  raise HTTPException(status_code=403,detail="The Analyst persona may use Ask ARCA guidance, but evidence tools for access, execution, and undocumented-change investigations require the Manager persona.")
 try:return AskArcaResponse.model_validate(service.ask(**payload.model_dump()))
 except AgentConfigurationError as exc:raise HTTPException(status_code=503,detail=str(exc)) from None
 except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc)) from None
 except Exception:
  logger.exception("Ask ARCA investigation failed"); raise HTTPException(status_code=500,detail="Ask ARCA could not complete the investigation.") from None
