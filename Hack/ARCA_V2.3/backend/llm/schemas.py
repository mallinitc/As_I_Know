from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ProviderName = Literal["aws", "azure", "snowflake", "all"]
IntentName = Literal[
    "change_investigation",
    "change_execution",
    "user_investigation",
    "role_investigation",
    "cross_environment_summary",
    "unauthorized_activity",
    "historical_activity",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LlmIntent(StrictModel):
    investigation_type: IntentName
    provider: ProviderName | None = None
    change_id: str | None = Field(default=None, max_length=80)
    user_identifier: str | None = Field(default=None, max_length=320)
    role: str | None = Field(default=None, max_length=200)
    resource: str | None = Field(default=None, max_length=1000)
    time_period_days: Literal[1, 7, 10, 15, 30] = 10
    severity: Literal["all", "critical", "high", "medium", "low"] = "all"
    clarification: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_identifiers(self) -> "LlmIntent":
        if self.investigation_type.startswith("change") and not self.change_id and not self.clarification:
            raise ValueError("change investigations require a change ID or clarification")
        if self.investigation_type == "user_investigation" and not self.user_identifier and not self.clarification:
            raise ValueError("user investigations require an identity or clarification")
        if not self.provider and not self.clarification:
            raise ValueError("an environment or clarification is required")
        return self


class ToolParameters(StrictModel):
    provider: ProviderName | None = None
    change_id: str | None = Field(default=None, max_length=80)
    user_identifier: str | None = Field(default=None, max_length=320)
    role: str | None = Field(default=None, max_length=200)
    resource: str | None = Field(default=None, max_length=1000)
    time_period_days: Literal[1, 7, 10, 15, 30] | None = None
    severity: Literal["all", "critical", "high", "medium", "low"] | None = None


class PlannedToolCall(StrictModel):
    tool_name: str = Field(min_length=1, max_length=100)
    parameters: ToolParameters = Field(default_factory=ToolParameters)
    purpose: str = Field(min_length=1, max_length=300)


class LlmPlan(StrictModel):
    intent: LlmIntent
    tool_calls: list[PlannedToolCall] = Field(default_factory=list, max_length=5)


class LlmSynthesis(StrictModel):
    summary: str = Field(min_length=1, max_length=3000)
    evidence_citations: list[str] = Field(default_factory=list, max_length=100)
    limitation: str | None = Field(default=None, max_length=1000)


class AgentAssistanceOutput(StrictModel):
    ai_summary: str = Field(min_length=1, max_length=3000)
    ai_observations: list[str] = Field(default_factory=list, max_length=30)
    ai_recommendations: list[str] = Field(default_factory=list, max_length=30)
    evidence_references: list[str] = Field(default_factory=list, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=30)


class DraftRefinementOutput(StrictModel):
    change_title: str = Field(default="", max_length=500)
    business_justification: str = Field(default="", max_length=3000)
    implementation_steps: list[str] = Field(default_factory=list, max_length=30)
    validation_plan: list[str] = Field(default_factory=list, max_length=30)
    rollback_plan: str = Field(default="", max_length=3000)
    expected_outcome: str = Field(default="", max_length=3000)
    risk_and_impact: str = Field(default="", max_length=3000)


class LlmCallMetrics(StrictModel):
    operation: str = Field(default="structured_output", max_length=100)
    attempt: int = Field(default=1, ge=1)
    status: str = Field(default="completed", max_length=100)
    provider: str = Field(default="", max_length=100)
    model_identifier: str = Field(default="", max_length=300)
    duration_ms: float = Field(default=0.0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class TokenUsage(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_output_tokens: int | None = Field(default=None, ge=0)
    calls: list[LlmCallMetrics] = Field(default_factory=list, max_length=10)

    def plus(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_input_tokens=(self.cached_input_tokens or 0) + (other.cached_input_tokens or 0),
            reasoning_output_tokens=(self.reasoning_output_tokens or 0) + (other.reasoning_output_tokens or 0),
            calls=[*self.calls, *other.calls],
        )


class StructuredLlmResult(StrictModel):
    value: dict[str, Any]
    model_identifier: str
    usage: TokenUsage
