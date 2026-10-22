"""V1-compatible contracts for independent Stage 1 draft validation."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.common import AiExecutionMetrics, ExecutionMode


Provider = Literal["azure", "aws"]


class ExpectedOperation(BaseModel):
    operation: str
    resource_id: str = ""


class ExtractedChange(BaseModel):
    change_id: str | None = None
    provider: Provider
    source_mode: Literal["existing", "pasted"] = "pasted"
    extraction_mode: Literal["mock", "openai", "bedrock"] = "mock"
    purpose: str = ""
    title: str = ""
    business_justification: str = ""
    environment: str = ""
    subscription: str = ""
    resource_group: str = ""
    resource_name: str = ""
    timezone: str = ""
    target_resources: list[str] = Field(default_factory=list)
    implementer: str = ""
    implementation_tasks: list[str] = Field(default_factory=list)
    start: str = ""
    end: str = ""
    expected_outcome: str = ""
    validation_steps: list[str] = Field(default_factory=list)
    rollback_plan: str = ""
    risk_impact: str = ""
    role_requirements: list[str] = Field(default_factory=list)
    scope_requirements: list[str] = Field(default_factory=list)
    expected_operations: list[ExpectedOperation] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    raw_text: str = ""


class ValidationIssue(BaseModel):
    field: str
    reason: str
    severity: Literal["ERROR", "WARNING", "REVIEW"]
    category: Literal["INCOMPLETE", "AMBIGUOUS", "INCONSISTENT", "MANUAL_REVIEW_REQUIRED"]
    recommended_correction: str


class DraftValidationResult(BaseModel):
    status: Literal["VALID", "INCOMPLETE", "AMBIGUOUS", "INCONSISTENT", "MANUAL_REVIEW_REQUIRED"]
    ready_for_submission: bool
    completeness: dict[str, int]
    extracted_change: ExtractedChange
    issues: list[ValidationIssue]
    missing_mandatory: list[str]
    clarification_questions: list[str]
    expected_operations: list[ExpectedOperation]
    policy_version: str = "1.0"


class ImprovedChangeDraft(BaseModel):
    provider: Provider
    change_title: str = ""
    change_number: str = ""
    business_justification: str = ""
    environment: str = ""
    subscription: str = ""
    resource_group: str = ""
    resource_name_or_id: str = ""
    implementer: str = ""
    change_start: str = ""
    change_end: str = ""
    timezone: str = ""
    required_role: str = ""
    required_access_scope: str = ""
    implementation_steps: list[str] = Field(default_factory=list)
    validation_plan: list[str] = Field(default_factory=list)
    rollback_plan: str = ""
    expected_outcome: str = ""
    risk_and_impact: str = ""
    expected_operations: list[ExpectedOperation] = Field(default_factory=list)
    source_mode: Literal["existing", "pasted"] = "pasted"
    source_text: str = ""
    source_conflicts: list[str] = Field(default_factory=list)


class DraftValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Provider
    text: str = Field(min_length=1, max_length=50_000)
    overrides: dict[str, str] = Field(default_factory=dict)


class StructuredDraftValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: ImprovedChangeDraft


class DraftImproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extracted_change: ExtractedChange
    execution_mode: ExecutionMode = "deterministic"


class DraftImproveResponse(BaseModel):
    draft: ImprovedChangeDraft
    validation: DraftValidationResult
    copy_text: str
    llm_invoked: bool = False
    llm_status: str = "not_invoked"
    model_identifier: str | None = None
    execution_metrics: AiExecutionMetrics
    disclosure: str


class Stage1Scenario(BaseModel):
    scenario_id: str
    name: str
    provider: Provider
    expected_outcome: str
    explanation: str
    text: str


class Stage1ScenariosResponse(BaseModel):
    provider: Provider
    synthetic: Literal[True] = True
    count: int
    items: list[Stage1Scenario]
