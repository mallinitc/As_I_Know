from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from backend.errors import (
    SnowflakeChangeNotFound,
    SnowflakeIdentityAmbiguous,
    SnowflakeIdentityNotFound,
    SnowflakeScenarioNotFound,
)
from backend.schemas.snowflake import (
    SnowflakeChangesResponse,
    SnowflakeDemoScenariosResponse,
    SnowflakeValidationRequest,
    SnowflakeValidationResponse,
    SnowflakeChangeExecutionRequest,
    SnowflakeExecutionResponse,
    SnowflakeExecutionScenariosResponse,
    SnowflakeUserExecutionRequest,
)
from backend.services.snowflake import SnowflakeValidationService
from backend.services.snowflake_execution import SnowflakeExecutionService
from backend.services.llm_assistance import attach_ai_analysis

router = APIRouter(prefix="/api/v1/snowflake", tags=["Snowflake Change Assurance"])
service = SnowflakeValidationService()
execution_service = SnowflakeExecutionService()
logger = logging.getLogger("arca.api")
EVIDENCE_SOURCE = "Synthetic Snowflake change-management evidence"


@router.get("/changes", response_model=SnowflakeChangesResponse, summary="List synthetic Snowflake changes")
def list_changes() -> SnowflakeChangesResponse:
    items = service.list_changes()
    return SnowflakeChangesResponse(evidence_source=EVIDENCE_SOURCE, count=len(items), items=items)


@router.get("/demo-scenarios", response_model=SnowflakeDemoScenariosResponse, summary="List verified Snowflake demo scenarios")
def list_demo_scenarios() -> SnowflakeDemoScenariosResponse:
    items = service.list_demo_scenarios()
    return SnowflakeDemoScenariosResponse(count=len(items), items=items)


@router.post(
    "/validate",
    response_model=SnowflakeValidationResponse,
    summary="Run unified Snowflake change and access validation",
    responses={
        404: {"description": "Change ID was not found in synthetic evidence"},
        422: {"description": "Request validation failed"},
        500: {"description": "Validation could not be completed"},
    },
)
def validate_change(request: SnowflakeValidationRequest) -> SnowflakeValidationResponse:
    try:
        result = attach_ai_analysis(service.validate(request.change_id, request.evaluation_timestamp), "snowflake_change_access", request.execution_mode)
        return SnowflakeValidationResponse.model_validate(result)
    except SnowflakeChangeNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snowflake change '{request.change_id}' was not found.",
        ) from None
    except Exception:
        logger.exception("Snowflake validation failed for change_id=%s", request.change_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Snowflake validation could not be completed.",
        ) from None


@router.get(
    "/execution-scenarios",
    response_model=SnowflakeExecutionScenariosResponse,
    summary="List verified Snowflake post-implementation scenarios",
)
def list_execution_scenarios() -> SnowflakeExecutionScenariosResponse:
    items = execution_service.scenarios()
    return SnowflakeExecutionScenariosResponse(count=len(items), items=items)


@router.post(
    "/execution-assurance/change",
    response_model=SnowflakeExecutionResponse,
    summary="Compare an approved change with Snowflake execution evidence",
)
def assure_change_execution(request: SnowflakeChangeExecutionRequest) -> SnowflakeExecutionResponse:
    try:
        deterministic = execution_service.assess_change(
            request.change_id, request.evaluation_timestamp, request.scenario_id,
        )
        result = attach_ai_analysis(deterministic, "execution_assurance", request.execution_mode)
        return SnowflakeExecutionResponse.model_validate(result)
    except SnowflakeChangeNotFound:
        raise HTTPException(status_code=404, detail=f"Snowflake change '{request.change_id}' was not found.") from None
    except SnowflakeScenarioNotFound:
        raise HTTPException(status_code=404, detail="The requested execution scenario was not found or does not match the selected change.") from None
    except Exception:
        logger.exception("Snowflake change execution assurance failed for change_id=%s", request.change_id)
        raise HTTPException(status_code=500, detail="Snowflake execution assurance could not be completed.") from None


@router.post(
    "/execution-assurance/user",
    response_model=SnowflakeExecutionResponse,
    summary="Investigate Snowflake activity for a resolved user identity",
)
def assure_user_execution(request: SnowflakeUserExecutionRequest) -> SnowflakeExecutionResponse:
    try:
        deterministic = execution_service.assess_user(
            request.user_identity, request.window_days, request.evaluation_timestamp, request.scenario_id,
        )
        result = attach_ai_analysis(deterministic, "execution_assurance", request.execution_mode)
        return SnowflakeExecutionResponse.model_validate(result)
    except SnowflakeIdentityNotFound:
        raise HTTPException(status_code=404, detail="The Snowflake user identity was not found.") from None
    except SnowflakeIdentityAmbiguous:
        raise HTTPException(status_code=409, detail="The Snowflake user identity is ambiguous.") from None
    except SnowflakeScenarioNotFound:
        raise HTTPException(status_code=404, detail="The requested execution scenario was not found or does not match the selected user.") from None
    except Exception:
        logger.exception("Snowflake user execution assurance failed")
        raise HTTPException(status_code=500, detail="Snowflake execution assurance could not be completed.") from None
