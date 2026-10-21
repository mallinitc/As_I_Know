"""Typed, provider-neutral models for pre-submission change validation."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class ExpectedOperation(BaseModel):
    operation: str
    resource_id: str = ""


class ExtractedChange(BaseModel):
    change_id: str | None = None
    provider: Literal["azure", "aws", "snowflake"]
    source_mode: Literal["existing", "pasted"]
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
    """Editable ServiceNow-shaped draft populated only from extracted evidence."""
    provider: Literal["azure", "aws", "snowflake"]
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
