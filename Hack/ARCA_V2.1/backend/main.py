from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import PROJECT_ROOT, cors_origins, log_path

load_dotenv(PROJECT_ROOT / ".env", override=False)

from backend.api.routes.health import router as health_router
from backend.api.routes.azure import router as azure_router
from backend.api.routes.aws import router as aws_router
from backend.api.routes.snowflake import router as snowflake_router
from backend.api.routes.investigations import router as investigations_router
from backend.api.routes.ask_arca import router as ask_arca_router
from backend.api.routes.analytics import router as analytics_router
from backend.api.routes.change_draft import router as change_draft_router


def _configure_logging() -> None:
    logger = logging.getLogger("arca.api")
    if any(getattr(handler, "name", None) == "arca-v2-api-file" for handler in logger.handlers):
        return
    directory = log_path() / "api"
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / "backend.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.name = "arca-v2-api-file"
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def create_app() -> FastAPI:
    _configure_logging()
    application = FastAPI(
        title="ARCA V2 API",
        description="Read-only API foundation exposing existing ARCA assurance engines over synthetic evidence.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/v1/openapi.json",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    application.include_router(health_router)
    application.include_router(azure_router)
    application.include_router(aws_router)
    application.include_router(snowflake_router)
    application.include_router(investigations_router)
    application.include_router(ask_arca_router)
    application.include_router(analytics_router)
    application.include_router(change_draft_router)

    @application.exception_handler(Exception)
    async def unhandled_exception(_request: Request, exception: Exception) -> JSONResponse:
        logging.getLogger("arca.api").exception("Unhandled API error", exc_info=exception)
        return JSONResponse(status_code=500, content={"detail": "An internal API error occurred."})

    return application


app = create_app()
