from __future__ import annotations

import json
from functools import lru_cache
from time import perf_counter
from typing import Any

from backend.config import PROJECT_ROOT
from backend.llm.schemas import TokenUsage


@lru_cache(maxsize=1)
def pricing_catalog() -> dict[str, Any]:
    try:
        payload = json.loads((PROJECT_ROOT / "config" / "model_pricing.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"catalog_version": None, "models": []}
    if payload.get("schema_version") != 1 or not isinstance(payload.get("models"), list):
        return {"catalog_version": None, "models": []}
    return payload


def estimate_cost(provider: str | None, model: str | None, usage: TokenUsage) -> tuple[float | None, str | None, str]:
    if not usage.calls:
        return 0.0, pricing_catalog().get("catalog_version"), "not_applicable"
    catalog = pricing_catalog()
    price = next((
        item for item in catalog.get("models", [])
        if item.get("provider") == provider and item.get("model_id") == model
    ), None)
    measured = any(call.input_tokens is not None and call.output_tokens is not None for call in usage.calls)
    if not measured:
        return None, catalog.get("catalog_version"), "usage_unavailable"
    if not price:
        return None, catalog.get("catalog_version"), "pricing_unavailable"
    rates = price.get("usd_per_million_tokens") or {}
    if "input" not in rates or "output" not in rates:
        return None, catalog.get("catalog_version"), "pricing_unavailable"
    cached = usage.cached_input_tokens or 0
    uncached = max(usage.input_tokens - cached, 0)
    cost = (
        uncached * float(rates["input"])
        + cached * float(rates.get("cached_input", rates["input"]))
        + usage.output_tokens * float(rates["output"])
    ) / 1_000_000
    return round(cost, 10), catalog.get("catalog_version"), "estimated"


def execution_metrics(
    *,
    agent_id: str,
    execution_mode: str,
    provider: str | None,
    model: str | None,
    status: str,
    usage: TokenUsage | None,
    started_at: float,
) -> dict[str, Any]:
    actual = usage or TokenUsage()
    calls = [call.model_dump() for call in actual.calls]
    attempted = bool(calls)
    measured = any(call.get("input_tokens") is not None and call.get("output_tokens") is not None for call in calls)
    cost, catalog_version, cost_status = estimate_cost(provider, model, actual)
    return {
        "agent_id": agent_id,
        "execution_mode": execution_mode,
        "provider": provider,
        "model_identifier": model,
        "llm_invocation_status": status,
        "model_call_count": len(calls),
        "input_tokens": actual.input_tokens if measured else (0 if not attempted else None),
        "output_tokens": actual.output_tokens if measured else (0 if not attempted else None),
        "total_tokens": actual.total_tokens if measured else (0 if not attempted else None),
        "model_execution_time_ms": round(sum(float(call.get("duration_ms") or 0) for call in calls), 3),
        "total_analysis_time_ms": round((perf_counter() - started_at) * 1000, 3),
        "estimated_cost_usd": cost,
        "pricing_catalog_version": catalog_version,
        "cost_status": cost_status,
        "call_details": calls,
    }


__all__ = ["estimate_cost", "execution_metrics", "pricing_catalog"]
