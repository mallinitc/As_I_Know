from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    noncompliant_changes: int
    changes_requiring_review: int
    compliance_rate: float | None
    compliance_denominator: int
    high_risk_findings: int
    execution_deviations: int
    potentially_unapproved_activities: int
    provider_risk_counts: list[DistributionItem]
    findings_by_severity: list[DistributionItem]
    findings_over_time: list[TrendItem]
    change_assurance: AssuranceSummary
    execution_assurance: AssuranceSummary
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

