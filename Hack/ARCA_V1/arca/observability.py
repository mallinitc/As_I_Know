"""Portable, best-effort JSONL observability for ARCA.

Telemetry must never interrupt an assurance decision. Records contain metadata by
default; model content is opt-in, size-limited, and redacted.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import csv
import io
import json
import os
from pathlib import Path
import re
import threading
from time import perf_counter
from typing import Any, Iterable
from uuid import uuid4

from .paths import PROVIDERS, log_dir as environment_log_dir, log_root

UTC = timezone.utc
LOG_NAMES = ("llm_calls", "assessments", "feedback", "errors", "performance_spans")
_LOCK = threading.RLock()
_context: ContextVar[dict[str, Any]] = ContextVar("arca_observability_context", default={})

PRICING_CATALOG = {
    # USD per one million tokens. These are ARCA estimates, not provider invoices.
    ("openai", "gpt-5-mini"): {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    ("openai", "gpt-4.1-mini"): {"input": 0.40, "cached_input": 0.10, "output": 1.60},
    ("bedrock", "anthropic.claude-3-5-sonnet-20241022-v2:0"): {"input": 3.00, "output": 15.00},
}


def pricing_catalog() -> dict[tuple[str, str], dict[str, float]]:
    """Load optional portable pricing overrides from config/model_pricing.json."""
    catalog = dict(PRICING_CATALOG)
    path = Path(os.getenv("ARCA_PRICING_FILE", Path(__file__).resolve().parents[1] / "config" / "model_pricing.json"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("models", []):
            catalog[(item["provider"], item["model_id"])] = {key: float(value) for key, value in item["usd_per_million_tokens"].items()}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError): pass
    return catalog


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log_dir() -> Path:
    return log_root()


def ensure_log_files(environment: str | None = None) -> dict[str, Path]:
    """Create log files in a provider directory, or the legacy/shared root."""
    provider = str(environment or "").strip().lower()
    root = environment_log_dir(provider if provider in PROVIDERS else None, create=True)
    paths = {name: root / f"{name}.jsonl" for name in LOG_NAMES}
    for path in paths.values(): path.touch(exist_ok=True)
    return paths


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def telemetry_context(**values):
    """Temporarily attach stage/environment/assessment metadata to nested calls."""
    merged = {**_context.get(), **{k: v for k, v in values.items() if v is not None}}
    token = _context.set(merged)
    class Reset:
        def __enter__(self): return merged
        def __exit__(self, *_): _context.reset(token)
    return Reset()


def current_context() -> dict[str, Any]:
    return dict(_context.get())


def _append(name: str, record: dict[str, Any]) -> bool:
    try:
        record.setdefault("telemetry_schema_version", 1)
        environment = record.get("environment") or current_context().get("environment")
        path = ensure_log_files(environment)[name]
        line = json.dumps(record, ensure_ascii=False, default=str, separators=(",", ":")) + "\n"
        with _LOCK, path.open("a", encoding="utf-8", newline="") as handle:
            # Streamlit sessions share a process; flush makes records immediately visible.
            handle.write(line); handle.flush()
        return True
    except Exception:
        return False


_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+"),
    re.compile(r"(?i)((?:openai_api_key|api[_-]?key|secret|token|password)\s*[:=]\s*)[^\s,;\"']+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
]


def redact(value: Any, limit: int = 8000) -> tuple[Any, bool]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    for pattern in _SECRET_PATTERNS: text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    truncated = len(text) > limit
    return text[:limit], truncated


def content_capture(model_input: Any = None, model_output: Any = None) -> dict[str, Any]:
    enabled = os.getenv("ARCA_LOG_LLM_CONTENT", "false").strip().lower() in {"1", "true", "yes"}
    result = {"content_logging_enabled": enabled}
    if enabled:
        result["model_input"], input_cut = redact(model_input)
        result["model_output"], output_cut = redact(model_output)
        result["content_truncated"] = input_cut or output_cut
    return result


def normalize_openai_usage(usage: Any) -> dict[str, int | None]:
    if usage is None: return {k: None for k in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens", "total_tokens")}
    get = lambda obj, key, default=None: obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    inp, out = get(usage, "input_tokens"), get(usage, "output_tokens")
    input_details, output_details = get(usage, "input_tokens_details", {}) or {}, get(usage, "output_tokens_details", {}) or {}
    cached = get(input_details, "cached_tokens")
    reasoning = get(output_details, "reasoning_tokens")
    total = get(usage, "total_tokens", (inp + out if inp is not None and out is not None else None))
    return {"input_tokens": inp, "output_tokens": out, "cached_input_tokens": cached,
            "reasoning_output_tokens": reasoning, "total_tokens": total}


def normalize_bedrock_usage(response: Any) -> dict[str, int | None]:
    usage = (response or {}).get("usage", {}) if isinstance(response, dict) else {}
    inp, out = usage.get("inputTokens"), usage.get("outputTokens")
    return {"input_tokens": inp, "output_tokens": out, "cached_input_tokens": usage.get("cacheReadInputTokens"),
            "reasoning_output_tokens": None, "total_tokens": usage.get("totalTokens", inp + out if inp is not None and out is not None else None)}


def estimate_cost(provider: str, model: str, usage: dict[str, Any]) -> tuple[float | None, str]:
    if provider == "mock": return 0.0, "estimated"
    prices = pricing_catalog().get((provider, model))
    if not prices: return None, "unknown"
    inp, cached, out = usage.get("input_tokens"), usage.get("cached_input_tokens") or 0, usage.get("output_tokens")
    if inp is None or out is None: return None, "partial_or_unknown"
    uncached = max(inp - cached, 0)
    cost = (uncached * prices["input"] + cached * prices.get("cached_input", prices["input"]) + out * prices["output"]) / 1_000_000
    return round(cost, 10), "estimated"


def log_llm_call(*, provider: str, model_id: str, duration_ms: float, status: str,
                 usage: dict[str, Any] | None = None, error: Exception | str | None = None,
                 request_type: str = "structured_parse", retry_attempt_count: int = 0,
                 model_input: Any = None, model_output: Any = None, **metadata) -> str:
    call_id = metadata.pop("call_id", None) or new_id("llm")
    ctx = {**current_context(), **metadata}; normalized = usage or {}
    cost, cost_status = estimate_cost(provider, model_id, normalized)
    record = {"call_id": call_id, "timestamp_utc": iso_utc(), "environment": ctx.get("environment"),
              "feature": ctx.get("feature") or ctx.get("stage"), "stage": ctx.get("stage"),
              "agent_name": ctx.get("agent_name"), "provider": provider, "model_id": model_id,
              "request_type": request_type, **{k: normalized.get(k) for k in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens", "total_tokens")},
              "estimated_cost_usd": cost, "cost_status": cost_status, "billing_basis": "ARCA estimate",
              "duration_ms": round(duration_ms, 3), "status": status,
              "error_category": type(error).__name__ if isinstance(error, Exception) else (str(error) if error else None),
              "assessment_id": ctx.get("assessment_id"), "change_id": ctx.get("change_id"),
              "retry_attempt_count": retry_attempt_count, **content_capture(model_input, model_output)}
    _append("llm_calls", record)
    return call_id


def stable_finding_id(assessment_id: str, index: int, finding: Any) -> str:
    import hashlib
    raw = json.dumps(finding, sort_keys=True, default=str)
    return f"finding_{hashlib.sha256(f'{assessment_id}:{index}:{raw}'.encode()).hexdigest()[:20]}"


def log_assessment(*, feature: str, environment: str, final_status: str, findings: Iterable[Any] = (),
                   duration_ms: float = 0, assessment_id: str | None = None, **metadata) -> dict[str, Any]:
    idempotency_key = metadata.pop("idempotency_key", None)
    if idempotency_key:
        existing = next((item for item in reversed(read_records("assessments"))
                         if item.get("idempotency_key") == idempotency_key), None)
        if existing: return existing
    assessment_id = assessment_id or new_id("assessment"); rows = list(findings or [])
    detailed = []
    counts = {"error": 0, "warning": 0, "review": 0}
    for index, item in enumerate(rows):
        value = item if isinstance(item, dict) else (item.model_dump() if hasattr(item, "model_dump") else {"message": str(item)})
        severity = str(value.get("severity") or value.get("status") or value.get("category") or "review").lower()
        bucket = "error" if any(x in severity for x in ("error", "invalid", "inconsistent", "fail")) else "warning" if "warn" in severity else "review"
        counts[bucket] += 1
        detailed.append({"finding_id": stable_finding_id(assessment_id, index, value), **value})
    record = {"assessment_id": assessment_id, "execution_id": metadata.pop("execution_id", new_id("exec")),
              "timestamp_utc": iso_utc(), "environment": environment, "feature": feature, "stage": metadata.pop("stage", feature),
              "selected_scenario": metadata.pop("selected_scenario", None), "change_id": metadata.pop("change_id", None),
              "actor_session_id": metadata.pop("actor_session_id", None), "final_assessment_status": final_status,
              "finding_count": len(detailed), "error_finding_count": counts["error"],
              "warning_finding_count": counts["warning"], "review_finding_count": counts["review"],
              "duration_ms": round(duration_ms, 3), "related_llm_call_ids": metadata.pop("related_llm_call_ids", []),
              "findings": detailed, **metadata}
    if idempotency_key: record["idempotency_key"] = idempotency_key
    _append("assessments", record)
    return record


def log_feedback(*, assessment_id: str, original_decision: str, feedback_decision: str,
                 environment: str, feature: str, finding_id: str | None = None,
                 feedback_reason: str = "", user_session_id: str | None = None) -> dict[str, Any]:
    record = {"feedback_id": new_id("feedback"), "timestamp_utc": iso_utc(), "assessment_id": assessment_id,
              "finding_id": finding_id, "original_arca_decision": original_decision,
              "feedback_decision": feedback_decision, "feedback_reason": feedback_reason[:2000],
              "environment": environment, "feature": feature, "user_session_id": user_session_id}
    _append("feedback", record); return record


def log_error(error: Exception, **metadata) -> None:
    _append("errors", {"error_id": new_id("error"), "timestamp_utc": iso_utc(),
                       "error_category": type(error).__name__, **metadata})


def log_performance(*, component_name: str, stage: str, duration_ms: float, status: str = "success",
                    agent: str | None = None, trace_id: str | None = None, span_id: str | None = None,
                    parent_span_id: str | None = None, **metadata) -> dict[str, Any]:
    """Record a duration already measured with perf_counter (useful at UI action boundaries)."""
    record = {"trace_id": trace_id or new_id("trace"), "span_id": span_id or new_id("span"),
              "parent_span_id": parent_span_id, "execution_id": metadata.get("execution_id"),
              "assessment_id": metadata.get("assessment_id"), "llm_call_id": metadata.get("llm_call_id"),
              "timestamp_utc": iso_utc(), "start_time": metadata.get("start_time"), "end_time": iso_utc(),
              "component_name": component_name, "stage": stage, "agent": agent,
              "duration_ms": round(duration_ms, 3), "status": status,
              "error_category": metadata.get("error_category"), "environment": metadata.get("environment")}
    _append("performance_spans", record); return record


@contextmanager
def performance_span(component_name: str, *, stage: str, agent: str | None = None,
                     trace_id: str | None = None, parent_span_id: str | None = None, **metadata):
    metadata = {**current_context(), **metadata}
    trace_id, span_id = trace_id or new_id("trace"), new_id("span"); started_at = iso_utc(); start = perf_counter()
    holder = {"trace_id": trace_id, "span_id": span_id}
    try:
        yield holder
    except Exception as exc:
        status, error = "failure", type(exc).__name__; raise
    else: status, error = "success", None
    finally:
        duration = (perf_counter() - start) * 1000
        _append("performance_spans", {"trace_id": trace_id, "span_id": span_id, "parent_span_id": parent_span_id,
            "execution_id": metadata.get("execution_id"), "assessment_id": metadata.get("assessment_id"),
            "llm_call_id": metadata.get("llm_call_id"), "timestamp_utc": started_at, "start_time": started_at,
            "end_time": iso_utc(), "component_name": component_name, "stage": stage, "agent": agent,
            "duration_ms": round(duration, 3), "status": status, "error_category": error,
            "environment": metadata.get("environment")})


def read_records(name: str) -> list[dict[str, Any]]:
    records, _ = read_records_with_diagnostics(name)
    return records


def read_records_with_diagnostics(name: str) -> tuple[list[dict[str, Any]], list[str]]:
    if name not in LOG_NAMES: raise ValueError(f"Unknown log: {name}")
    errors: list[str] = []
    try:
        root = log_dir(); root.mkdir(parents=True, exist_ok=True)
        # Read legacy/shared logs plus isolated provider logs. Existing records are
        # deliberately not moved or rewritten.
        paths = [root / f"{name}.jsonl"] + [root / provider / f"{name}.jsonl" for provider in sorted(PROVIDERS)]
        records = []
        for path in paths:
            if not path.exists():
                continue
            with _LOCK, path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict): records.append(item)
                        else: errors.append(f"{path.parent.name}/{path.name}:{line_number}: record is not a JSON object")
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        errors.append(f"{path.parent.name}/{path.name}:{line_number}: {type(exc).__name__}")
        return records, errors
    except Exception as exc:
        return [], [f"{name}.jsonl: {type(exc).__name__}"]


def parse_timestamp(value: str | None) -> datetime | None:
    try: return datetime.fromisoformat((value or "").replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, TypeError): return None


def filter_records(records: Iterable[dict], *, start: datetime | None = None, end: datetime | None = None, **filters) -> list[dict]:
    output = []
    for record in records:
        timestamp = parse_timestamp(record.get("timestamp_utc"))
        if start and (timestamp is None or timestamp < start.astimezone(UTC)): continue
        if end and (timestamp is None or timestamp > end.astimezone(UTC)): continue
        if any(value not in (None, "", "All") and str(record.get(key, "")).lower() != str(value).lower() for key, value in filters.items()): continue
        output.append(record)
    return output


def time_window(selection: str, now: datetime | None = None, custom: tuple[Any, Any] | None = None) -> tuple[datetime, datetime]:
    end = (now or utc_now()).astimezone(UTC)
    days = {"Last 24 hours": 1, "Last 2 days": 2, "Last 5 days": 5, "Last 7 days": 7,
            "Last 15 days": 15, "Last 30 days": 30}
    if selection == "Custom date range" and custom:
        start_date, end_date = custom
        return datetime.combine(start_date, datetime.min.time(), UTC), datetime.combine(end_date, datetime.max.time(), UTC)
    return end - timedelta(days=days.get(selection, 7)), end


def csv_export(records: Iterable[dict]) -> str:
    rows = list(records)
    if not rows: return ""
    keys = sorted({key for row in rows for key in row if key != "findings"})
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=keys); writer.writeheader()
    for row in rows: writer.writerow({key: json.dumps(row.get(key), default=str) if isinstance(row.get(key), (dict, list)) else row.get(key) for key in keys})
    return stream.getvalue()


def latest_feedback(records: Iterable[dict]) -> dict[tuple[str, str | None], dict]:
    latest = {}
    for item in sorted(records, key=lambda x: x.get("timestamp_utc", "")):
        latest[(item.get("assessment_id"), item.get("finding_id"))] = item
    return latest


def percentile(values: Iterable[float], value: float) -> float | None:
    items = sorted(float(x) for x in values if x is not None)
    if not items: return None
    position = (len(items) - 1) * value; lower = int(position); upper = min(lower + 1, len(items) - 1)
    return items[lower] + (items[upper] - items[lower]) * (position - lower)
