from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from hashlib import sha256
from typing import Any

from backend.repositories.aws import AwsRepository
from backend.repositories.azure import AzureRepository
from backend.repositories.snowflake import SnowflakeRepository
from backend.services.aws_execution import AwsExecutionService
from backend.services.aws_validation import AwsValidationService
from backend.services.azure_execution import AzureExecutionService
from backend.services.azure_validation import AzureValidationService
from backend.services.snowflake import SnowflakeValidationService
from backend.services.snowflake_execution import SnowflakeExecutionService


PROVIDERS = ("aws", "azure", "snowflake")
COMPLIANT = {"VALID", "PASS", "COMPLIANT"}
REVIEW = {"NEEDS_INFO", "NEED_MORE_INFO", "INCOMPLETE", "AMBIGUOUS", "MANUAL_REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"}
UNAPPROVED = {"POSSIBLE_UNAPPROVED_ACTIVITY", "UNAPPROVED_OPERATION", "UNAPPROVED_CHANGE", "UNEXPECTED_ADDITIONAL_OPERATION"}
METRIC_DEFINITIONS = {
    "total_unique_changes": "Distinct provider and change ID pairs in the selected period.",
    "approved_changes": "Distinct selected changes whose recorded state is approved.",
    "noncompliant_changes": "Distinct change assessments with a deterministic adverse outcome; review/unknown outcomes are excluded.",
    "changes_requiring_review": "Distinct change assessments with incomplete, unknown, ambiguous, or evidence-limited outcomes.",
    "compliance_rate": "Compliant change assessments divided by compliant plus noncompliant assessments; review/unknown outcomes are excluded from the denominator.",
    "unique_high_risk_findings": "Distinct provider-aware finding IDs with Critical or High severity.",
    "access_risk_findings": "Distinct adverse findings produced by native access or role assessments.",
    "execution_deviations": "Distinct non-compliant execution findings; informational compliant findings are excluded.",
    "potentially_unapproved_activities": "Distinct execution findings classified as possible or confirmed unapproved activity.",
    "evidence_coverage": "Approved changes linked to at least one observed execution evidence ID divided by approved changes.",
}


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _utc(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _severity(value: Any, category: str) -> str:
    text = str(value or "").upper()
    if text == "CRITICAL": return "critical"
    if text in {"HIGH", "ERROR"}: return "high"
    if text in {"MEDIUM", "WARNING", "WARN", "REVIEW"}: return "medium"
    if text in {"LOW", "INFO", "INFORMATIONAL"}: return "low"
    return "medium" if category != "COMPLIANT_EXECUTION" else "low"


def _finding_id(provider: str, domain: str, category: str, change_id: str | None, evidence_ids: list[str], locator: str) -> str:
    identity = "|".join([provider, domain, category, change_id or "", *sorted(set(evidence_ids)), locator])
    return f"AN-{provider.upper()}-{sha256(identity.encode()).hexdigest()[:12].upper()}"


def _route(provider: str, domain: str, change_id: str | None) -> str | None:
    if domain == "execution": return "/execution-assurance"
    if domain in {"change", "access"} and change_id: return "/change-assurance"
    return "/risk-investigations"


class AnalyticsService:
    """Reproducible, read-only aggregation over native V2 synthetic evidence."""

    def __init__(self) -> None:
        self.repositories = {"aws": AwsRepository(), "azure": AzureRepository(), "snowflake": SnowflakeRepository()}
        self.validators = {"aws": AwsValidationService(), "azure": AzureValidationService(), "snowflake": SnowflakeValidationService()}
        self.executors = {"aws": AwsExecutionService(), "azure": AzureExecutionService(), "snowflake": SnowflakeExecutionService()}

    @staticmethod
    def _change_time(change: dict[str, Any]) -> datetime | None:
        return _dt(change.get("start") or change.get("planned_start") or change.get("start_time"))

    def _reference_time(self) -> datetime:
        values: list[datetime] = []
        for provider, repository in self.repositories.items():
            values += [value for change in repository.changes() if (value := self._change_time(change))]
            if provider == "aws": raw = repository.execution_events(); keys = ("eventTime",)
            elif provider == "azure": raw = repository.activity_logs(); keys = ("event_timestamp",)
            else: raw = repository.query_history(); keys = ("start_time",)
            values += [value for item in raw for key in keys if (value := _dt(item.get(key)))]
        return max(values)

    def _validate_change(self, provider: str, change: dict[str, Any], reference: datetime) -> dict[str, Any]:
        change_id = str(change["change_id"])
        if provider == "snowflake": return self.validators[provider].validate(change_id, reference)
        return self.validators[provider].validate_change(change_id)

    def _validate_access(self, provider: str, change_id: str) -> dict[str, Any] | None:
        if provider == "snowflake": return None
        return self.validators[provider].validate_access(change_id)

    def _normalize_findings(self, provider: str, domain: str, result: dict[str, Any], timestamp: datetime | None) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        change_id = result.get("change_id")
        source_findings = list(result.get("findings") or [])
        if domain == "access" and provider == "azure":
            for assessment in result.get("pim_assessments") or []:
                source_findings.extend(assessment.get("findings") or [])
        for finding in source_findings:
            category = str(finding.get("category") or "UNCLASSIFIED")
            if category == "COMPLIANT_EXECUTION": continue
            evidence_ids = [str(x) for x in (finding.get("evidence_ids") or finding.get("event_ids") or finding.get("query_ids") or []) if x]
            locator = str(finding.get("field") or finding.get("message") or finding.get("explanation") or finding.get("summary") or "")
            fid = _finding_id(provider, domain, category, change_id, evidence_ids, locator)
            normalized.append({
                "finding_id": fid, "provider": provider, "domain": domain, "category": category,
                "severity": _severity(finding.get("severity"), category),
                "summary": str(finding.get("explanation") or finding.get("message") or finding.get("summary") or category.replace("_", " ").title()),
                "timestamp": _utc(timestamp), "change_id": change_id, "evidence_ids": sorted(set(evidence_ids)),
                "resource": finding.get("resource"), "route": _route(provider, domain, change_id),
            })
        return normalized

    def _execution_results(self, provider: str) -> list[dict[str, Any]]:
        executor = self.executors[provider]
        results = []
        for scenario in executor.scenarios():
            mode = scenario.get("mode") or scenario.get("investigation_mode")
            evaluated = _dt(scenario.get("evaluation_timestamp"))
            if mode == "change":
                results.append(executor.assess_change(str(scenario["change_id"]), evaluated, str(scenario["scenario_id"])))
            else:
                identity = scenario.get("user_identity")
                if identity:
                    results.append(executor.assess_user(str(identity), int(scenario.get("window_days") or 10), evaluated, str(scenario["scenario_id"])))
        return results

    @lru_cache(maxsize=1)
    def _base(self) -> dict[str, Any]:
        reference = self._reference_time()
        changes: list[dict[str, Any]] = []
        findings: dict[str, dict[str, Any]] = {}
        executions: list[dict[str, Any]] = []
        covered_changes: set[tuple[str, str]] = set()
        for provider in PROVIDERS:
            for change in self.repositories[provider].changes():
                timestamp = self._change_time(change)
                result = self._validate_change(provider, change, reference)
                status = str(result.get("overall_status") or "UNKNOWN").upper()
                changes.append({"provider": provider, "change_id": str(change["change_id"]), "timestamp": timestamp, "approved": str(change.get("state") or change.get("approval_status") or "").casefold() == "approved", "status": status})
                for item in self._normalize_findings(provider, "change", result, timestamp): findings[item["finding_id"]] = item
                access = self._validate_access(provider, str(change["change_id"]))
                if access:
                    for item in self._normalize_findings(provider, "access", access, timestamp): findings[item["finding_id"]] = item
            for result in self._execution_results(provider):
                event_times = {str(x.get("event_id") or x.get("eventID") or x.get("event_data_id") or x.get("query_id") or ""): _dt(x.get("timestamp") or x.get("eventTime") or x.get("event_timestamp") or x.get("start_time")) for x in result.get("timeline") or []}
                result_time = max((x for x in event_times.values() if x), default=_dt(result.get("evaluation_timestamp")))
                executions.append({"provider": provider, "status": str(result.get("overall_status") or "UNKNOWN").upper(), "timestamp": result_time, "change_id": result.get("change_id"), "evidence_ids": set(x for x in event_times if x)})
                if result.get("change_id") and any(event_times): covered_changes.add((provider, str(result["change_id"])))
                for raw in result.get("findings") or []:
                    evidence_ids = [str(x) for x in (raw.get("event_ids") or raw.get("query_ids") or []) if x]
                    timestamp = max((event_times.get(x) for x in evidence_ids if event_times.get(x)), default=result_time)
                    wrapper = {"change_id": result.get("change_id"), "findings": [raw]}
                    for item in self._normalize_findings(provider, "execution", wrapper, timestamp): findings[item["finding_id"]] = item
        return {"reference": reference, "changes": changes, "findings": list(findings.values()), "executions": executions, "covered_changes": covered_changes}

    def _filtered(self, provider: str, days: int | None, severity: str) -> dict[str, Any]:
        if provider not in {"all", *PROVIDERS}: raise ValueError("Unsupported provider filter")
        if days not in {None, 7, 15, 30}: raise ValueError("Unsupported time period")
        if severity not in {"all", "critical", "high", "medium", "low"}: raise ValueError("Unsupported severity filter")
        base = self._base(); cutoff = base["reference"] - timedelta(days=days) if days else None
        in_scope = lambda item: (provider == "all" or item["provider"] == provider) and (cutoff is None or item.get("timestamp") is not None and item["timestamp"] >= cutoff)
        changes = [x for x in base["changes"] if in_scope(x)]
        findings = [x for x in base["findings"] if in_scope({**x, "timestamp": _dt(x.get("timestamp"))}) and (severity == "all" or x["severity"] == severity)]
        executions = [x for x in base["executions"] if in_scope(x)]
        return {**base, "changes": changes, "findings": findings, "executions": executions, "provider": provider, "days": days, "severity": severity}

    def _metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"synthetic": True, "dataset_label": "Synthetic Demo Dataset", "reference_timestamp": _utc(data["reference"]), "provider": data["provider"], "days": data["days"], "severity": data["severity"], "metric_definitions": METRIC_DEFINITIONS, "limitations": ["Metrics are reproducible snapshots of synthetic fixtures, not live cloud telemetry.", "Review, unknown, and insufficient-evidence outcomes are never counted as compliant.", "Scenario results are deduplicated by provider-aware finding and evidence identities."]}

    @staticmethod
    def _distribution(values: list[str], order: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        counts = Counter(values); names = order or tuple(sorted(counts))
        return [{"name": name, "value": counts.get(name, 0)} for name in names]

    def _trend(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        finding_counts = Counter(x["timestamp"][:10] for x in data["findings"] if x.get("timestamp"))
        assessment_counts = Counter(_utc(x["timestamp"])[:10] for x in data["changes"] if x.get("timestamp"))
        return [{"date": day, "findings": finding_counts[day], "assessments": assessment_counts[day]} for day in sorted(set(finding_counts) | set(assessment_counts))]

    def _change_summary(self, changes: list[dict[str, Any]]) -> dict[str, int]:
        compliant = sum(x["status"] in COMPLIANT for x in changes); review = sum(x["status"] in REVIEW or x["status"] == "UNKNOWN" for x in changes)
        return {"compliant": compliant, "noncompliant": len(changes) - compliant - review, "review_or_unknown": review, "denominator": len(changes) - review}

    def _execution_summary(self, executions: list[dict[str, Any]]) -> dict[str, int]:
        compliant = sum(x["status"] in COMPLIANT for x in executions); review = sum(x["status"] in REVIEW or x["status"] == "UNKNOWN" for x in executions)
        return {"compliant": compliant, "noncompliant": len(executions) - compliant - review, "review_or_unknown": review, "denominator": len(executions) - review}

    def overview(self, provider: str = "all", days: int | None = None, severity: str = "all") -> dict[str, Any]:
        data = self._filtered(provider, days, severity); change_summary = self._change_summary(data["changes"]); execution_summary = self._execution_summary(data["executions"])
        high = [x for x in data["findings"] if x["severity"] in {"critical", "high"}]
        recent = sorted(high or data["findings"], key=lambda x: x.get("timestamp") or "", reverse=True)[:8]
        return {"metadata": self._metadata(data), "total_unique_changes": len({(x["provider"], x["change_id"]) for x in data["changes"]}), "approved_changes": sum(x["approved"] for x in data["changes"]), "noncompliant_changes": change_summary["noncompliant"], "changes_requiring_review": change_summary["review_or_unknown"], "compliance_rate": round(change_summary["compliant"] * 100 / change_summary["denominator"], 1) if change_summary["denominator"] else None, "compliance_denominator": change_summary["denominator"], "high_risk_findings": len(high), "execution_deviations": sum(x["domain"] == "execution" for x in data["findings"]), "potentially_unapproved_activities": sum(x["category"] in UNAPPROVED for x in data["findings"]), "provider_risk_counts": self._distribution([x["provider"] for x in data["findings"]], PROVIDERS), "findings_by_severity": self._distribution([x["severity"] for x in data["findings"]], ("critical", "high", "medium", "low")), "findings_over_time": self._trend(data), "change_assurance": change_summary, "execution_assurance": execution_summary, "recent_significant_findings": recent}

    def risks(self, provider: str = "all", days: int | None = None, severity: str = "all") -> dict[str, Any]:
        data = self._filtered(provider, days, severity)
        return {"metadata": self._metadata(data), "total_findings": len(data["findings"]), "unique_high_risk_findings": sum(x["severity"] in {"critical", "high"} for x in data["findings"]), "findings_by_severity": self._distribution([x["severity"] for x in data["findings"]], ("critical", "high", "medium", "low")), "findings_by_provider": self._distribution([x["provider"] for x in data["findings"]], PROVIDERS), "findings_by_category": self._distribution([x["category"] for x in data["findings"]]), "findings_over_time": self._trend(data), "findings": data["findings"]}

    def execution(self, provider: str = "all", days: int | None = None, severity: str = "all") -> dict[str, Any]:
        data = self._filtered(provider, days, severity); findings = [x for x in data["findings"] if x["domain"] == "execution"]; summary = self._execution_summary(data["executions"])
        approved = {(x["provider"], x["change_id"]) for x in data["changes"] if x["approved"]}; covered = approved & data["covered_changes"]
        return {"metadata": self._metadata(data), "summary": summary, "deviations": len(findings), "potentially_unapproved_activities": sum(x["category"] in UNAPPROVED for x in findings), "categories": self._distribution([x["category"] for x in findings]), "evidence_coverage": {"covered": len(covered), "eligible": len(approved), "percentage": round(len(covered) * 100 / len(approved), 1) if approved else None, "unavailable_reason": None if approved else "No approved changes are present in the selected scope."}}

    def access(self, provider: str = "all", days: int | None = None, severity: str = "all") -> dict[str, Any]:
        data = self._filtered(provider, days, severity); findings = [x for x in data["findings"] if x["domain"] == "access" or (x["domain"] == "change" and x["provider"] == "snowflake" and "ROLE" in x["category"])]
        return {"metadata": self._metadata(data), "access_risk_findings": len(findings), "categories": self._distribution([x["category"] for x in findings]), "provider_counts": self._distribution([x["provider"] for x in findings], PROVIDERS), "unavailable_metrics": {"effective_permissions": "Synthetic policy and grant evidence is not a complete live effective-permissions calculation."}}
