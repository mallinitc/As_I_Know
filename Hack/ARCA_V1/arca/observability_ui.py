"""Streamlit presentation for local ARCA telemetry."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import statistics
import streamlit as st

from .observability import (csv_export, filter_records, latest_feedback, log_feedback,
                            log_dir, percentile, read_records_with_diagnostics, time_window)


def feedback_controls(assessment: dict | None, key: str) -> None:
    if not assessment: return
    with st.expander("Assessment feedback"):
        st.markdown("**Was ARCA's assessment correct?**")
        decision = st.radio("Feedback decision", ["Not Reviewed", "Correct", "Incorrect", "Needs Review"],
                            horizontal=True, key=f"feedback-decision-{key}", label_visibility="collapsed")
        reason = st.text_area("Feedback reason (optional)", key=f"feedback-reason-{key}", height=80)
        if st.button("Submit Feedback", key=f"feedback-submit-{key}", disabled=decision == "Not Reviewed"):
            log_feedback(assessment_id=assessment["assessment_id"],
                         original_decision=assessment["final_assessment_status"], feedback_decision=decision,
                         feedback_reason=reason, environment=assessment.get("environment", ""),
                         feature=assessment.get("feature", ""), user_session_id="streamlit")
            st.success("Feedback recorded. It does not change the original ARCA decision.")


def _filter_options(records, key):
    return ["All"] + sorted({str(x.get(key)) for x in records if x.get(key)})


def _filter_options_for(records, *keys):
    return ["All"] + sorted({str(row.get(key)) for row in records for key in keys if row.get(key)})


def _remember_filter(key):
    st.session_state[f"{key}-saved"] = st.session_state[key]


def _chart(rows, x, y, title):
    st.markdown(f"**{title}**")
    if rows: st.bar_chart(rows, x=x, y=y, use_container_width=True)
    else: st.caption("No telemetry is available for the selected filters.")


def _daily(records, value=None):
    values = defaultdict(float)
    for row in records:
        day = str(row.get("timestamp_utc", ""))[:10]
        if day: values[day] += float(row.get(value) or 0) if value else 1
    return [{"Date": day, "Value": amount} for day, amount in sorted(values.items())]


def _group(records, key, value=None):
    values = defaultdict(float)
    for row in records:
        label = str(row.get(key) or "Unknown")
        values[label] += float(row.get(value) or 0) if value else 1
    return [{"Group": label, "Value": amount} for label, amount in sorted(values.items())]


def render_observability() -> None:
    st.markdown("<div class='section-eyebrow'>Runtime assurance telemetry</div><div class='section-title'>Observability</div><div class='section-copy'>Local usage, cost estimates, validation outcomes, performance traces, and user feedback. Costs are ARCA estimates, not provider billing.</div>", unsafe_allow_html=True)
    diagnostics = {}
    def load(name):
        rows, errors = read_records_with_diagnostics(name)
        diagnostics[name] = errors
        # Records written before schema versioning remain valid and must not disappear.
        return [row for row in rows if row.get("telemetry_schema_version") in (None, 1)]
    llm, assessments = load("llm_calls"), load("assessments")
    feedback, spans = load("feedback"), load("performance_spans")
    all_records = llm + assessments + feedback + spans

    with st.container(border=True):
        title_col, reset_col = st.columns([5, 1], vertical_alignment="center")
        with title_col: st.markdown("**Global Filters**")
        with reset_col:
            reset = st.button("Reset Filters", key="metrics-reset-filters", width="stretch")
        filter_defaults = {
            "metrics-time": "Last 24 hours", "metrics-environment": "All",
            "metrics-stage": "All", "metrics-status": "All", "metrics-agent": "All",
            "metrics-provider": "All", "metrics-model": "All",
        }
        if reset:
            for key, value in filter_defaults.items():
                st.session_state[key] = value
                st.session_state[f"{key}-saved"] = value
            st.rerun()

        time_options = ["Last 24 hours", "Last 2 days", "Last 5 days", "Last 7 days", "Last 15 days", "Last 30 days", "Custom date range"]
        environment_options = _filter_options(all_records, "environment")
        stage_options = _filter_options_for(all_records, "feature", "stage")
        status_options = _filter_options_for(llm + assessments + spans + feedback, "status", "final_assessment_status", "feedback_decision")
        agent_options = _filter_options_for(llm + spans, "agent_name", "agent")
        provider_options = _filter_options(llm, "provider")
        model_options = _filter_options(llm, "model_id")
        option_sets = {"metrics-time": time_options, "metrics-environment": environment_options,
                       "metrics-stage": stage_options, "metrics-status": status_options,
                       "metrics-agent": agent_options, "metrics-provider": provider_options,
                       "metrics-model": model_options}
        for key, options in option_sets.items():
            saved_key = f"{key}-saved"
            saved = st.session_state.get(saved_key, filter_defaults[key])
            if saved not in options: saved = filter_defaults[key]
            if key not in st.session_state: st.session_state[key] = saved
            if st.session_state.get(key) not in options: st.session_state[key] = saved
            st.session_state[saved_key] = st.session_state[key]

        f1, f2, f3, f4 = st.columns(4)
        with f1: period = st.selectbox("Time", time_options, key="metrics-time", on_change=_remember_filter, args=("metrics-time",))
        custom = None
        with f2: environment = st.selectbox("Environment", environment_options, key="metrics-environment", on_change=_remember_filter, args=("metrics-environment",))
        with f3: stage = st.selectbox("Stage / feature", stage_options, key="metrics-stage", on_change=_remember_filter, args=("metrics-stage",))
        with f4: status = st.selectbox("Status", status_options, key="metrics-status", on_change=_remember_filter, args=("metrics-status",))
        if period == "Custom date range": custom = st.date_input("Custom date range", value=(datetime.now().date(), datetime.now().date()), key="metrics-custom-range")

        active_advanced = sum(st.session_state.get(key, "All") != "All" for key in ("metrics-agent", "metrics-provider", "metrics-model"))
        advanced_label = f"Advanced Filters ({active_advanced} active)" if active_advanced else "Advanced Filters"
        with st.expander(advanced_label, expanded=False):
            f5, f6, f7 = st.columns(3)
            with f5: agent = st.selectbox("Agent", agent_options, key="metrics-agent", on_change=_remember_filter, args=("metrics-agent",))
            with f6: provider = st.selectbox("LLM provider", provider_options, key="metrics-provider", on_change=_remember_filter, args=("metrics-provider",))
            with f7: model = st.selectbox("Model", model_options, key="metrics-model", on_change=_remember_filter, args=("metrics-model",))
    custom_range = custom if isinstance(custom, tuple) and len(custom) == 2 else None
    start, end = time_window(period, custom=custom_range)
    filtered_assessments = filter_records(assessments, start=start, end=end,
                                          environment=environment, feature=stage,
                                          final_assessment_status=status)
    filtered_feedback = filter_records(feedback, start=start, end=end,
                                       environment=environment, feature=stage,
                                       feedback_decision=status)
    filtered_llm = filter_records(llm, start=start, end=end, environment=environment, feature=stage,
                                  provider=provider, model_id=model, status=status,
                                  agent_name=agent)
    filtered_spans = filter_records(spans, start=start, end=end,
                                    environment=environment, stage=stage, status=status, agent=agent)

    overview = st.expander("Overview", expanded=True)
    usage_tab = st.expander("LLM Usage & Cost")
    validation_tab = st.expander("Validation Analytics")
    performance_tab = st.expander("Performance Analytics")
    feedback_tab = st.expander("Human Feedback")
    latest = latest_feedback(filtered_feedback)
    decisions = Counter(x.get("feedback_decision") for x in latest.values())
    reviewed_ids = {key[0] for key in latest}
    total_cost = sum(float(x.get("estimated_cost_usd") or 0) for x in filtered_llm)
    with overview:
        row1 = st.columns(4); row2 = st.columns(5)
        metrics = [("Total assessments", len(filtered_assessments)), ("Total LLM API calls", len(filtered_llm)),
                   ("Estimated LLM cost", f"${total_cost:.6f}"), ("Failed API calls", sum(x.get("status") == "failure" for x in filtered_llm))]
        for col, (label, value) in zip(row1, metrics): col.metric(label, value)
        metrics2 = [("Input tokens", sum(x.get("input_tokens") or 0 for x in filtered_llm)),
                    ("Output tokens", sum(x.get("output_tokens") or 0 for x in filtered_llm)),
                    ("Confirmed correct", decisions["Correct"]), ("Reported incorrect", decisions["Incorrect"]),
                    ("Unreviewed decisions", max(len(filtered_assessments) - len(reviewed_ids), 0))]
        for col, (label, value) in zip(row2, metrics2): col.metric(label, value)
        st.caption("Feedback represents user agreement, not independently verified model accuracy. No feedback is counted as not reviewed.")

    with usage_tab:
        c1, c2 = st.columns(2)
        with c1: _chart(_daily(filtered_llm, "estimated_cost_usd"), "Date", "Value", "Daily estimated spending")
        with c2: _chart(_daily(filtered_llm), "Date", "Value", "Daily API requests")
        token_rows = []
        for day in sorted({str(x.get("timestamp_utc", ""))[:10] for x in filtered_llm}):
            selected = [x for x in filtered_llm if str(x.get("timestamp_utc", "")).startswith(day)]
            token_rows.extend(({"Date": day, "Token type": "Input", "Tokens": sum(x.get("input_tokens") or 0 for x in selected)},
                               {"Date": day, "Token type": "Output", "Tokens": sum(x.get("output_tokens") or 0 for x in selected)}))
        if token_rows: st.line_chart(token_rows, x="Date", y="Tokens", color="Token type")
        c1, c2 = st.columns(2)
        with c1: _chart(_group(filtered_llm, "feature", "estimated_cost_usd"), "Group", "Value", "Cost by stage")
        with c2: _chart(_group(filtered_llm, "model_id", "estimated_cost_usd"), "Group", "Value", "Cost by provider / model")
        latencies = [x.get("duration_ms") for x in filtered_llm if x.get("duration_ms") is not None]
        l1, l2 = st.columns(2); l1.metric("Average request latency", f"{statistics.mean(latencies):.0f} ms" if latencies else "Unavailable"); l2.metric("P95 request latency", f"{percentile(latencies, .95):.0f} ms" if latencies else "Unavailable")
        st.dataframe(filtered_llm, hide_index=True, width="stretch") if filtered_llm else st.info("No LLM calls in the selected period.")
        st.download_button("Export filtered API calls", csv_export(filtered_llm), "arca_llm_usage.csv", "text/csv", disabled=not filtered_llm)

    with validation_tab:
        c1, c2 = st.columns(2)
        with c1: _chart(_group(filtered_assessments, "feature"), "Group", "Value", "Assessments by stage")
        with c2: _chart(_group(filtered_assessments, "final_assessment_status"), "Group", "Value", "Result distribution")
        _chart(_daily(filtered_assessments), "Date", "Value", "Assessments over time")
        severity = [{"Severity": label, "Findings": sum(x.get(key) or 0 for x in filtered_assessments)} for label, key in (("Error", "error_finding_count"), ("Warning", "warning_finding_count"), ("Review", "review_finding_count"))]
        _chart(severity, "Severity", "Findings", "Findings by severity")
        st.dataframe(filtered_assessments, hide_index=True, width="stretch") if filtered_assessments else st.info("No assessments in the selected period.")
        st.download_button("Export filtered assessments", csv_export(filtered_assessments), "arca_assessments.csv", "text/csv", disabled=not filtered_assessments)

    with performance_tab:
        if not filtered_spans: st.info("Insufficient observations.")
        else:
            by_stage = defaultdict(list); by_agent = defaultdict(list)
            for row in filtered_spans:
                by_stage[row.get("stage") or "Unknown"].append(row.get("duration_ms") or 0)
                by_agent[row.get("agent") or "Unknown"].append(row.get("duration_ms") or 0)
            stage_rows = [{"Stage": key, "Average ms": statistics.mean(values), "P50 ms": percentile(values, .5), "P95 ms": percentile(values, .95)} for key, values in by_stage.items()]
            agent_rows = [{"Agent": key, "Average ms": statistics.mean(values), "P95 ms": percentile(values, .95)} for key, values in by_agent.items()]
            c1, c2 = st.columns(2)
            with c1: st.dataframe(stage_rows, hide_index=True, width="stretch")
            with c2: st.dataframe(agent_rows, hide_index=True, width="stretch")
            executions = sorted({x.get("execution_id") for x in filtered_spans if x.get("execution_id")})
            if executions:
                selected = st.selectbox("Execution breakdown", executions)
                trace = [x for x in filtered_spans if x.get("execution_id") == selected]
                st.dataframe(sorted(trace, key=lambda x: x.get("start_time", "")), hide_index=True, width="stretch")
                longest = max(trace, key=lambda x: x.get("duration_ms") or 0)
                st.caption(f"Longest observed operation: {longest.get('component_name')} ({longest.get('duration_ms', 0):.0f} ms). Nested spans are shown separately and are not summed into wall-clock duration.")
            st.dataframe(filtered_spans, hide_index=True, width="stretch")
            st.download_button("Export filtered traces", csv_export(filtered_spans), "arca_performance_spans.csv", "text/csv")

    with feedback_tab:
        total_reviewed = sum(decisions[x] for x in ("Correct", "Incorrect", "Needs Review"))
        agreement = decisions["Correct"] / total_reviewed * 100 if total_reviewed else None
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Confirmed correct", decisions["Correct"]); f2.metric("Reported incorrect", decisions["Incorrect"])
        f3.metric("Needs Review", decisions["Needs Review"]); f4.metric("User agreement", f"{agreement:.1f}%" if agreement is not None else "Not available")
        st.caption("Agreement is calculated only among reviewed decisions and represents user agreement, not verified accuracy.")
        _chart(_group(list(latest.values()), "feedback_decision"), "Group", "Value", "Latest feedback distribution")
        st.dataframe(filtered_feedback, hide_index=True, width="stretch") if filtered_feedback else st.info("No feedback in the selected period.")
        st.download_button("Export feedback history", csv_export(filtered_feedback), "arca_feedback.csv", "text/csv", disabled=not filtered_feedback)

    latest_timestamps = [row.get("timestamp_utc") for row in all_records if row.get("timestamp_utc")]
    included = len(filtered_llm) + len(filtered_assessments) + len(filtered_feedback) + len(filtered_spans)
    with st.expander("Telemetry Diagnostics"):
        d1, d2 = st.columns(2)
        d1.markdown(f"**Logging enabled:** Yes  \n**Logs directory:** `{log_dir().resolve()}`  \n**Latest event timestamp:** {max(latest_timestamps) if latest_timestamps else 'No events recorded'}")
        d2.markdown(f"**LLM records found:** {len(llm)}  \n**Assessment records found:** {len(assessments)}  \n**Feedback records found:** {len(feedback)}  \n**Performance spans found:** {len(spans)}  \n**Records excluded by current filters:** {max(len(all_records) - included, 0)}")
        read_errors = [error for errors in diagnostics.values() for error in errors]
        if read_errors:
            st.warning("Log-reading issues: " + "; ".join(read_errors))
        else:
            st.caption("No log-reading errors detected. Legacy unversioned records are included for backward compatibility.")
