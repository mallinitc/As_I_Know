from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


ROLE_HEADER: Final = "X-ARCA-Demo-Role"
CAPABILITY_HEADER: Final = "X-ARCA-Capability"
PERMISSIONS: Final[dict[str, frozenset[str]]] = {
    "arca_analyst": frozenset({"stage1", "agent5"}),
    "arca_manager": frozenset({"stage2", "stage3", "agent4", "agent5", "executive_dashboard", "analytics_dashboard"}),
}


@dataclass(frozen=True)
class Principal:
    identity: str
    role: str
    demo: bool

    def allows(self, capability: str) -> bool:
        return capability in PERMISSIONS.get(self.role, frozenset())


def demo_persona_enabled() -> bool:
    value = os.getenv("ARCA_DEMO_PERSONA_MODE", "").strip().casefold()
    environment = os.getenv("ARCA_DEPLOYMENT_ENV", "development").strip().casefold()
    return value in {"1", "true", "yes", "on"} and environment in {"local", "development", "dev"}


def capability_for(path: str, method: str, requested: str | None) -> str | None:
    if method == "OPTIONS" or path in {"/api/v1/health", "/api/v1/persona"} or path.startswith(("/docs", "/redoc", "/api/v1/openapi.json")):
        return None
    if path == "/api/v1/environments":
        return "authenticated"
    if path.startswith("/api/v1/agents/change-quality"):
        return "stage1"
    if path.startswith("/api/v1/agents/access-intelligence"):
        return "stage2"
    if path.startswith("/api/v1/investigations/risk"):
        return "agent4"
    if path.startswith("/api/v1/agents/ask-arca"):
        return "agent5"
    if path.startswith("/api/v1/analytics/feedback"):
        return "feedback"
    if path.startswith("/api/v1/analytics/observability"):
        return "analytics_dashboard"
    if path.startswith("/api/v1/analytics"):
        return "executive_dashboard"
    if path.startswith(("/api/v1/aws/", "/api/v1/azure/", "/api/v1/snowflake/")):
        if "/execution-assurance/" in path or path.endswith("/execution-scenarios"):
            return "stage3"
        if path.endswith("/validate/access"):
            return "stage2"
        if path.endswith("/validate/change"):
            return "stage1"
        if path.endswith("/validate"):
            # Snowflake's unified validation serves A1 (stage1) and A2 (stage2).
            return requested if requested in {"stage1", "stage2"} else "unassigned"
        if path.endswith(("/changes", "/demo-scenarios")):
            # The AWS execution-assurance page loads the change catalog under stage3.
            if path == "/api/v1/aws/changes" and requested == "stage3":
                return "stage3"
            return requested if requested in {"stage1", "stage2"} else "unassigned"
    return "unassigned"


def feedback_capability(stage: str) -> str | None:
    return {"A1": "stage1", "A2": "stage2", "A3": "stage3", "A4": "agent4", "A5": "agent5"}.get(stage)


class PersonaAuthorizationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        capability = capability_for(request.url.path, request.method, request.headers.get(CAPABILITY_HEADER))
        if capability == "unassigned" and os.getenv("PYTEST_CURRENT_TEST") and os.getenv("ARCA_TEST_AUTO_ROLE") == "1":
            capability = "stage2"
        if capability is None:
            return await call_next(request)
        if not demo_persona_enabled():
            return JSONResponse(status_code=401, content={"detail": "A verified production identity provider is not configured."})
        role = request.headers.get(ROLE_HEADER, "").strip()
        if not role and os.getenv("PYTEST_CURRENT_TEST") and os.getenv("ARCA_TEST_AUTO_ROLE") == "1":
            role = "arca_analyst" if capability == "stage1" else "arca_manager"
        if role not in PERMISSIONS:
            return JSONResponse(status_code=401, content={"detail": "A valid ARCA persona is required."})
        principal = Principal(identity=f"demo:{role}", role=role, demo=True)
        request.state.principal = principal
        if capability == "unassigned":
            return JSONResponse(status_code=403, content={"detail": "The requested API capability was not assigned."})
        if capability not in {"authenticated", "feedback"} and not principal.allows(capability):
            return JSONResponse(status_code=403, content={"detail": f"The {role} persona is not authorized for {capability}."})
        return await call_next(request)


def principal_from(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise RuntimeError("Authorization middleware did not resolve a principal")
    return principal
