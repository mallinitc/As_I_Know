from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ProviderFilter = Literal["all", "aws", "azure", "snowflake"]
SeverityFilter = Literal["all", "critical", "high", "medium", "low"]


class AnalyticsMetadata(BaseModel):
    synthetic: Literal[True] = True
    dataset_label: str = "Synthetic Demo Dataset"
    reference_timestamp: str
    provider: ProviderFilter
    days: int | None
    severity: SeverityFilter
    metric_definitions: dict[str, str]
    limitations: list[str] = Field(default_factory=list)


class AnalyticsFinding(BaseModel):
    finding_id: str
    provider: Literal["aws", "azure", "snowflake"]
    domain: Literal["change", "access", "execution"]
    category: str
    severity: Literal["critical", "high", "medium", "low"]
    summary: str
    timestamp: str | None = None
    change_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    resource: str | None = None
    route: str | None = None


class DistributionItem(BaseModel):
    name: str
    value: int


class TrendItem(BaseModel):
    date: str
    findings: int
    assessments: int


class AssuranceSummary(BaseModel):
    compliant: int
    noncompliant: int
    review_or_unknown: int
    denominator: int


class EvidenceCoverage(BaseModel):
    covered: int
    eligible: int
    percentage: float | None
    unavailable_reason: str | None = None


class AnalyticsOverviewResponse(BaseModel):
    metadata: AnalyticsMetadata
    total_unique_changes: int
    approved_changes: int
    successfully_verified_changes: int
    noncompliant_changes: int
    changes_requiring_review: int
    compliance_rate: float | None
    compliance_denominator: int
    high_risk_findings: int
    execution_deviations: int
    potentially_unapproved_activities: int
    potentially_undocumented_changes: int
    access_risk_findings: int
    provider_risk_counts: list[DistributionItem]
    findings_by_severity: list[DistributionItem]
    findings_over_time: list[TrendItem]
    change_assurance: AssuranceSummary
    execution_assurance: AssuranceSummary
    execution_risk_categories: list[DistributionItem]
    access_risk_categories: list[DistributionItem]
    undocumented_activity: list[dict[str, Any]]
    recent_significant_findings: list[AnalyticsFinding]


class AnalyticsRisksResponse(BaseModel):
    metadata: AnalyticsMetadata
    total_findings: int
    unique_high_risk_findings: int
    findings_by_severity: list[DistributionItem]
    findings_by_provider: list[DistributionItem]
    findings_by_category: list[DistributionItem]
    findings_over_time: list[TrendItem]
    findings: list[AnalyticsFinding]


class AnalyticsExecutionResponse(BaseModel):
    metadata: AnalyticsMetadata
    summary: AssuranceSummary
    deviations: int
    potentially_unapproved_activities: int
    categories: list[DistributionItem]
    evidence_coverage: EvidenceCoverage


class AnalyticsAccessResponse(BaseModel):
    metadata: AnalyticsMetadata
    access_risk_findings: int
    categories: list[DistributionItem]
    provider_counts: list[DistributionItem]
    unavailable_metrics: dict[str, str] = Field(default_factory=dict)


class FeedbackCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_id: str = Field(min_length=8, max_length=100)
    assessment_id: str = Field(min_length=3, max_length=240)
    stage: Literal["A1", "A2", "A3", "A4", "A5"]
    provider: Literal["azure", "aws", "snowflake", "all"]
    result_reference: str | None = Field(default=None, max_length=500)
    finding_reference: str | None = Field(default=None, max_length=500)
    original_decision: str = Field(min_length=1, max_length=200)
    feedback_decision: Literal["Correct", "Incorrect", "Needs Review"]
    feedback_reason: str = Field(default="", max_length=2000)
    user_identity: str | None = Field(default=None, max_length=320)


class FeedbackRecord(BaseModel):
    telemetry_schema_version: int = 1
    feedback_id: str
    timestamp_utc: str
    submission_id: str
    assessment_id: str
    stage: str
    provider: str
    result_reference: str | None = None
    finding_reference: str | None = None
    original_arca_decision: str
    feedback_decision: str
    feedback_reason: str
    user_identity: str | None = None
    user_role: str | None = None


class FeedbackLatestResponse(BaseModel):
    item: FeedbackRecord | None = None


class ObservabilityResponse(BaseModel):
    metadata: dict[str, Any]
    summary: dict[str, Any]
    performance: dict[str, Any]
    llm_by_agent: list[dict[str, Any]]
    llm_by_provider: list[dict[str, Any]]
    llm_by_model: list[dict[str, Any]]
    cost_by_agent: list[dict[str, Any]]
    cost_by_provider: list[dict[str, Any]]
    cost_by_model: list[dict[str, Any]]
    feedback_by_stage: list[dict[str, Any]]
    feedback_by_provider: list[dict[str, Any]]
    feedback_by_decision: list[dict[str, Any]]
    frequently_disputed: list[dict[str, Any]]
    trends: list[dict[str, Any]]
    recent_executions: list[dict[str, Any]]
    recent_feedback: list[dict[str, Any]]
    limitations: list[str]


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["deterministic_and_mocked_llm"] = "deterministic_and_mocked_llm"


class EvaluationRunResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    timestamp: str
    evaluation_mode: str
    live_llm_calls: int = 0


class EvaluationHistoryResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
