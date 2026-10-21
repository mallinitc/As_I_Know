from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.schemas.analytics import AnalyticsAccessResponse, AnalyticsExecutionResponse, AnalyticsOverviewResponse, AnalyticsRisksResponse
from backend.services.analytics import AnalyticsService


router = APIRouter(prefix="/api/v1/analytics", tags=["Executive Analytics"])
service = AnalyticsService()


def _filters(provider: str, days: int | None, severity: str) -> tuple[str, int | None, str]:
    if provider not in {"all", "aws", "azure", "snowflake"}: raise HTTPException(422, "Unsupported provider filter.")
    if days not in {None, 7, 15, 30}: raise HTTPException(422, "Time period must be 7, 15, 30, or omitted for all available evidence.")
    if severity not in {"all", "critical", "high", "medium", "low"}: raise HTTPException(422, "Unsupported severity filter.")
    return provider, days, severity


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def overview(provider: str = Query("all"), days: int | None = Query(None), severity: str = Query("all")) -> AnalyticsOverviewResponse:
    return AnalyticsOverviewResponse.model_validate(service.overview(*_filters(provider, days, severity)))


@router.get("/risks", response_model=AnalyticsRisksResponse)
def risks(provider: str = Query("all"), days: int | None = Query(None), severity: str = Query("all")) -> AnalyticsRisksResponse:
    return AnalyticsRisksResponse.model_validate(service.risks(*_filters(provider, days, severity)))


@router.get("/execution", response_model=AnalyticsExecutionResponse)
def execution(provider: str = Query("all"), days: int | None = Query(None), severity: str = Query("all")) -> AnalyticsExecutionResponse:
    return AnalyticsExecutionResponse.model_validate(service.execution(*_filters(provider, days, severity)))


@router.get("/access", response_model=AnalyticsAccessResponse)
def access(provider: str = Query("all"), days: int | None = Query(None), severity: str = Query("all")) -> AnalyticsAccessResponse:
    return AnalyticsAccessResponse.model_validate(service.access(*_filters(provider, days, severity)))

