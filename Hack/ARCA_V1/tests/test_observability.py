from datetime import date, datetime, timedelta, timezone
import json
import threading
from pathlib import Path
from streamlit.testing.v1 import AppTest

from arca.observability import (
    content_capture, csv_export, ensure_log_files, estimate_cost, filter_records,
    latest_feedback, log_assessment, log_feedback, log_llm_call, log_performance,
    normalize_bedrock_usage, normalize_openai_usage, percentile, read_records, read_records_with_diagnostics,
    time_window,
)


def configure(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCA_LOG_DIR", str(tmp_path / "logs"))
    return ensure_log_files()


def test_log_files_created_and_successful_llm_call(tmp_path, monkeypatch):
    paths = configure(tmp_path, monkeypatch)
    assert all(path.exists() for path in paths.values())
    call_id = log_llm_call(provider="openai", model_id="gpt-5-mini", duration_ms=12,
                           status="success", usage={"input_tokens": 100, "output_tokens": 20,
                           "cached_input_tokens": 10, "total_tokens": 120})
    row = read_records("llm_calls")[0]
    assert row["call_id"] == call_id and row["total_tokens"] == 120
    assert row["estimated_cost_usd"] > 0


def test_failed_call_has_no_invented_usage_or_cost(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    log_llm_call(provider="openai", model_id="gpt-5-mini", duration_ms=2, status="failure",
                 error=TimeoutError("hidden"))
    row = read_records("llm_calls")[0]
    assert row["error_category"] == "TimeoutError"
    assert row["estimated_cost_usd"] is None


def test_usage_normalization_and_unknown_pricing():
    class Details: cached_tokens = 5; reasoning_tokens = 3
    class Usage:
        input_tokens = 10; output_tokens = 4; total_tokens = 14
        input_tokens_details = Details(); output_tokens_details = Details()
    assert normalize_openai_usage(Usage())["cached_input_tokens"] == 5
    assert normalize_bedrock_usage({"usage": {"inputTokens": 8, "outputTokens": 2}})["total_tokens"] == 10
    assert estimate_cost("openai", "unknown-model", {"input_tokens": 1, "output_tokens": 1}) == (None, "unknown")
    assert estimate_cost("mock", "mock", {}) == (0.0, "estimated")


def test_assessment_findings_feedback_history_and_deduplication(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    first = log_assessment(feature="Stage 1", environment="azure", final_status="INCOMPLETE",
                           findings=[{"severity": "ERROR", "field": "implementer"}], idempotency_key="click-1")
    second = log_assessment(feature="Stage 1", environment="azure", final_status="INCOMPLETE",
                            idempotency_key="click-1")
    assert first["assessment_id"] == second["assessment_id"]
    assert len(read_records("assessments")) == 1
    finding_id = first["findings"][0]["finding_id"]
    log_feedback(assessment_id=first["assessment_id"], finding_id=finding_id,
                 original_decision="INCOMPLETE", feedback_decision="Incorrect",
                 environment="azure", feature="Stage 1")
    latest_row = log_feedback(assessment_id=first["assessment_id"], finding_id=finding_id,
                              original_decision="INCOMPLETE", feedback_decision="Needs Review",
                              environment="azure", feature="Stage 1")
    assert latest_feedback(read_records("feedback"))[(first["assessment_id"], finding_id)]["feedback_id"] == latest_row["feedback_id"]


def test_time_filter_and_csv_export():
    now = datetime(2026, 1, 10, tzinfo=timezone.utc)
    records = [{"timestamp_utc": (now - timedelta(hours=2)).isoformat(), "environment": "azure", "value": 1},
               {"timestamp_utc": (now - timedelta(days=3)).isoformat(), "environment": "aws", "value": 2}]
    start, end = time_window("Last 24 hours", now)
    assert filter_records(records, start=start, end=end, environment="azure") == [records[0]]
    assert "environment" in csv_export(records)
    custom_start, custom_end = time_window("Custom date range", custom=(date(2026, 1, 1), date(2026, 1, 2)))
    assert custom_start.hour == 0 and custom_end.day == 2


def test_malformed_log_lines_are_ignored(tmp_path, monkeypatch):
    paths = configure(tmp_path, monkeypatch)
    paths["errors"].write_text('{bad json}\n{"error_id":"ok"}\n', encoding="utf-8")
    assert read_records("errors") == [{"error_id": "ok"}]
    rows, errors = read_records_with_diagnostics("errors")
    assert rows == [{"error_id": "ok"}]
    assert errors and "JSONDecodeError" in errors[0]


def test_sensitive_content_is_opt_in_redacted_and_truncated(monkeypatch):
    monkeypatch.setenv("ARCA_LOG_LLM_CONTENT", "true")
    captured = content_capture("OPENAI_API_KEY=sk-supersecretvalue " + "x" * 9000, "ok")
    assert "supersecret" not in captured["model_input"]
    assert captured["content_truncated"] is True
    monkeypatch.setenv("ARCA_LOG_LLM_CONTENT", "false")
    assert "model_input" not in content_capture("private", "private")


def test_performance_spans_and_percentiles(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    parent = log_performance(component_name="Stage 1 Validation", stage="Stage 1", duration_ms=100,
                             execution_id="exec-1", span_id="parent")
    child = log_performance(component_name="Input extraction", stage="Stage 1", duration_ms=40,
                            execution_id="exec-1", parent_span_id=parent["span_id"])
    assert child["parent_span_id"] == "parent"
    assert percentile([10, 20, 30, 40], .5) == 25
    # Parent wall time remains 100 ms; nested spans are not summed by the recorder.
    assert read_records("performance_spans")[0]["duration_ms"] == 100


def test_concurrent_append_produces_valid_jsonl(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    threads = [threading.Thread(target=log_llm_call, kwargs={"provider": "mock", "model_id": "mock",
               "duration_ms": index, "status": "success", "usage": {}}) for index in range(20)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert len(read_records("llm_calls")) == 20


def test_metrics_view_reads_persisted_records_and_survives_rerun(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    log_assessment(feature="Stage 1 Validation", environment="azure", final_status="VALID")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
    nav = next(radio for radio in app.radio if list(radio.options) == ["ARCA", "Metrics"])
    nav.set_value("Metrics").run(timeout=30)
    assert not list(app.exception)
    total = next(metric for metric in app.metric if metric.label == "Total assessments")
    assert str(total.value) == "1"


def test_compact_filters_persist_combine_and_reset(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    log_assessment(feature="Stage 1 Validation", environment="azure", final_status="VALID")
    log_llm_call(provider="openai", model_id="gpt-5-mini", duration_ms=10, status="success",
                 usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
                 environment="azure", feature="Stage 1 Validation", agent_name="Draft Refinement")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
    next(radio for radio in app.radio if list(radio.options) == ["ARCA", "Metrics"]).set_value("Metrics").run(timeout=30)

    select = lambda label, required="All": next(widget for widget in app.selectbox if widget.label == label and required in widget.options)
    assert select("Time", "Last 24 hours").value == "Last 24 hours"
    select("Environment").set_value("azure").run(timeout=30)
    select("Stage / feature").set_value("Stage 1 Validation").run(timeout=30)
    select("Status").set_value("success").run(timeout=30)
    select("Agent").set_value("Draft Refinement").run(timeout=30)
    select("LLM provider").set_value("openai").run(timeout=30)
    select("Model").set_value("gpt-5-mini").run(timeout=30)
    next(radio for radio in app.radio if list(radio.options) == ["ARCA", "Metrics"]).set_value("ARCA").run(timeout=30)
    next(radio for radio in app.radio if list(radio.options) == ["ARCA", "Metrics"]).set_value("Metrics").run(timeout=30)
    select = lambda label, required="All": next(widget for widget in app.selectbox if widget.label == label and required in widget.options)
    assert select("Agent").value == "Draft Refinement"
    assert select("LLM provider").value == "openai"
    assert select("Model").value == "gpt-5-mini"
    assert any(expander.label == "Advanced Filters (3 active)" for expander in app.expander)
    calls = next(metric for metric in app.metric if metric.label == "Total LLM API calls")
    assert str(calls.value) == "1"

    next(button for button in app.button if button.label == "Reset Filters").click().run(timeout=30)
    assert select("Time", "Last 24 hours").value == "Last 24 hours"
    for label in ("Environment", "Stage / feature", "Status", "Agent", "LLM provider", "Model"):
        assert select(label).value == "All"
    assert any(expander.label == "Advanced Filters" for expander in app.expander)
    app.run(timeout=30)
    total = next(metric for metric in app.metric if metric.label == "Total assessments")
    assert str(total.value) == "1"
