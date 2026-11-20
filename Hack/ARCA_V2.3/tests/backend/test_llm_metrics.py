from time import perf_counter

from backend.llm.schemas import LlmCallMetrics, TokenUsage
from backend.services.llm_metrics import estimate_cost, execution_metrics


def test_known_model_cost_uses_versioned_pricing_and_actual_usage():
    usage = TokenUsage(input_tokens=1000, output_tokens=500, total_tokens=1500, calls=[LlmCallMetrics(operation="agent1_analysis", status="completed", provider="openai", model_identifier="gpt-5-mini", duration_ms=25, input_tokens=1000, output_tokens=500, total_tokens=1500)])
    cost, version, status = estimate_cost("openai", "gpt-5-mini", usage)
    assert status == "estimated" and version and cost is not None and cost > 0


def test_unknown_model_and_missing_usage_are_not_fabricated():
    attempted = TokenUsage(calls=[LlmCallMetrics(operation="agent1_analysis", status="timeout", provider="openai", model_identifier="unknown-model", duration_ms=10)])
    assert estimate_cost("openai", "unknown-model", attempted)[2] == "usage_unavailable"
    metrics = execution_metrics(agent_id="A1", execution_mode="llm_assisted", provider="openai", model="unknown-model", status="timeout", usage=attempted, started_at=perf_counter())
    assert metrics["model_call_count"] == 1 and metrics["total_tokens"] is None and metrics["estimated_cost_usd"] is None
