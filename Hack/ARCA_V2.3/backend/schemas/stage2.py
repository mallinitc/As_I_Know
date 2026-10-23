"""V1-compatible independent Stage 2 access-governance contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from backend.schemas.common import AiAnalysis, ExecutionMode


class Stage2Scenario(BaseModel):
    scenario_id: str
    name: str
    mode: Literal["change", "user", "paste"]
    change_id: str
    pim_request_ids: list[str]
    user_identity: str
    expected_outcome: str
    explanation: str
    access_state: str = "All"


class Stage2ScenariosResponse(BaseModel):
    provider: Literal["azure"] = "azure"
    synthetic: Literal[True] = True
    count: int
    items: list[Stage2Scenario]


class Stage2AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["change", "user", "paste"]
    change_id: str = Field(default="", max_length=100)
    user_identity: str = Field(default="", max_length=320)
    access_state: Literal["Active", "Pending", "Scheduled", "All"] = "All"
    records_text: str = Field(default="", max_length=100_000)
    evaluation_timestamp: AwareDatetime | None = None
    execution_mode: ExecutionMode = "deterministic"

    @field_validator("change_id")
    @classmethod
    def normalize_change_id(cls, value: str) -> str:
        return value.strip().upper()


class Stage2AssessmentResponse(BaseModel):
    provider: Literal["azure"] = "azure"
    mode: Literal["change", "user", "paste"]
    evaluation_timestamp: datetime
    overall_assessment: str
    risk_classification: str
    records: list[dict[str, Any]]
    assessments: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    missing_information: list[str]
    recommendations: list[str]
    evidence: list[dict[str, Any]]
    ai_analysis: AiAnalysis | None = None
    disclaimer: str = "ARCA recommendation only; no PIM approval, rejection, or activation was performed."
