from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from backend.schemas.common import AiAnalysis, ExecutionMode


class AwsValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    execution_mode: ExecutionMode = "deterministic"

    @field_validator("change_id")
    @classmethod
    def normalize_change_id(cls, value: str) -> str:
        return value.strip().upper()


class AwsFinding(BaseModel):
    category: str
    field: str
    severity: str
    explanation: str
    actual: Any = None
    expected: Any = None
    recommendation: str
    evidence_ids: list[str] = Field(default_factory=list)


class AwsChangeRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    change_id: str
    environment: str = ""
    actor: str = ""
    state: str | None = None
    start: str | None = None
    end: str | None = None
    description: str = ""
    expected: list[dict[str, Any]] = Field(default_factory=list)


class AwsChangesResponse(BaseModel):
    provider: Literal["aws"] = "aws"
    evidence_source: str
    synthetic: bool = True
    count: int
    items: list[AwsChangeRecord]


class AwsDemoScenario(BaseModel):
    scenario_id: str
    scenario_name: str
    stage: Literal["change", "access"]
    change_id: str
    expected_status: str | None = None
    expected_findings: list[str] = Field(default_factory=list)


class AwsDemoScenariosResponse(BaseModel):
    provider: Literal["aws"] = "aws"
    synthetic: bool = True
    count: int
    items: list[AwsDemoScenario]


class AwsChangeValidationResponse(BaseModel):
    schema_version: int
    provider: Literal["aws"]
    stage: Literal["change"]
    change_id: str
    overall_status: str
    findings: list[AwsFinding]
    missing_information: list[str]
    recommendations: list[str]
    evidence: list[dict[str, Any]]
    change: dict[str, Any]
    ai_analysis: AiAnalysis | None = None


class AwsPermissionEvaluation(BaseModel):
    event_name: str
    iam_action: str | None = None
    resource: str | None = None
    decision: str
    allow_evidence: list[str] = Field(default_factory=list)
    deny_evidence: list[str] = Field(default_factory=list)


class AwsAccessValidationResponse(BaseModel):
    schema_version: int
    provider: Literal["aws"]
    stage: Literal["access"]
    change_id: str
    overall_status: str
    permission_evaluations: list[AwsPermissionEvaluation]
    findings: list[AwsFinding]
    missing_information: list[str]
    recommendations: list[str]
    evidence: list[dict[str, Any]]
    limitations: list[str]
    change: dict[str, Any]
    access_request: dict[str, Any] | None = None
    ai_analysis: AiAnalysis | None = None

class AwsExecutionScenario(BaseModel):
    scenario_id: str
    scenario_name: str
    mode: Literal["change", "user"]
    change_id: str | None = None
    user_identity: str | None = None
    evaluation_timestamp: AwareDatetime
    window_days: int
    event_ids: list[str]
    expected_findings: list[str]

class AwsExecutionScenariosResponse(BaseModel):
    provider: Literal["aws"] = "aws"
    synthetic: bool = True
    count: int
    items: list[AwsExecutionScenario]

class AwsChangeExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    evaluation_timestamp: AwareDatetime | None = None
    scenario_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    execution_mode: ExecutionMode = "deterministic"

class AwsUserExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_identity: str = Field(min_length=1, max_length=254)
    window_days: Literal[1, 7, 10, 15, 30] = 10
    evaluation_timestamp: AwareDatetime | None = None
    scenario_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    execution_mode: ExecutionMode = "deterministic"

class AwsExecutionFinding(BaseModel):
    category: str
    severity: str
    confidence: Literal["confirmed", "possible", "insufficient"]
    message: str
    event_ids: list[str] = Field(default_factory=list)
    change_id: str | None = None
    recommendation: str

class AwsExecutionResponse(BaseModel):
    schema_version: int
    investigation_id: str
    provider: Literal["aws"]
    mode: Literal["change", "user"]
    change_id: str | None = None
    user: dict[str, Any] | None = None
    evaluation_timestamp: AwareDatetime
    period_start: AwareDatetime | None = None
    period_end: AwareDatetime
    overall_status: str
    findings: list[AwsExecutionFinding]
    event_ids: list[str]
    confidence: str
    timeline: list[dict[str, Any]]
    expected_operations: list[dict[str, Any]] = Field(default_factory=list)
    observed_operations: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    ai_analysis: AiAnalysis | None = None
