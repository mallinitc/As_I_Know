from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from backend.schemas.common import AiAnalysis, ExecutionMode


class SnowflakeValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "examples": [{"change_id": "CHG-SF-1007", "evaluation_timestamp": "2026-10-21T10:30:00Z"}]
    })

    change_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    evaluation_timestamp: AwareDatetime | None = Field(
        default=None,
        description="Optional timezone-aware evaluation instant. Current UTC is used when omitted.",
    )
    execution_mode: ExecutionMode = "deterministic"

    @field_validator("change_id")
    @classmethod
    def normalize_change_id(cls, value: str) -> str:
        return value.strip().upper()


class AssessmentSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    evidence: list[Any] = Field(default_factory=list)
    findings: list[Any] = Field(default_factory=list)


class SnowflakeValidationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int
    change_id: str
    provider: Literal["snowflake"]
    status: str
    overall_status: str
    change_quality: AssessmentSection
    window_assessment: AssessmentSection
    role_assessment: AssessmentSection
    missing_information: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[Any] = Field(default_factory=list)
    evaluation_timestamp: datetime
    warning: str | None = None
    ai_analysis: AiAnalysis | None = None


class SnowflakeChangeRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    change_id: str
    provider: str = "snowflake"
    short_description: str = ""
    description: str = ""
    state: str = ""
    environment: str = ""
    start: str | None = None
    end: str | None = None
    expected: list[dict[str, Any]] = Field(default_factory=list)


class SnowflakeChangesResponse(BaseModel):
    provider: Literal["snowflake"] = "snowflake"
    evidence_source: str
    synthetic: Literal[True] = True
    count: int
    items: list[SnowflakeChangeRecord]


class SnowflakeDemoScenario(BaseModel):
    model_config = ConfigDict(extra="allow")

    scenario_id: str
    scenario_name: str
    description: str
    change_id: str
    evaluation_timestamp: AwareDatetime
    expected_check_outcomes: dict[str, str]


class SnowflakeDemoScenariosResponse(BaseModel):
    provider: Literal["snowflake"] = "snowflake"
    synthetic: Literal[True] = True
    count: int
    items: list[SnowflakeDemoScenario]


class SnowflakeExecutionScenario(BaseModel):
    model_config = ConfigDict(extra="allow")

    scenario_id: str
    scenario_name: str
    change_id: str | None = None
    user_identity: str | None = None
    evaluation_timestamp: AwareDatetime
    investigation_mode: Literal["change", "user"]
    evidence_query_ids: list[str]
    window_days: int
    expected_findings: list[str]


class SnowflakeExecutionScenariosResponse(BaseModel):
    provider: Literal["snowflake"] = "snowflake"
    synthetic: Literal[True] = True
    count: int
    items: list[SnowflakeExecutionScenario]


class SnowflakeChangeExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    evaluation_timestamp: AwareDatetime | None = None
    scenario_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    execution_mode: ExecutionMode = "deterministic"

    @field_validator("change_id")
    @classmethod
    def normalize_execution_change_id(cls, value: str) -> str:
        return value.strip().upper()


class SnowflakeUserExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_identity: str = Field(min_length=1, max_length=254)
    window_days: Literal[1, 7, 10, 15, 30] = 10
    evaluation_timestamp: AwareDatetime | None = None
    scenario_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    execution_mode: ExecutionMode = "deterministic"

    @field_validator("user_identity")
    @classmethod
    def normalize_user_identity(cls, value: str) -> str:
        return value.strip()


class SnowflakeExecutionFinding(BaseModel):
    category: str
    severity: str
    confidence: Literal["confirmed", "possible", "insufficient"]
    message: str
    query_ids: list[str] = Field(default_factory=list)
    change_id: str | None = None


class SnowflakeExecutionResponse(BaseModel):
    schema_version: int
    investigation_id: str
    provider: Literal["snowflake"]
    mode: Literal["change", "user"]
    change_id: str | None = None
    user: dict[str, Any] | None = None
    evaluation_timestamp: datetime
    period_start: datetime | None = None
    period_end: datetime
    overall_status: str
    findings: list[SnowflakeExecutionFinding]
    query_ids: list[str]
    confidence: str
    timeline: list[dict[str, Any]]
    expected_operations: list[dict[str, Any]] = Field(default_factory=list)
    observed_operations: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    ai_analysis: AiAnalysis | None = None
