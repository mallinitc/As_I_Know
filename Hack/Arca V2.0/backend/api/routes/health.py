from datetime import datetime, timezone

from fastapi import APIRouter

from backend.providers import PROVIDERS
from backend.schemas.common import EnvironmentCapability, EnvironmentsResponse, HealthResponse

router = APIRouter(prefix="/api/v1", tags=["Platform"])


@router.get("/health", response_model=HealthResponse, summary="Check API health")
def health() -> HealthResponse:
    return HealthResponse(
        application="ARCA V2 API",
        api_version="v1",
        status="healthy",
        mode="synthetic-read-only",
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/environments", response_model=EnvironmentsResponse, summary="List registered evidence providers")
def environments() -> EnvironmentsResponse:
    items = [
        EnvironmentCapability(
            provider=definition.name,
            display_name=definition.display_name,
            capabilities=list(definition.capabilities),
        )
        for definition in PROVIDERS.values()
    ]
    return EnvironmentsResponse(environments=items)
