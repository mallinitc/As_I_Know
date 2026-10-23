from __future__ import annotations

import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException

from backend.errors import AwsChangeNotFound, AwsIdentityNotFound, AwsScenarioNotFound
from backend.schemas.aws import (
    AwsAccessValidationResponse,
    AwsChangeValidationResponse,
    AwsChangesResponse,
    AwsDemoScenariosResponse,
    AwsValidationRequest,
    AwsChangeExecutionRequest,
    AwsExecutionResponse,
    AwsExecutionScenariosResponse,
    AwsUserExecutionRequest,
)
from backend.services.aws_execution import AwsExecutionService
from backend.services.aws_validation import AwsValidationService
from backend.services.llm_assistance import attach_ai_analysis


router = APIRouter(prefix="/api/v1/aws", tags=["AWS Change Assurance"])
service = AwsValidationService()
execution_service = AwsExecutionService()
logger = logging.getLogger("arca.api")


@router.get("/changes", response_model=AwsChangesResponse)
def list_changes() -> AwsChangesResponse:
    items = service.list_changes()
    synthetic = service.repository.synthetic
    source = "Synthetic AWS change evidence" if synthetic else "Live AWS evidence (CloudTrail and IAM, ARCA test resources)"
    return AwsChangesResponse(evidence_source=source, synthetic=synthetic, count=len(items), items=items)


@router.get("/demo-scenarios", response_model=AwsDemoScenariosResponse)
def list_demo_scenarios() -> AwsDemoScenariosResponse:
    items = service.list_demo_scenarios()
    return AwsDemoScenariosResponse(synthetic=service.repository.synthetic, count=len(items), items=items)


@router.post("/validate/change", response_model=AwsChangeValidationResponse)
def validate_change(request: AwsValidationRequest) -> AwsChangeValidationResponse:
    started = perf_counter()
    try:
        result = attach_ai_analysis(service.validate_change(request.change_id), "change_quality", request.execution_mode, started_at=started)
        return AwsChangeValidationResponse.model_validate(result)
    except AwsChangeNotFound:
        raise HTTPException(status_code=404, detail=f"AWS change '{request.change_id}' was not found.") from None
    except Exception:
        logger.exception("AWS change validation failed for change_id=%s", request.change_id)
        raise HTTPException(status_code=500, detail="AWS change validation could not be completed.") from None


@router.post("/validate/access", response_model=AwsAccessValidationResponse)
def validate_access(request: AwsValidationRequest) -> AwsAccessValidationResponse:
    started = perf_counter()
    try:
        result = attach_ai_analysis(service.validate_access(request.change_id), "access_intelligence", request.execution_mode, started_at=started)
        return AwsAccessValidationResponse.model_validate(result)
    except AwsChangeNotFound:
        raise HTTPException(status_code=404, detail=f"AWS change '{request.change_id}' was not found.") from None
    except Exception:
        logger.exception("AWS access validation failed for change_id=%s", request.change_id)
        raise HTTPException(status_code=500, detail="AWS access validation could not be completed.") from None

@router.get("/execution-scenarios", response_model=AwsExecutionScenariosResponse)
def list_execution_scenarios() -> AwsExecutionScenariosResponse:
    items = execution_service.scenarios()
    return AwsExecutionScenariosResponse(synthetic=execution_service.repository.synthetic, count=len(items), items=items)

@router.post("/execution-assurance/change", response_model=AwsExecutionResponse)
def assure_change_execution(request: AwsChangeExecutionRequest) -> AwsExecutionResponse:
    started = perf_counter()
    try:
        result = execution_service.assess_change(request.change_id, request.evaluation_timestamp, request.scenario_id)
        return AwsExecutionResponse.model_validate(attach_ai_analysis(result, "execution_assurance", request.execution_mode, started_at=started))
    except AwsChangeNotFound: raise HTTPException(status_code=404, detail=f"AWS change '{request.change_id}' was not found.") from None
    except AwsScenarioNotFound: raise HTTPException(status_code=404, detail="The AWS execution scenario was not found or does not match the change.") from None
    except Exception:
        logger.exception("AWS execution assurance failed for change_id=%s", request.change_id)
        raise HTTPException(status_code=500, detail="AWS execution assurance could not be completed.") from None

@router.post("/execution-assurance/user", response_model=AwsExecutionResponse)
def assure_user_execution(request: AwsUserExecutionRequest) -> AwsExecutionResponse:
    started = perf_counter()
    try:
        result = execution_service.assess_user(request.user_identity, request.window_days, request.evaluation_timestamp, request.scenario_id)
        return AwsExecutionResponse.model_validate(attach_ai_analysis(result, "execution_assurance", request.execution_mode, started_at=started))
    except AwsIdentityNotFound: raise HTTPException(status_code=404, detail="The AWS principal was not found.") from None
    except AwsScenarioNotFound: raise HTTPException(status_code=404, detail="The AWS execution scenario was not found or does not match the principal.") from None
    except Exception:
        logger.exception("AWS principal execution assurance failed")
        raise HTTPException(status_code=500, detail="AWS execution assurance could not be completed.") from None
