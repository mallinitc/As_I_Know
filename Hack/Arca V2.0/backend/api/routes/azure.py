from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.errors import AzureChangeNotFound, AzureIdentityAmbiguous, AzureIdentityNotFound, AzureScenarioNotFound
from backend.schemas.azure import (
    AzureAccessValidationResponse,
    AzureChangeValidationResponse,
    AzureChangesResponse,
    AzureDemoScenariosResponse,
    AzureValidationRequest,
    AzureChangeExecutionRequest,
    AzureExecutionResponse,
    AzureExecutionScenariosResponse,
    AzureUserExecutionRequest,
)
from backend.services.azure_execution import AzureExecutionService
from backend.services.azure_validation import AzureValidationService
from backend.services.llm_assistance import attach_ai_analysis


router = APIRouter(prefix="/api/v1/azure", tags=["Azure Change Assurance"])
service = AzureValidationService()
execution_service = AzureExecutionService()
logger = logging.getLogger("arca.api")


@router.get("/changes", response_model=AzureChangesResponse)
def list_changes() -> AzureChangesResponse:
    items = service.list_changes()
    return AzureChangesResponse(
        evidence_source="Synthetic Azure ServiceNow change evidence",
        count=len(items), items=items,
    )


@router.get("/demo-scenarios", response_model=AzureDemoScenariosResponse)
def list_demo_scenarios() -> AzureDemoScenariosResponse:
    items = service.list_demo_scenarios()
    return AzureDemoScenariosResponse(count=len(items), items=items)


@router.post("/validate/change", response_model=AzureChangeValidationResponse)
def validate_change(request: AzureValidationRequest) -> AzureChangeValidationResponse:
    try:
        result = attach_ai_analysis(service.validate_change(request.change_id), "change_quality", request.execution_mode)
        return AzureChangeValidationResponse.model_validate(result)
    except AzureChangeNotFound:
        raise HTTPException(status_code=404, detail=f"Azure change '{request.change_id}' was not found.") from None
    except Exception:
        logger.exception("Azure change-quality validation failed for change_id=%s", request.change_id)
        raise HTTPException(status_code=500, detail="Azure change validation could not be completed.") from None


@router.post("/validate/access", response_model=AzureAccessValidationResponse)
def validate_access(request: AzureValidationRequest) -> AzureAccessValidationResponse:
    try:
        result = service.validate_access(request.change_id, request.pim_request_id)
        return AzureAccessValidationResponse.model_validate(attach_ai_analysis(result, "access_intelligence", request.execution_mode))
    except AzureChangeNotFound:
        raise HTTPException(status_code=404, detail=f"Azure change '{request.change_id}' was not found.") from None
    except Exception:
        logger.exception("Azure access validation failed for change_id=%s", request.change_id)
        raise HTTPException(status_code=500, detail="Azure access validation could not be completed.") from None


@router.get("/execution-scenarios", response_model=AzureExecutionScenariosResponse)
def list_execution_scenarios() -> AzureExecutionScenariosResponse:
    items = execution_service.scenarios()
    return AzureExecutionScenariosResponse(count=len(items), items=items)


@router.post("/execution-assurance/change", response_model=AzureExecutionResponse)
def assure_change_execution(request: AzureChangeExecutionRequest) -> AzureExecutionResponse:
    try:
        result = execution_service.assess_change(request.change_id, request.evaluation_timestamp, request.scenario_id)
        return AzureExecutionResponse.model_validate(attach_ai_analysis(result, "execution_assurance", request.execution_mode))
    except AzureChangeNotFound:
        raise HTTPException(status_code=404, detail=f"Azure change '{request.change_id}' was not found.") from None
    except AzureScenarioNotFound:
        raise HTTPException(status_code=404, detail="The execution scenario was not found or does not match the selected change.") from None
    except Exception:
        logger.exception("Azure execution assurance failed for change_id=%s", request.change_id)
        raise HTTPException(status_code=500, detail="Azure execution assurance could not be completed.") from None


@router.post("/execution-assurance/user", response_model=AzureExecutionResponse)
def assure_user_execution(request: AzureUserExecutionRequest) -> AzureExecutionResponse:
    try:
        result = execution_service.assess_user(request.user_identity, request.window_days, request.evaluation_timestamp, request.scenario_id)
        return AzureExecutionResponse.model_validate(attach_ai_analysis(result, "execution_assurance", request.execution_mode))
    except AzureIdentityNotFound:
        raise HTTPException(status_code=404, detail="The Azure identity was not found.") from None
    except AzureIdentityAmbiguous:
        raise HTTPException(status_code=409, detail="The Azure identity is ambiguous.") from None
    except AzureScenarioNotFound:
        raise HTTPException(status_code=404, detail="The execution scenario was not found or does not match the selected identity.") from None
    except Exception:
        logger.exception("Azure user execution assurance failed")
        raise HTTPException(status_code=500, detail="Azure execution assurance could not be completed.") from None
