from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.common import ExecutionMode


class ChangeDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["aws", "azure", "snowflake"]
    change_id: str = Field(min_length=2, max_length=100)
    execution_mode: ExecutionMode = "deterministic"


class ChangeDraft(BaseModel):
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


class ChangeDraftResponse(BaseModel):
    provider: Literal["aws", "azure", "snowflake"]
    change_id: str
    draft: ChangeDraft
    missing_fields: list[str]
    source_evidence_ids: list[str]
    llm_invoked: bool = False
    llm_status: str = "not_invoked"
    model_identifier: str | None = None
    token_usage: dict[str, int] | None = None
    disclosure: str
