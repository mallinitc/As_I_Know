from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import csv
import io
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Iterable
from uuid import uuid4

from backend.config import log_path


_LOCK = RLock()
_FILES = {"executions", "feedback"}


def _root() -> Path:
    path = log_path() / "observability"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(name: str) -> Path:
    if name not in _FILES:
        raise ValueError("Unsupported observability record type")
    return _root() / f"{name}.jsonl"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_text(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _append(name: str, record: dict[str, Any]) -> None:
    line = json.dumps({"telemetry_schema_version": 1, **record}, ensure_ascii=False, default=str, separators=(",", ":")) + "\n"
    with _LOCK, _path(name).open("a", encoding="utf-8", newline="") as handle:
        handle.write(line)
        handle.flush()


def read_records(name: str) -> tuple[list[dict[str, Any]], list[str]]:
    path = _path(name)
    if not path.exists():
        return [], []
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    with _LOCK, path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                value = json.loads(line)
                if isinstance(value, dict): rows.append(value)
                else: errors.append(f"{path.name}:{line_number}: not an object")
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                errors.append(f"{path.name}:{line_number}: {type(exc).__name__}")
    return rows, errors


def record_execution_metrics(metrics: dict[str, Any]) -> None:
    """Persist metadata-only execution telemetry without model prompts or evidence."""
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("ARCA_TELEMETRY_ENABLED", "true").casefold() not in {"1", "true", "yes", "on"}:
        return
    _append("executions", {"execution_id": f"exec_{uuid4().hex}", "timestamp_utc": utc_text(), **metrics})


def submit_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    rows, _ = read_records("feedback")
    submission_id = str(payload["submission_id"])
    existing = next((row for row in rows if row.get("submission_id") == submission_id), None)
    if existing:
        return existing
    record = {
        "feedback_id": f"feedback_{uuid4().hex}", "timestamp_utc": utc_text(),
        "submission_id": submission_id, "assessment_id": payload["assessment_id"],
        "stage": payload["stage"], "provider": payload["provider"],
        "result_reference": payload.get("result_reference"), "finding_reference": payload.get("finding_reference"),
        "original_arca_decision": payload["original_decision"], "feedback_decision": payload["feedback_decision"],
        "feedback_reason": str(payload.get("feedback_reason") or "")[:2000],
        "user_identity": payload.get("user_identity"),
        "user_role": payload.get("user_role"),
    }
    _append("feedback", record)
    return record


def latest_feedback(assessment_id: str) -> dict[str, Any] | None:
    rows, _ = read_records("feedback")
    matches = [row for row in rows if row.get("assessment_id") == assessment_id]
    return max(matches, key=lambda row: row.get("timestamp_utc", ""), default=None)


def _dt(value: Any) -> datetime | None:
    try: return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError): return None


def _percentile(values: Iterable[float], fraction: float) -> float | None:
    items = sorted(float(value) for value in values)
    if not items: return None
    position = (len(items) - 1) * fraction
    lower = int(position); upper = min(lower + 1, len(items) - 1)
    return round(items[lower] + (items[upper] - items[lower]) * (position - lower), 3)


def _distribution(rows: Iterable[dict[str, Any]], key: str, value: str | None = None) -> list[dict[str, Any]]:
    counts: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        counts[str(row.get(key) or "Unknown")] += float(row.get(value) or 0) if value else 1
    return [{"name": name, "value": amount} for name, amount in sorted(counts.items())]


def _filter(rows: list[dict[str, Any]], *, start: datetime, environment: str, agent: str, provider: str, model: str, status: str) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        timestamp = _dt(row.get("timestamp_utc"))
        if timestamp is None or timestamp < start: continue
        if environment != "all" and str(row.get("environment") or row.get("provider") or "").casefold() != environment.casefold(): continue
        if agent != "all" and str(row.get("agent_id") or row.get("stage") or "").casefold() != agent.casefold(): continue
        if provider != "all" and str(row.get("provider") or "").casefold() != provider.casefold(): continue
        if model != "all" and str(row.get("model_identifier") or "").casefold() != model.casefold(): continue
        if status != "all" and str(row.get("llm_invocation_status") or row.get("feedback_decision") or "").casefold() != status.casefold(): continue
        output.append(row)
    return output


def observability_summary(*, days: int = 30, environment: str = "all", agent: str = "all", provider: str = "all", model: str = "all", status: str = "all") -> dict[str, Any]:
    end = utc_now(); start = end - timedelta(days=days)
    executions, execution_errors = read_records("executions"); feedback, feedback_errors = read_records("feedback")
    selected = _filter(executions, start=start, environment=environment, agent=agent, provider=provider, model=model, status=status)
    selected_feedback = _filter(feedback, start=start, environment=environment, agent=agent, provider="all", model="all", status=status)
    llm_calls = sum(int(row.get("model_call_count") or 0) for row in selected)
    successful = sum(row.get("llm_invocation_status") == "completed" for row in selected)
    failed = sum(row.get("llm_invocation_status") not in {"completed", "not_invoked"} for row in selected)
    fallbacks = sum("fallback" in str(row.get("execution_mode") or "").casefold() for row in selected)
    known_costs = [float(row["estimated_cost_usd"]) for row in selected if row.get("estimated_cost_usd") is not None and int(row.get("model_call_count") or 0) > 0]
    tokens = sum(int(row.get("total_tokens") or 0) for row in selected)
    latencies = [float(row.get("total_analysis_time_ms") or 0) for row in selected]
    llm_latencies = [float(row.get("model_execution_time_ms") or 0) for row in selected if int(row.get("model_call_count") or 0) > 0]
    deterministic_latencies = [float(row.get("total_analysis_time_ms") or 0) for row in selected if int(row.get("model_call_count") or 0) == 0]
    decisions = Counter(row.get("feedback_decision") for row in selected_feedback)
    dates = sorted({str(row.get("timestamp_utc") or "")[:10] for row in selected + selected_feedback if row.get("timestamp_utc")})
    trends = [{"date": date, "executions": sum(str(row.get("timestamp_utc", "")).startswith(date) for row in selected), "llm_calls": sum(int(row.get("model_call_count") or 0) for row in selected if str(row.get("timestamp_utc", "")).startswith(date)), "feedback": sum(str(row.get("timestamp_utc", "")).startswith(date) for row in selected_feedback), "estimated_cost_usd": round(sum(float(row.get("estimated_cost_usd") or 0) for row in selected if str(row.get("timestamp_utc", "")).startswith(date)), 10)} for date in dates]
    disputed = Counter(str(row.get("finding_reference") or row.get("result_reference") or "Unspecified result") for row in selected_feedback if row.get("feedback_decision") in {"Incorrect", "Needs Review"})
    return {
        "metadata": {"source": "V2 local metadata-only telemetry", "start": utc_text(start), "end": utc_text(end), "filters": {"days": days, "environment": environment, "agent": agent, "provider": provider, "model": model, "status": status}, "read_errors": execution_errors + feedback_errors},
        "summary": {"total_executions": len(selected), "successful_llm_executions": successful, "failed_llm_executions": failed, "total_llm_calls": llm_calls, "input_tokens": sum(int(row.get("input_tokens") or 0) for row in selected), "output_tokens": sum(int(row.get("output_tokens") or 0) for row in selected), "total_tokens": tokens, "average_tokens_per_llm_request": round(tokens / llm_calls, 2) if llm_calls else None, "estimated_cost_usd": round(sum(known_costs), 10) if known_costs and len(known_costs) == sum(int(row.get("model_call_count") or 0) > 0 for row in selected) else None, "average_cost_per_request": round(sum(known_costs) / llm_calls, 10) if known_costs and llm_calls and len(known_costs) == sum(int(row.get("model_call_count") or 0) > 0 for row in selected) else None, "fallback_count": fallbacks, "error_count": failed, "feedback_submissions": len(selected_feedback), "positive_feedback": decisions["Correct"], "negative_feedback": decisions["Incorrect"], "needs_review_feedback": decisions["Needs Review"]},
        "performance": {"sample_count": len(latencies), "average_ms": round(sum(latencies) / len(latencies), 3) if latencies else None, "p50_ms": _percentile(latencies, .5), "p95_ms": _percentile(latencies, .95) if len(latencies) >= 2 else None, "max_ms": max(latencies, default=None), "average_llm_ms": round(sum(llm_latencies) / len(llm_latencies), 3) if llm_latencies else None, "average_deterministic_ms": round(sum(deterministic_latencies) / len(deterministic_latencies), 3) if deterministic_latencies else None, "error_rate": round(failed * 100 / len(selected), 2) if selected else None, "fallback_rate": round(fallbacks * 100 / len(selected), 2) if selected else None, "throughput_per_day": round(len(selected) / days, 3)},
        "llm_by_agent": _distribution(selected, "agent_id", "model_call_count"), "llm_by_provider": _distribution([row for row in selected if row.get("provider")], "provider", "model_call_count"), "llm_by_model": _distribution([row for row in selected if row.get("model_identifier")], "model_identifier", "model_call_count"),
        "cost_by_agent": _distribution([row for row in selected if row.get("estimated_cost_usd") is not None], "agent_id", "estimated_cost_usd"), "cost_by_provider": _distribution([row for row in selected if row.get("estimated_cost_usd") is not None], "provider", "estimated_cost_usd"), "cost_by_model": _distribution([row for row in selected if row.get("estimated_cost_usd") is not None], "model_identifier", "estimated_cost_usd"),
        "feedback_by_stage": _distribution(selected_feedback, "stage"), "feedback_by_provider": _distribution(selected_feedback, "provider"), "feedback_by_decision": _distribution(selected_feedback, "feedback_decision"), "frequently_disputed": [{"name": name, "value": value} for name, value in disputed.most_common(10)], "trends": trends,
        "recent_executions": list(reversed(selected[-100:])), "recent_feedback": list(reversed(selected_feedback[-100:])),
        "limitations": ["Feedback is user agreement, not independently verified accuracy.", "P95 is unavailable with fewer than two observations.", "Cost is unavailable unless every LLM call in scope has attributable token usage and configured pricing.", "Advanced quality scoring is not yet evaluated because no labeled ground-truth dataset exists."],
    }


def csv_export(rows: Iterable[dict[str, Any]]) -> str:
    values = list(rows)
    if not values: return ""
    keys = sorted({key for row in values for key in row})
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader()
    for row in values: writer.writerow({key: json.dumps(row.get(key), default=str) if isinstance(row.get(key), (dict, list)) else row.get(key) for key in keys})
    return stream.getvalue()
