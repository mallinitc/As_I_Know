from datetime import datetime

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


ExecutionMode = Annotated[
    Literal["deterministic", "llm_assisted"],
    BeforeValidator(lambda value: str(value).strip().casefold()),
]


class AiCallDetail(BaseModel):
    operation: str
    attempt: int = 1
    status: str
    provider: str = ""
    model_identifier: str = ""
    duration_ms: float = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class AiExecutionMetrics(BaseModel):
    agent_id: str
    environment: str | None = None
    execution_mode: str
    provider: str | None = None
    model_identifier: str | None = None
    llm_invocation_status: str
    model_call_count: int = 0
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    total_tokens: int | None = 0
    model_execution_time_ms: float = 0
    total_analysis_time_ms: float = 0
    estimated_cost_usd: float | None = None
    pricing_catalog_version: str | None = None
    cost_status: str = "not_applicable"
    call_details: list[AiCallDetail] = Field(default_factory=list)


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
    token_usage: dict[str, Any] | None = None
    execution_metrics: AiExecutionMetrics | None = None


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
