from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from backend.schemas.common import AiAnalysis, ExecutionMode


class AzureValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    pim_request_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    execution_mode: ExecutionMode = "deterministic"

    @field_validator("change_id")
    @classmethod
    def normalize_change_id(cls, value: str) -> str:
        return value.strip().upper()


class AzureFinding(BaseModel):
    category: str
    field: str
    severity: str
    message: str
    actual: Any = None
    expected: Any = None
    recommendation: str
    evidence_ids: list[str] = Field(default_factory=list)


class AzureChangeRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    change_id: str
    provider: Literal["azure"] = "azure"
    environment: str = ""
    description: str = ""
    state: str = ""
    implementer: dict[str, Any] | None = None
    start: str | None = None
    end: str | None = None
    expected: list[dict[str, Any]] = Field(default_factory=list)


class AzureChangesResponse(BaseModel):
    provider: Literal["azure"] = "azure"
    evidence_source: str
    synthetic: Literal[True] = True
    count: int
    items: list[AzureChangeRecord]


class AzureDemoScenario(BaseModel):
    scenario_id: str
    scenario_name: str
    stage: Literal["change", "access"]
    change_id: str
    description: str
    source_scenario: str


class AzureDemoScenariosResponse(BaseModel):
    provider: Literal["azure"] = "azure"
    synthetic: Literal[True] = True
    count: int
    items: list[AzureDemoScenario]


class AzureChangeValidationResponse(BaseModel):
    schema_version: int
    provider: Literal["azure"]
    stage: Literal["change"]
    change_id: str
    overall_status: str
    findings: list[AzureFinding]
    missing_information: list[str]
    evidence: list[dict[str, Any]]
    recommendations: list[str]
    change: dict[str, Any]
    ai_analysis: AiAnalysis | None = None


class AzurePimAssessment(BaseModel):
    pim_request_id: str
    overall_status: str
    supported_operations: list[dict[str, Any]]
    findings: list[AzureFinding]
    evidence_ids: list[str]


class AzureAccessValidationResponse(BaseModel):
    schema_version: int
    provider: Literal["azure"]
    stage: Literal["access"]
    change_id: str
    overall_status: str
    pim_assessments: list[AzurePimAssessment]
    covered_operations: list[dict[str, Any]]
    missing_operations: list[dict[str, Any]]
    findings: list[AzureFinding]
    missing_information: list[str]
    recommendations: list[str]
    evidence: list[dict[str, Any]]
    change: dict[str, Any]
    ai_analysis: AiAnalysis | None = None


class AzureExecutionScenario(BaseModel):
    scenario_id: str
    scenario_name: str
    mode: Literal["change", "user"]
    change_id: str | None = None
    user_identity: str | None = None
    evaluation_timestamp: AwareDatetime
    window_days: int
    event_data_ids: list[str]
    expected_findings: list[str]
    source: Literal["v1", "v2"] = "v2"
    description: str | None = None
    expected_outcome: str | None = None


class AzureExecutionScenariosResponse(BaseModel):
    provider: Literal["azure"] = "azure"
    synthetic: Literal[True] = True
    count: int
    items: list[AzureExecutionScenario]


class AzureChangeExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    evaluation_timestamp: AwareDatetime | None = None
    scenario_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    execution_mode: ExecutionMode = "deterministic"

    @field_validator("change_id")
    @classmethod
    def normalize_execution_change_id(cls, value: str) -> str:
        return value.strip().upper()


class AzureUserExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_identity: str = Field(min_length=1, max_length=254)
    window_days: Literal[1, 7, 10, 15, 30] = 10
    evaluation_timestamp: AwareDatetime | None = None
    scenario_id: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    execution_mode: ExecutionMode = "deterministic"

    @field_validator("user_identity")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return value.strip()


class AzureExecutionFinding(BaseModel):
    category: str
    severity: str
    confidence: Literal["confirmed", "possible", "insufficient"]
    message: str
    event_ids: list[str] = Field(default_factory=list)
    change_id: str | None = None
    recommendation: str


class AzureExecutionResponse(BaseModel):
    schema_version: int
    investigation_id: str
    provider: Literal["azure"]
    mode: Literal["change", "user"]
    change_id: str | None = None
    user: dict[str, Any] | None = None
    evaluation_timestamp: AwareDatetime
    period_start: AwareDatetime | None = None
    period_end: AwareDatetime
    overall_status: str
    findings: list[AzureExecutionFinding]
    event_ids: list[str]
    confidence: str
    timeline: list[dict[str, Any]]
    expected_operations: list[dict[str, Any]] = Field(default_factory=list)
    observed_operations: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    v1_assessment: dict[str, Any] | None = None
    ai_analysis: AiAnalysis | None = None
