from datetime import datetime

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


ExecutionMode = Annotated[
    Literal["deterministic", "llm_assisted"],
    BeforeValidator(lambda value: str(value).strip().casefold()),
]


class AiAnalysis(BaseModel):
    execution_mode: ExecutionMode = "deterministic"
    llm_invoked: bool = False
    llm_status: str = "not_invoked"
    model_identifier: str | None = None
    ai_summary: str | None = None
    ai_observations: list[str] = Field(default_factory=list)
    ai_recommendations: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    token_usage: dict[str, int] | None = None


class HealthResponse(BaseModel):
    application: str
    api_version: str
    status: str
    mode: str
    timestamp: datetime


class EnvironmentCapability(BaseModel):
    provider: str
    display_name: str
    capabilities: list[str]


class EnvironmentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environments: list[EnvironmentCapability]
