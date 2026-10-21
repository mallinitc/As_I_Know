"""Deterministic Stage 1 pre-submission validation."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from .change_models import DraftValidationResult, ExtractedChange, ValidationIssue

POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "change_validation_policy.json"


def load_validation_policy(path: Path | None = None) -> dict:
    return json.loads((path or POLICY_PATH).read_text(encoding="utf-8"))


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone is required")
    return parsed


def validate_draft(change: ExtractedChange, policy: dict | None = None) -> DraftValidationResult:
    policy = policy or load_validation_policy()
    issues: list[ValidationIssue] = []
    missing = []
    values = change.model_dump()
    for field in policy["mandatory_fields"]:
        if not values.get(field):
            missing.append(field)
            issues.append(ValidationIssue(field=field, reason="Mandatory information is missing.", severity="ERROR", category="INCOMPLETE", recommended_correction=f"Provide an explicit {field.replace('_', ' ')}."))
    if change.start:
        try: start = _timestamp(change.start)
        except ValueError as exc:
            start = None
            issues.append(ValidationIssue(field="start", reason=f"Invalid start timestamp: {exc}.", severity="ERROR", category="INCONSISTENT", recommended_correction="Provide an ISO 8601 start timestamp with an explicit timezone."))
    else: start = None
    if change.end:
        try: end = _timestamp(change.end)
        except ValueError as exc:
            end = None
            issues.append(ValidationIssue(field="end", reason=f"Invalid end timestamp: {exc}.", severity="ERROR", category="INCONSISTENT", recommended_correction="Provide an ISO 8601 end timestamp with an explicit timezone."))
    else: end = None
    if start and end and start >= end:
        issues.append(ValidationIssue(field="change_window", reason="The end timestamp must be later than the start timestamp.", severity="ERROR", category="INCONSISTENT", recommended_correction="Correct the change window and retain explicit timezones."))
    for conflict in change.conflicts:
        issues.append(ValidationIssue(field="change_details", reason=conflict, severity="ERROR", category="INCONSISTENT", recommended_correction="Resolve the conflicting values and provide one authoritative value."))
    for field in ("implementation_tasks", "purpose", "target_resources"):
        text = " ".join(values.get(field, [])) if isinstance(values.get(field), list) else str(values.get(field, ""))
        if text and any(phrase in text.lower() for phrase in policy.get("ambiguous_phrases", [])):
            issues.append(ValidationIssue(field=field, reason="The supplied information contains non-specific instructions.", severity="REVIEW", category="AMBIGUOUS", recommended_correction="Replace vague wording with explicit resources, operations, and accountable steps."))
    for ambiguity in change.ambiguities:
        issues.append(ValidationIssue(field="change_details", reason=ambiguity, severity="REVIEW", category="AMBIGUOUS", recommended_correction="Clarify the statement before submission."))
    categories = {issue.category for issue in issues}
    status = "INCONSISTENT" if "INCONSISTENT" in categories else "AMBIGUOUS" if "AMBIGUOUS" in categories else "INCOMPLETE" if missing else "MANUAL_REVIEW_REQUIRED" if "MANUAL_REVIEW_REQUIRED" in categories else "VALID"
    supplied = sum(bool(values.get(field)) for field in policy["mandatory_fields"])
    questions = [f"What is the {field.replace('_', ' ')}?" for field in missing]
    questions += [f"Please clarify: {issue.reason}" for issue in issues if issue.category in {"AMBIGUOUS", "INCONSISTENT"}]
    return DraftValidationResult(status=status, ready_for_submission=status == "VALID",
        completeness={"mandatory_supplied": supplied, "mandatory_total": len(policy["mandatory_fields"]), "recommended_supplied": sum(bool(values.get(field)) for field in policy["recommended_fields"]), "recommended_total": len(policy["recommended_fields"])},
        extracted_change=change, issues=issues, missing_mandatory=missing, clarification_questions=questions,
        expected_operations=change.expected_operations)
