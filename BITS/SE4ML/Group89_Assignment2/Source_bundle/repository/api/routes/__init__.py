"""Public FastAPI route package."""

from api.routes.aggregate import router as aggregate_router
from api.routes.system import health_router, system_router
from api.routes.workflows import router as workflow_router

__all__ = [
    "aggregate_router",
    "health_router",
    "system_router",
    "workflow_router",
]
