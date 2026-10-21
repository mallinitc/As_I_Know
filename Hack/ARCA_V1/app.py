"""Enterprise Streamlit interface for ARCA."""
from __future__ import annotations

from html import escape
import json
import logging
from pathlib import Path
from time import perf_counter
import streamlit as st
from arca.providers import get_provider, provider_capabilities
from arca.investigation import InvestigationAgent, InvestigationTools
from arca.investigation.snowflake_tools import SnowflakeInvestigationTools
from arca.investigation.ui import choose_question
from arca.time_filters import TIME_RANGES, evidence_reference_time, filter_evidence_window, undocumented_window_status, parse_utc, utc_label
from arca.workflow import build
from arca.change_extraction import extract_existing_change, get_extractor
from arca.change_validation import validate_draft
from arca.smart_draft import draft_field_findings, draft_to_extracted, improve_draft_with_status, servicenow_text
from arca.pim_validation import assess_combined_pim, find_pim_requests, find_pim_requests_by_change, parse_pim_records, record_from_evidence
from arca.demo_catalog import demo_scenarios, pim_records_json, stage1_demo_text
from arca.observability import log_assessment, log_performance, new_id, telemetry_context
from arca.observability_ui import feedback_controls, render_observability
from arca.snowflake_stage2 import (
    UNIFIED_RESULT_SCHEMA_VERSION,
    normalize_unified_result,
    presentation_findings,
)
from arca.ui_actions import processing_action

VERSION_CONFIG = Path(__file__).resolve().parent / "config" / "version.json"
try:
    ARCA_VERSION_LABEL = str(json.loads(VERSION_CONFIG.read_text(encoding="utf-8"))["version_label"])
except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
    ARCA_VERSION_LABEL = "ARCA"

st.set_page_config(page_title="ARCA | Agentic Risk & Change Assurance", page_icon="A", layout="wide", initial_sidebar_state="collapsed")

# Reusable design tokens for the portal theme.
THEME = {
    "navy": "#0B1F3A", "blue": "#1769E0", "green": "#198754",
    "ink": "#172235", "muted": "#617084", "line": "#DDE4EC",
    "canvas": "#F5F7FA", "green_soft": "#E9F7F0", "blue_soft": "#EAF2FF",
    "amber_soft": "#FFF4DE", "red_soft": "#FDECEC",
}
LOGGER = logging.getLogger("arca.ui")


def inject_theme():
    st.markdown(f"""
    <style>
    :root{{--navy:{THEME['navy']};--blue:{THEME['blue']};--green:{THEME['green']};--ink:{THEME['ink']};--muted:{THEME['muted']};--line:{THEME['line']};}}
    .stApp{{background:{THEME['canvas']};color:var(--ink)}}
    [data-testid="stHeader"]{{background:transparent}} [data-testid="stToolbar"]{{right:1.5rem}}
    .block-container{{max-width:1240px;padding:1.25rem 2.25rem 4rem}}
    h1,h2,h3,p,label,div{{font-family:Inter,"Segoe UI",Arial,sans-serif}}
    .portal-header{{display:flex;align-items:center;justify-content:space-between;background:#fff;border:1px solid var(--line);border-radius:14px;padding:.8rem 1.1rem;margin-bottom:1rem;box-shadow:0 4px 16px rgba(11,31,58,.04)}}
    .brand-lockup{{display:flex;align-items:center;gap:.75rem}} .brand-mark{{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;background:var(--navy);color:#fff;font-weight:800}}
    .brand-name{{color:var(--navy);font-weight:760}} .brand-version{{display:inline-flex;margin-left:.4rem;padding:.08rem .38rem;border:1px solid #B8D2E5;border-radius:999px;background:#EAF5FC;color:#185AA6;font-size:.62rem;font-weight:800;vertical-align:middle}} .brand-sub{{color:var(--muted);font-size:.75rem}}
    .user-meta{{display:flex;align-items:center;gap:.65rem;color:var(--muted);font-size:.8rem}} .env-pill{{padding:.3rem .62rem;border-radius:999px;color:#12633d;background:{THEME['green_soft']};border:1px solid #C5E8D6;font-weight:700}}
    .avatar{{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:{THEME['blue_soft']};color:var(--blue);font-weight:750}}
    .profile{{display:flex;justify-content:flex-end;align-items:center;gap:.65rem;padding-top:1.55rem}} .profile-copy{{text-align:right}} .profile-name{{color:var(--navy);font-size:.8rem;font-weight:750}} .profile-role{{color:var(--muted);font-size:.7rem}}
    .hero{{position:relative;isolation:isolate;overflow:hidden;box-sizing:border-box;height:88px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;background:#D9F0FF;border:1px solid #B8DCF3;border-radius:14px;padding:10px 24px;margin-bottom:1.1rem;box-shadow:0 8px 24px rgba(16,42,67,.07)}}
    .hero>*{{position:relative;z-index:2}}
    .hero:before{{content:"";position:absolute;z-index:1;width:118px;height:74px;right:2.15rem;bottom:1.15rem;opacity:.42;border:1px solid rgba(0,119,200,.24);clip-path:polygon(18% 0,100% 0,82% 100%,0 100%);background:repeating-linear-gradient(90deg,transparent 0 17px,rgba(0,119,200,.16) 18px 19px),repeating-linear-gradient(0deg,transparent 0 17px,rgba(0,119,200,.12) 18px 19px)}}
    .hero:after{{content:"";position:absolute;z-index:1;width:210px;height:88px;right:-48px;top:-23px;transform:skewX(-28deg);background:linear-gradient(135deg,rgba(0,119,200,.14),rgba(25,135,84,.07));border-left:1px solid rgba(0,119,200,.2);border-bottom:1px solid rgba(0,119,200,.16)}}
    .hero h1{{color:#102A43;font-size:23px;line-height:1.15;letter-spacing:-.015em;margin:0 0 5px}}
    .hero p{{color:#425C75;font-size:13px;line-height:1.25;margin:0;white-space:nowrap}}
    .hero-meta{{display:flex;gap:.65rem;margin-top:1.35rem}} .hero-chip{{padding:.38rem .68rem;background:rgba(255,255,255,.08);color:#D8E2EE;border:1px solid rgba(255,255,255,.13);border-radius:999px;font-size:.76rem}}
    div[data-testid="stTabs"]{{margin-top:.4rem}} div[data-testid="stTabs"] [data-baseweb="tab-list"]{{gap:.35rem;padding:.35rem;background:transparent;border-radius:10px;width:fit-content;margin-bottom:1.2rem}}
    div[data-testid="stTabs"] [data-baseweb="tab"]{{height:40px;padding:0 1.05rem;border-radius:7px;color:#102A43;background:#EAF5FC;border:1px solid #B8D2E5;font-weight:700;cursor:pointer}}
    div[data-testid="stTabs"] [data-baseweb="tab"]:hover{{color:#fff;background:#005A9C;border-color:#005A9C}}
    div[data-testid="stTabs"] [aria-selected="true"]{{color:#fff!important;background:#0077C8!important;border-color:#0077C8!important;box-shadow:none}}
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{{display:none}}
    div[data-testid="stTabs"] [data-baseweb="tab"]:focus-visible{{outline:3px solid rgba(0,119,200,.28);outline-offset:2px}}
    div[data-testid="stButtonGroup"] [data-variant="segmented_control"]{{min-height:38px!important;padding:.35rem .8rem!important;border:1px solid #B8D2E5!important;background:#EAF5FC!important;color:#102A43!important;font-weight:700!important;cursor:pointer!important}}
    div[data-testid="stButtonGroup"] [data-variant="segmented_control"]:hover{{background:#D9F0FF!important;border-color:#0077C8!important}}
    div[data-testid="stButtonGroup"] [data-variant="segmented_control"][data-selected]{{background:#0077C8!important;color:#fff!important;border-color:#0077C8!important}}
    div[data-testid="stButtonGroup"] [data-variant="segmented_control"]:focus-visible{{outline:3px solid rgba(0,119,200,.28)!important;outline-offset:2px}}
    div[data-testid="stElementContainer"]:has(.primary-nav-marker)+div[data-testid="stElementContainer"] div[role="radiogroup"]{{display:flex;gap:6px;flex-wrap:nowrap}}
    div[data-testid="stElementContainer"]:has(.primary-nav-marker)+div[data-testid="stElementContainer"] div[role="radiogroup"] label{{margin:0;padding:8px 13px;border:1px solid #B8D2E5;border-radius:7px;background:#EAF5FC;color:#102A43;font-weight:700;cursor:pointer}}
    div[data-testid="stElementContainer"]:has(.primary-nav-marker)+div[data-testid="stElementContainer"] div[role="radiogroup"] label:hover{{background:#D9F0FF;border-color:#0077C8}}
    div[data-testid="stElementContainer"]:has(.primary-nav-marker)+div[data-testid="stElementContainer"] div[role="radiogroup"] label:has(input:checked){{background:#0077C8;color:#fff;border-color:#0077C8}}
    div[data-testid="stElementContainer"]:has(.primary-nav-marker)+div[data-testid="stElementContainer"] div[role="radiogroup"] label:focus-within{{outline:3px solid rgba(0,119,200,.28);outline-offset:2px}}
    div[data-testid="stElementContainer"]:has(.primary-nav-marker)+div[data-testid="stElementContainer"] div[role="radiogroup"] label>div:first-child{{display:none}}
    .primary-nav-marker{{display:none}}
    .section-eyebrow{{color:var(--green);font-size:.72rem;font-weight:800;letter-spacing:.11em;text-transform:uppercase}} .section-title{{color:var(--navy);font-size:1.45rem;font-weight:760;letter-spacing:-.02em;margin:.18rem 0 .35rem}}
    .section-copy{{color:var(--muted);font-size:.9rem;line-height:1.55;margin:0 0 1rem}}
    .change-overview{{background:#fff;border:1px solid var(--line);border-left:4px solid var(--blue);border-radius:13px;padding:1rem 1.1rem;margin:.35rem 0 1rem}}
    .change-id{{color:var(--navy);font-size:.8rem;font-weight:800;letter-spacing:.04em}} .change-description{{color:#435268;font-size:.9rem;line-height:1.55;margin-top:.3rem}}
    div[data-testid="stVerticalBlockBorderWrapper"]{{background:#fff;border-color:var(--line)!important;border-radius:15px;box-shadow:0 5px 18px rgba(11,31,58,.045)}}
    .card-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem;margin-bottom:.55rem}} .card-step{{color:var(--muted);font-size:.7rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase}}
    .card-title{{color:var(--navy);font-size:1rem;font-weight:750;margin-top:.16rem}} .status-badge{{display:inline-flex;border-radius:999px;padding:.28rem .58rem;font-size:.68rem;font-weight:800;white-space:nowrap}}
    .status-good{{color:#12633D;background:{THEME['green_soft']}}}.status-info{{color:#185AA6;background:{THEME['blue_soft']}}}.status-warn{{color:#8B5200;background:{THEME['amber_soft']}}}.status-risk{{color:#B42318;background:{THEME['red_soft']}}}
    .card-summary{{min-height:3rem;color:#536277;font-size:.84rem;line-height:1.55;margin-bottom:.6rem}} details{{border-top:1px solid #E8EDF3;padding-top:.55rem}} details summary{{color:#40536A!important;font-size:.8rem!important;font-weight:650}}
    .assistant-panel{{background:#F8FBFF;border:1px solid #D7E5F7;border-radius:16px;padding:1.15rem 1.25rem;margin-top:1rem}} .assistant-label{{color:var(--blue);font-size:.72rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase}}
    .assistant-title{{color:var(--navy);font-size:1.08rem;font-weight:760;margin:.2rem 0 .35rem}} .narrative{{color:#3F5168;font-size:.9rem;line-height:1.65}} .event-meta{{color:var(--muted);font-size:.8rem;line-height:1.5}}
    .range-summary{{display:inline-flex;align-items:center;gap:.45rem;color:#315474;background:{THEME['blue_soft']};border:1px solid #D3E3F8;border-radius:9px;padding:.48rem .72rem;font-size:.78rem;margin:.15rem 0 1rem}}
    .ask-label{{color:var(--navy);font-size:1rem;font-weight:760;margin:.1rem 0 .15rem}} .ask-help{{color:var(--muted);font-size:.8rem;margin-bottom:.5rem}}
    .draft-flow{{color:#315474;background:{THEME['blue_soft']};border:1px solid #D3E3F8;border-radius:10px;padding:.65rem .8rem;margin:.5rem 0 1rem;font-size:.79rem;font-weight:650}}
    .field-warning{{border-left:3px solid #D59B2D;background:{THEME['amber_soft']};border-radius:7px;padding:.35rem .55rem;color:#7A5008;font-size:.72rem;margin:.15rem 0 .3rem}}
    .field-message{{border-radius:7px;padding:.36rem .55rem;font-size:.72rem;margin:.12rem 0 .42rem;line-height:1.4}}
    .field-message-error{{border-left:3px solid #D92D20;background:{THEME['red_soft']};color:#912018}}
    .field-message-review{{border-left:3px solid #D59B2D;background:{THEME['amber_soft']};color:#7A5008}}
    .finding-panel{{border:1px solid #DDE4EC;border-radius:10px;padding:.7rem .8rem;margin:.45rem 0;background:#FAFCFE}}
    .finding-field{{font-weight:750;color:#102A43;font-size:.82rem}}.finding-detail{{color:#536277;font-size:.76rem;line-height:1.45;margin-top:.22rem}}
    div[data-testid="stElementContainer"]:has(.field-marker-error)+div[data-testid="stElementContainer"] input,
    div[data-testid="stElementContainer"]:has(.field-marker-error)+div[data-testid="stElementContainer"] textarea{{border:2px solid #D92D20!important;box-shadow:0 0 0 1px rgba(217,45,32,.08)!important}}
    div[data-testid="stElementContainer"]:has(.field-marker-review)+div[data-testid="stElementContainer"] input,
    div[data-testid="stElementContainer"]:has(.field-marker-review)+div[data-testid="stElementContainer"] textarea{{border:2px solid #D59B2D!important;box-shadow:0 0 0 1px rgba(213,155,45,.08)!important}}
    div[data-testid="stForm"]{{background:#fff;border:1px solid #CBD8E6!important;border-radius:14px;padding:1rem 1.1rem;box-shadow:0 5px 18px rgba(11,31,58,.04)}}
    .stButton>button{{border-radius:9px;min-height:42px;font-weight:700;border:1px solid #C9D4E1}} .stButton>button[kind="primary"]{{background:var(--blue);border-color:var(--blue)}}
    .stSelectbox label,.stTextInput label{{color:#35465B!important;font-size:.8rem!important;font-weight:700!important}} [data-baseweb="select"]>div,.stTextInput input{{border-radius:9px!important;background:#fff!important}}
    .stAlert{{border-radius:12px}} footer{{visibility:hidden}}
    @media(max-width:720px){{.block-container{{padding:.8rem 1rem 3rem}}.user-name{{display:none}}.hero{{min-height:80px;height:auto;padding:10px 12px;border-radius:12px}}.hero p{{white-space:normal;max-width:92%}}.hero:before{{right:-1.8rem;bottom:.7rem;opacity:.24}}.hero:after{{right:-105px;opacity:.7}}}}
    </style>""", unsafe_allow_html=True)


def render_hero():
    st.markdown("""<section class="hero"><h1>Intelligent Change &amp; Access Governance</h1><p>End-to-end visibility into change quality, privileged access, execution compliance, and security investigations.</p></section>""", unsafe_allow_html=True)


def present_response(value):
    """Remove implementation labels from display while preserving stored response metadata."""
    return value.removeprefix("MOCK MODE: ")


def record_ui_assessment(feature, provider, status, started, findings=(), change_id=None, scenario=None):
    """Log exactly once from a user-action branch, never during passive rendering."""
    duration = (perf_counter() - started) * 1000
    assessment = log_assessment(feature=feature, environment=provider, final_status=status,
                                findings=findings or (), duration_ms=duration, change_id=change_id,
                                selected_scenario=scenario, actor_session_id="streamlit")
    log_performance(component_name=feature, stage=feature, agent="ARCA", duration_ms=duration,
                    assessment_id=assessment["assessment_id"], execution_id=assessment["execution_id"],
                    environment=provider)
    st.session_state.latest_assessment = assessment
    return assessment


def status_style(status):
    if status in {"VALID", "PASS", "APPROPRIATE", "POTENTIAL_MATCH"}: return "status-good"
    if status in {"REVIEW_REQUIRED", "DEVIATION_DETECTED", "OVERPRIVILEGED", "INSUFFICIENT"}: return "status-risk"
    if status in {"NEEDS_INFO", "MANUAL_REVIEW", "EVIDENCE_INCOMPLETE"}: return "status-warn"
    return "status-info"


def summary(key, value):
    status = value.get("status")
    if key == "stage1": return "The change record and requested access satisfy the applicable controls." if status in {"VALID", "PASS"} else "The change or requested access requires correction or review."
    if key == "stage2":
        if status == "APPROPRIATE": return "Requested actions and resources align with the expected change scope."
        if status in {"OVERPRIVILEGED", "RECOMMEND_LESSER_ROLE"}: return "The requested access is broader than necessary and a narrower evidenced role is available."
        if status == "NOT_AUTHORIZED": return "The approved change window is not currently active or the change is not approved."
        if status == "INSUFFICIENT_ACCESS": return "Effective grant evidence does not cover every intended operation and target."
        return "The requested access needs manual review or does not fully cover the planned work."
    if key == "stage3":
        count = sum(row.get("status") == "DEVIATION" for row in value.get("events", []))
        return f"Execution evidence contains {count} event{'s' if count != 1 else ''} that differ from the approved record." if status == "DEVIATION_DETECTED" else "Observed execution evidence is consistent with the available approved change record."
    count = len(value.get("deviations", []))
    return f"Investigation is required for {count} identified deviation{'s' if count != 1 else ''}." if status == "REVIEW_REQUIRED" else "No additional investigation was triggered."


def result_card(step, title, key, value):
    status = str(value.get("status", "NOT AVAILABLE"))
    with st.container(border=True):
        st.markdown(f"""<div class="card-head"><div><div class="card-step">{escape(step)}</div><div class="card-title">{escape(title)}</div></div><span class="status-badge {status_style(status)}">{escape(status.replace('_', ' '))}</span></div><div class="card-summary">{escape(summary(key, value))}</div>""", unsafe_allow_html=True)
        with st.expander("Technical details"): st.json(value)


def section_intro(eyebrow, title, copy):
    st.markdown(f"""<div class="section-eyebrow">{escape(eyebrow)}</div><div class="section-title">{escape(title)}</div><p class="section-copy">{escape(copy)}</p>""", unsafe_allow_html=True)


def demo_selector(feature, provider, key, label="Verified demo example"):
    """Render a reusable opt-in example picker and return its catalog record."""
    examples = demo_scenarios(feature, provider)
    choices = [""] + [item["scenario_id"] for item in examples]
    selected = st.selectbox(label, choices, key=key,
                            format_func=lambda value: "Manual entry" if not value else next(
                                item["name"] for item in examples if item["scenario_id"] == value))
    return next((item for item in examples if item["scenario_id"] == selected), None)


def apply_demo_once(key, scenario, values):
    """Populate widget state once per selection while preserving subsequent user edits."""
    scenario_id = scenario["scenario_id"] if scenario else ""
    marker = f"_applied_demo_{key}"
    if st.session_state.get(marker) != scenario_id:
        for widget_key, value in values.items():
            st.session_state[widget_key] = value
        st.session_state[marker] = scenario_id


def change_selector(label, key):
    selected = st.selectbox(label, [x["change_id"] for x in changes], key=key,
        format_func=lambda value: f"{value} · {next(c['environment'] for c in changes if c['change_id'] == value).title()}")
    return next(item for item in changes if item["change_id"] == selected)


def render_draft_result(result):
    status = result.status
    supplied, total = result.completeness["mandatory_supplied"], result.completeness["mandatory_total"]
    st.markdown(f"""<div class="change-overview"><div class="card-head"><div><div class="card-step">Stage 1 result</div><div class="card-title">Draft change validation</div></div><span class="status-badge {status_style(status)}">{escape(status.replace('_', ' '))}</span></div><div class="change-description">{supplied} of {total} mandatory requirements supplied. {'Ready for Submission' if result.ready_for_submission else 'Not ready for submission.'}</div></div>""", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.markdown("**Extracted change information**")
        st.json(result.extracted_change.model_dump(exclude={"raw_text", "conflicts", "ambiguities"}))
        st.markdown("**Expected implementation operations**")
        if result.expected_operations: st.dataframe([item.model_dump() for item in result.expected_operations], hide_index=True, width="stretch")
        else: st.caption("No explicit expected operations were extracted.")
    with right:
        st.markdown("**Missing mandatory fields**")
        if result.missing_mandatory: st.write("\n".join(f"- {field.replace('_', ' ').title()}" for field in result.missing_mandatory))
        else: st.success("All mandatory fields are present.")
        st.markdown("**Issues and recommended corrections**")
        if result.issues: st.dataframe([item.model_dump() for item in result.issues], hide_index=True, width="stretch")
        else: st.success("No validation issues identified.")
        st.markdown("**Suggested clarification questions**")
        if result.clarification_questions: st.write("\n".join(f"- {question}" for question in result.clarification_questions))
        else: st.caption("No clarification is required.")
    with st.expander("Technical JSON"): st.json(result.model_dump())


def _draft_field_before(field, findings):
    items = findings.get(field, [])
    if items:
        level = "error" if any(item["level"] == "error" for item in items) else "review"
        st.markdown(f"<span class='field-marker-{level}'></span>", unsafe_allow_html=True)


def _draft_field_after(field, findings):
    seen = set()
    for item in findings.get(field, []):
        message = item["message"]
        if message in seen: continue
        seen.add(message)
        st.markdown(f"<div class='field-message field-message-{item['level']}'>{escape(message)}</div>", unsafe_allow_html=True)


def render_smart_draft(draft, validation, generation):
    render_started = perf_counter()
    st.markdown("<div class='draft-flow'>Paste Change → Validate → View Findings → Improve Draft → Edit → Revalidate → Copy Draft</div>", unsafe_allow_html=True)
    st.markdown("### Improve Change Draft")
    st.caption("Only information supported by the original input is populated. Empty fields require an engineer's correction.")
    findings = draft_field_findings(validation)
    prefix = f"smart-{generation}-"
    with st.form(f"smart-draft-form-{generation}"):
        left, right = st.columns(2)
        with left:
            _draft_field_before("change_title", findings); title = st.text_input("Change title", value=draft.change_title, key=prefix + "title"); _draft_field_after("change_title", findings)
            number = st.text_input("Change number", value=draft.change_number, key=prefix + "number", help="Optional for draft validation.")
            _draft_field_before("business_justification", findings); justification = st.text_area("Business justification", value=draft.business_justification, key=prefix + "justification"); _draft_field_after("business_justification", findings)
            _draft_field_before("environment", findings); environment = st.text_input("Environment", value=draft.environment, key=prefix + "environment"); _draft_field_after("environment", findings)
            subscription = st.text_input("Subscription", value=draft.subscription, key=prefix + "subscription")
            resource_group = st.text_input("Resource group", value=draft.resource_group, key=prefix + "resource-group")
            _draft_field_before("resource_name_or_id", findings); resource = st.text_area("Resource name / ID", value=draft.resource_name_or_id, key=prefix + "resource"); _draft_field_after("resource_name_or_id", findings)
            _draft_field_before("implementer", findings); implementer = st.text_input("Implementer", value=draft.implementer, key=prefix + "implementer"); _draft_field_after("implementer", findings)
        with right:
            _draft_field_before("change_start", findings); start = st.text_input("Change start date/time", value=draft.change_start, key=prefix + "start"); _draft_field_after("change_start", findings)
            _draft_field_before("change_end", findings); end = st.text_input("Change end date/time", value=draft.change_end, key=prefix + "end"); _draft_field_after("change_end", findings)
            timezone = st.text_input("Timezone", value=draft.timezone, key=prefix + "timezone")
            _draft_field_before("required_role", findings); role = st.text_input("Required role", value=draft.required_role, key=prefix + "role"); _draft_field_after("required_role", findings)
            scope = st.text_input("Required access scope", value=draft.required_access_scope, key=prefix + "scope")
            _draft_field_before("implementation_steps", findings); steps = st.text_area("Implementation steps (one per line)", value="\n".join(draft.implementation_steps), key=prefix + "steps"); _draft_field_after("implementation_steps", findings)
            _draft_field_before("validation_plan", findings); validation_plan = st.text_area("Validation plan (one per line)", value="\n".join(draft.validation_plan), key=prefix + "validation"); _draft_field_after("validation_plan", findings)
            _draft_field_before("rollback_plan", findings); rollback = st.text_area("Rollback plan", value=draft.rollback_plan, key=prefix + "rollback"); _draft_field_after("rollback_plan", findings)
            _draft_field_before("expected_outcome", findings); outcome = st.text_area("Expected outcome", value=draft.expected_outcome, key=prefix + "outcome"); _draft_field_after("expected_outcome", findings)
            _draft_field_before("risk_and_impact", findings); risk = st.text_area("Risk and impact", value=draft.risk_and_impact, key=prefix + "risk"); _draft_field_after("risk_and_impact", findings)
        revalidate = st.form_submit_button("Revalidate Draft", type="primary", width="stretch")
    edited = draft.model_copy(update={
        "change_title": title, "change_number": number, "business_justification": justification,
        "environment": environment, "subscription": subscription, "resource_group": resource_group,
        "resource_name_or_id": resource, "implementer": implementer, "change_start": start,
        "change_end": end, "timezone": timezone, "required_role": role, "required_access_scope": scope,
        "implementation_steps": [x.strip() for x in steps.splitlines() if x.strip()],
        "validation_plan": [x.strip() for x in validation_plan.splitlines() if x.strip()],
        "rollback_plan": rollback, "expected_outcome": outcome, "risk_and_impact": risk,
    })
    if revalidate:
        action_started = perf_counter()
        st.session_state.smart_draft = edited
        st.session_state.smart_draft_validation = validate_draft(draft_to_extracted(edited))
        checked = st.session_state.smart_draft_validation
        record_ui_assessment("Stage 1 Revalidation", draft.provider, checked.status, action_started,
                             checked.issues, edited.change_number or None)
        LOGGER.info("draft_render status=revalidate render_ms=%.1f", (perf_counter() - render_started) * 1000)
        st.rerun()
    current = st.session_state.get("smart_draft_validation") or validation
    status = current.status
    st.markdown(f"**Overall readiness:** :{'green' if current.ready_for_submission else 'orange'}[{status.replace('_', ' ')}]")
    if current.ready_for_submission: st.success("Ready for Submission — every mandatory requirement has passed revalidation.")
    else: st.warning("Not ready for submission. Review the field-level findings and revalidate after editing.")
    if st.button("Copy Draft", key=f"copy-draft-{generation}"):
        st.session_state.smart_copy_text = servicenow_text(edited)
    if st.session_state.get("smart_copy_text"):
        st.caption("Copy-ready ServiceNow format. Use the copy control in the code block.")
        st.code(st.session_state.smart_copy_text, language=None)
    LOGGER.info("draft_render status=success render_ms=%.1f", (perf_counter() - render_started) * 1000)


def render_pim_assessment(result):
    status = result.overall_assessment
    st.markdown(f"""<div class="change-overview"><div class="card-head"><div><div class="card-step">Independent Stage 2 result</div><div class="card-title">Privileged-access recommendation</div></div><span class="status-badge {status_style(status)}">{escape(status.replace('_', ' '))}</span></div><div class="change-description">ARCA recommendation only. No PIM approval, rejection, or activation was performed.</div></div>""", unsafe_allow_html=True)
    top = st.columns(4)
    top[0].metric("Change", result.change_id or "Not identified")
    top[1].metric("PIM request", result.pim_request_id or "Pasted record")
    top[2].metric("Request status", result.request_status or "Unknown")
    top[3].metric("Activation", result.activation_status or "Unknown")
    left, right = st.columns(2)
    with left:
        st.markdown("**Control assessments**")
        st.dataframe([
            {"Control": "Principal", "Assessment": result.principal_match.get("status", "UNKNOWN")},
            {"Control": "Role", "Assessment": result.role_assessment.get("status", "UNKNOWN")},
            {"Control": "Scope", "Assessment": result.scope_assessment.get("status", "UNKNOWN")},
            {"Control": "Duration", "Assessment": result.duration_assessment.get("status", "UNKNOWN")},
            {"Control": "Justification", "Assessment": result.justification_assessment.get("status", "UNKNOWN")},
        ], hide_index=True, width="stretch")
    with right:
        st.markdown("**Least-privilege recommendation**")
        st.write(f"**Role:** {result.recommended_role or 'Manual role analysis required'}")
        st.write(f"**Scope:** {result.recommended_scope or 'Manual scope analysis required'}")
        st.write(f"**Duration:** {result.recommended_duration or 'Manual duration analysis required'}")
    if result.missing_information: st.warning("Missing information: " + ", ".join(result.missing_information))
    if result.human_review_requirements: st.info("Human review: " + " ".join(result.human_review_requirements))
    with st.expander(f"Supporting evidence references · {len(result.supporting_evidence_references)}"):
        st.write("  \n".join(f"`{reference}`" for reference in result.supporting_evidence_references) or "No evidence references available.")
    with st.expander("Technical assessment JSON"): st.json(result.model_dump())


def render_combined_pim_assessment(result):
    st.markdown(f"""<div class="change-overview"><div class="card-head"><div><div class="card-step">Combined access assessment</div><div class="card-title">Complete approved change intent</div></div><span class="status-badge {status_style(result.overall_assessment)}">{escape(result.overall_assessment.replace('_', ' '))}</span></div><div class="change-description">Overall risk: {escape(result.risk_classification)}. Privileges remain partitioned by principal.</div></div>""", unsafe_allow_html=True)
    summary = result.change_summary
    st.markdown(f"**Approved change summary — {escape(result.change_id)}**  \n{escape(summary.get('description', ''))}  \nWindow: `{escape(summary.get('start', ''))}` to `{escape(summary.get('end', ''))}`")
    st.markdown("**Combined permission coverage**")
    st.dataframe(result.task_coverage, hide_index=True, width="stretch")
    left, right = st.columns(2)
    with left:
        st.markdown("**Scope and duration concerns**")
        st.write("\n".join(f"- {item}" for item in result.scope_duration_concerns) or "No aggregate scope or duration concerns identified.")
        st.markdown("**Potential redundancies**")
        st.write("\n".join(f"- {item}" for item in result.potential_redundancies) or "No redundant grants identified.")
    with right:
        st.markdown("**Missing task coverage**")
        st.write("\n".join(f"- {item['operation']} @ {item['resource_id']}" for item in result.missing_tasks) or "Every documented task has evidence-backed coverage.")
        st.markdown("**Recommended corrections**")
        st.write("\n".join(f"- {item}" for item in result.recommended_corrections) or "No corrections recommended.")
    if result.overlapping_windows:
        with st.expander(f"Overlapping activation windows · {len(result.overlapping_windows)}"): st.dataframe(result.overlapping_windows, hide_index=True, width="stretch")
    st.markdown("**Individual PIM assessments**")
    for assessment in result.individual_assessments:
        with st.expander(f"{assessment.pim_request_id or 'Pasted request'} · {assessment.overall_assessment.replace('_', ' ')}"):
            st.json(assessment.model_dump())
    with st.expander(f"Combined evidence details · {len(result.supporting_evidence_references)}"):
        st.write("  \n".join(f"`{reference}`" for reference in result.supporting_evidence_references))


def render_snowflake_findings(groups):
    """Render evidence-derived corrections in distinct, reusable groups."""
    for heading, items in groups.items():
        st.markdown(f"**{heading}**")
        if not items:
            st.caption("No missing information identified." if heading == "Missing Information" else "None identified.")
            continue
        for item in items:
            st.markdown(
                f"<div class='finding-panel'><div class='finding-field'>{escape(str(item['field']))}</div>"
                f"<div class='finding-detail'><b>Current:</b> {escape(str(item['current_value']))}<br>"
                f"<b>Expected:</b> {escape(str(item['expected']))}<br><b>Problem:</b> {escape(str(item['problem']))}<br>"
                f"<b>Recommended correction:</b> {escape(str(item['recommendation']))}<br>"
                f"<b>Stage:</b> {escape(str(item['validation_stage']))}</div></div>", unsafe_allow_html=True)


def render_snowflake_stage1(change, result):
    """Present Snowflake change quality and focused corrections side by side."""
    left, right = st.columns([1.15, .85])
    with left:
        result_card("01 · Validate", "Change Quality", "stage1", result)
        st.markdown(f"**Validation Status:** `{result.get('status', 'UNKNOWN')}`")
        st.caption(summary("stage1", result))
    findings = {"Missing Information": [], "Validation Issues": [], "Access Risk Findings": []}
    for issue in result.get("issues", []):
        field = issue.get("field", "Change record")
        current = change.get(field) if field in change else change.get("expected") if field == "expected" else "Not provided"
        findings["Missing Information" if not current else "Validation Issues"].append({
            "field": field.replace("_", " ").title(), "current_value": current or "Not provided",
            "expected": "Complete, valid change evidence satisfying the Stage 1 policy.",
            "problem": issue.get("reason", "The value does not satisfy validation policy."),
            "recommendation": "Correct or complete this field, then rerun Stage 1 validation.",
            "validation_stage": "Stage 1",
        })
    with right:
        render_snowflake_findings(findings)


def render_snowflake_unified(change, result):
    """Render the unified Snowflake Stage 1 while preserving every independent finding."""
    result = normalize_unified_result(result)
    quality, window, role = result["change_quality"], result["window_assessment"], result["role_assessment"]
    groups = presentation_findings(change, result)
    for issue in quality.get("issues", []):
        field = issue.get("field", "Change record")
        current = change.get(field) if field in change else "Not provided"
        groups["Missing Information" if not current else "Validation Issues"].append({
            "field": field.replace("_", " ").title(), "current_value": current or "Not provided",
            "expected": "Complete and valid change-request evidence.", "problem": issue.get("reason", "Invalid value."),
            "recommendation": "Correct this field and rerun validation.", "validation_stage": "Change & Access Validation",
        })
    left, right = st.columns([1.15, .85])
    with left:
        st.markdown("### Change & Access Validation")
        result_card("01 · Validate", "Overall Result", "stage1", result)
        with st.container(border=True):
            st.markdown("**CHANGE QUALITY**")
            st.write({"Status": quality.get("status"), "Missing fields": quality.get("missing", [])})
        with st.container(border=True):
            st.markdown("**CHANGE WINDOW**")
            st.write({"Approval status": change.get("state"), "Approved start": window.get("approved_start"),
                      "Approved end": window.get("approved_end"), "Evaluation timestamp": window.get("evaluation_timestamp"),
                      "Status": window.get("status")})
            st.caption(window.get("explanation", ""))
        with st.container(border=True):
            st.markdown("**REQUESTED ROLE & ACCESS ASSESSMENT**")
            st.write({"Requested role": role.get("requested_role") or "Not provided",
                      "Description role": role.get("description_role") or "Not provided",
                      "Expected operations": role.get("intended_operations", []),
                      "Required privileges": role.get("required_privileges", []),
                      "Access status": role.get("status"), "Recommended role": role.get("recommended_role")})
            st.caption(role.get("explanation", ""))
        with st.expander("Technical Details"): st.json(result)
    with right:
        render_snowflake_findings(groups)


def render_snowflake_stage2(change, result):
    """Render both independent controls and evidence-derived corrections."""
    window, role = result["window_assessment"], result["role_assessment"]
    st.markdown("### Stage 2 — Change Window & Access Validation")
    left, right = st.columns([1.15, .85])
    with left:
        result_card("02 · Govern", "Overall Assessment", "stage2", result)
        with st.container(border=True):
            st.markdown("**CHANGE WINDOW ASSESSMENT**")
            st.write({"Approval status": change.get("state"), "Approved start": window.get("approved_start"),
                      "Approved end": window.get("approved_end"), "Evaluation timestamp": window.get("evaluation_timestamp"),
                      "Window status": window.get("status")})
            st.caption(window.get("explanation", ""))
        with st.container(border=True):
            st.markdown("**REQUESTED ROLE ASSESSMENT**")
            st.write({"Change intent": change.get("description"), "Expected operation": role.get("intended_operations"),
                      "Target object": [item.get("resource_id") for item in role.get("intended_operations", [])],
                      "Requested role": role.get("requested_role"), "Role assessment": role.get("status"),
                      "Recommended role": role.get("recommended_role")})
            st.caption(role.get("explanation", ""))
        st.markdown("**Required privileges**")
        st.dataframe(role.get("required_privileges", []), hide_index=True, width="stretch")
        with st.expander("Technical Details"):
            st.json(result)
            st.dataframe(role.get("effective_privileges", []), hide_index=True, width="stretch")
            st.write("  \n".join(f"`{item}`" for item in role.get("evidence", [])) or "No supporting grant IDs available.")
    with right:
        render_snowflake_findings(presentation_findings(change, result))


def render_snowflake_post_implementation(result):
    """Render Snowflake audit correlation without treating query text as HTML."""
    summary_data = result.get("summary", {})
    left, right = st.columns([1.05, .95])
    with left:
        st.markdown("### Investigation Summary")
        with st.container(border=True):
            st.write({"Subject": result.get("subject"), "Investigation mode": result.get("mode"),
                      "Investigation time range": result.get("investigation_window"),
                      "Overall assessment": summary_data.get("overall_assessment"),
                      "Activity events": summary_data.get("activity_count", 0),
                      "Governed operations": summary_data.get("governed_change_operations"),
                      "Matched approved changes": summary_data.get("matched_approved_changes")})
            if result.get("change"):
                change = result["change"]
                st.write({"Approved operations": change.get("expected", []),
                          "Authorized implementer": change.get("implementer"),
                          "Authorized role": change.get("snowflake_context", {}).get("requested_role")})
    with right:
        st.markdown("### Deviation Findings")
        if not result.get("findings"):
            st.success("No governed deviations were identified in the selected evidence window.")
        for finding in result.get("findings", []):
            with st.container(border=True):
                st.markdown(f"**{escape(finding['category'].replace('_', ' ').title())}** · `{escape(finding['severity'])}`")
                st.write({"Expected": finding.get("expected"), "Observed": finding.get("observed"),
                          "Evidence": finding.get("evidence"),
                          "Recommended action": finding.get("recommended_action")})
    st.markdown("### Activity Timeline")
    timeline = result.get("timeline", [])
    if result.get("mode") == "user" and timeline:
        view = st.segmented_control("Timeline filter", ["All", "Compliant", "Deviations", "Unmatched", "Failed"],
                                    default="All", key="snowflake-post-timeline-filter") or "All"
        if view == "Compliant": timeline = [row for row in timeline if "COMPLIANT_EXECUTION" in row["deviation"]]
        elif view == "Deviations": timeline = [row for row in timeline if row["deviation"] not in {"ROUTINE_ACTIVITY", "COMPLIANT_EXECUTION"}]
        elif view == "Unmatched": timeline = [row for row in timeline if row["correlation"] == "UNMATCHED"]
        elif view == "Failed": timeline = [row for row in timeline if row["execution_status"] != "SUCCESS"]
    if timeline: st.dataframe(timeline, hide_index=True, width="stretch")
    else: st.info("No activity events were found for this investigation selection.")
    for limitation in result.get("limitations", []): st.caption(f"Evidence limitation: {limitation}")
    with st.expander("Technical Details"):
        st.json(result)


inject_theme()
with st.container(border=True):
    brand_col, environment_col, navigation_col, profile_col = st.columns([2.25, 1.45, 1.25, 1.05], vertical_alignment="center")
    with brand_col:
        st.markdown(f"""<div class="brand-lockup"><div class="brand-mark">A</div><div><div class="brand-name">ARCA <span class="brand-version">{escape(ARCA_VERSION_LABEL)}</span></div><div class="brand-sub">Agentic Risk &amp; Change Assurance</div></div></div>""", unsafe_allow_html=True)
    with environment_col:
        provider_name = st.selectbox(
            "Environment",
            ["azure", "aws", "snowflake"],
            format_func=lambda name: {"azure": "Azure Environment", "aws": "AWS Environment",
                                      "snowflake": "Snowflake Environment"}[name],
            help="Select the demonstration evidence environment to review.",
        )
    with navigation_col:
        st.markdown("<span class='primary-nav-marker'></span>", unsafe_allow_html=True)
        primary_view = st.radio(
            "Primary navigation", ["ARCA", "Metrics"], horizontal=True,
            key="primary-navigation", label_visibility="collapsed",
        )
    with profile_col:
        st.markdown("""<div class="profile"><div class="profile-copy"><div class="profile-name">ARCA User</div><div class="profile-role">Assurance workspace</div></div><span class="avatar">AU</span></div>""", unsafe_allow_html=True)
if st.session_state.get("_active_evidence_provider") != provider_name:
    for stale_key in ("stage1_provider_result", "stage1_provider_key", "stage1_draft_result",
                      "stage1_draft_provider", "stage2_result", "stage2_key",
                      "analysis_result", "analysis_change_id", "analysis_provider",
                      "snowflake_unified_result", "snowflake_unified_key",
                      "_snowflake_unified_scenario", "snowflake_post_result",
                      "snowflake_post_key", "_snowflake_post_scenario"):
        st.session_state.pop(stale_key, None)
    st.session_state["_active_evidence_provider"] = provider_name
adapter = get_provider(provider_name)
capabilities = provider_capabilities(provider_name)
bundle = adapter.load_bundle()
changes, access, events = bundle["changes"], bundle["access_requests"], bundle["events"]
evidence_mode = "demonstration"
investigation_reference = evidence_reference_time(provider_name, events, evidence_mode)
with st.expander("Environment Details"):
    detail_left, detail_middle, detail_right, detail_clock = st.columns(4)
    detail_left.markdown("**Connection status**  \nDemonstration data — no live cloud connection")
    detail_middle.markdown(f"**Cloud environment**  \n{adapter.DISPLAY_NAME}")
    detail_right.markdown(f"**Evidence source**  \n{adapter.EVIDENCE_SOURCE}")
    detail_clock.markdown(f"**Investigation reference**  \n{utc_label(investigation_reference)}")
render_hero()
if primary_view == "Metrics":
    render_observability()
    st.markdown("<p style='text-align:center;color:#7A8798;font-size:.72rem;margin-top:2.5rem'>ARCA Â· Demonstration evidence Â· Not a security enforcement system</p>", unsafe_allow_html=True)
    st.stop()

tab1, tab2, tab3 = st.tabs(["Change Lifecycle", "Undocumented Changes", "Ask ARCA"])

with tab1:
    lifecycle_copy = ("Validate change consistency, confirm the approved window is active, and assess the requested Snowflake role."
                      if provider_name == "snowflake" else
                      "Validate a draft before submission, assess privileges, verify execution evidence, or run the complete assurance workflow.")
    section_intro("Independent assurance stages", "Change Lifecycle", lifecycle_copy)
    stage1_label = "Change & Access Validation" if provider_name == "snowflake" else "Stage 1 — Validate Change"
    lifecycle_options = [stage1_label]
    if provider_name == "snowflake" and "post_implementation" in capabilities:
        lifecycle_options.append("Post-Implementation Validation")
    stage2_label = "Stage 2 — Access Validation" if provider_name == "snowflake" else "Stage 2 — Validate Privileges"
    if "stage2" in capabilities: lifecycle_options.append(stage2_label)
    if "stage3" in capabilities: lifecycle_options.append("Stage 3 — Verify Execution")
    if "lifecycle" in capabilities: lifecycle_options.append("Full Lifecycle Assessment")
    lifecycle_mode = st.segmented_control(
        "Assessment", lifecycle_options, default=stage1_label,
        selection_mode="single", key=f"assessment-stage-{provider_name}",
    ) or stage1_label
    run_analysis, cid = False, None
    if provider_name == "snowflake" and lifecycle_mode == stage1_label:
        scenarios = bundle.get("demo_scenarios", [])
        if not scenarios:
            st.error("Snowflake demo scenarios could not be loaded. Verify data/snowflake/demo_scenarios.json.")
            st.stop()
        scenario_choices = [""] + [item["scenario_id"] for item in scenarios]
        selected_scenario_id = st.selectbox(
            "Verified Demo Example", scenario_choices, key="snowflake-unified-demo",
            format_func=lambda value: "Manual Entry" if not value else next(
                item["scenario_name"] for item in scenarios if item["scenario_id"] == value),
        )
        selected_scenario = next((item for item in scenarios if item["scenario_id"] == selected_scenario_id), None)
        if st.session_state.get("_snowflake_unified_scenario") != selected_scenario_id:
            if selected_scenario:
                st.session_state["snowflake-unified-change"] = selected_scenario["change_id"]
            st.session_state.pop("snowflake_unified_result", None)
            st.session_state.pop("snowflake_unified_key", None)
            st.session_state["_snowflake_unified_scenario"] = selected_scenario_id
        change = change_selector("Approved Change Record", "snowflake-unified-change")
        role = change.get("snowflake_context", {}).get("requested_role") or "Not provided"
        operations = change.get("expected") or []
        st.markdown(f"""<div class="change-overview"><div class="change-id">{escape(change['change_id'])} · {escape(change.get('state', '').upper())}</div><div class="change-description">{escape(change.get('description') or 'No description supplied')}</div></div>""", unsafe_allow_html=True)
        evaluation_time = selected_scenario["evaluation_timestamp"] if selected_scenario else None
        if evaluation_time: st.markdown(f"**Demo Evaluation Time:** `{escape(utc_label(parse_utc(evaluation_time)))}`")
        else: st.caption("Evaluation time: current UTC time (manual mode)")
        st.write({"Requested role": role, "Approved window": f"{change.get('start') or 'Not provided'} to {change.get('end') or 'Not provided'}",
                  "Expected operation": [item.get("operation") for item in operations],
                  "Target object": [item.get("resource_id") for item in operations]})
        with processing_action(st, "Run Validation", "run-snowflake-unified", "Validating change...") as run_validation:
            if run_validation:
                action_started = perf_counter()
                context = {**bundle, "evaluation_time": evaluation_time} if evaluation_time else bundle
                try:
                    result1 = adapter.evaluate_stage1(change, context)
                    st.session_state.snowflake_unified_result = result1
                    st.session_state.snowflake_unified_key = (
                        change["change_id"], selected_scenario_id, UNIFIED_RESULT_SCHEMA_VERSION
                    )
                    record_ui_assessment("Stage 1 Snowflake Change & Access Validation", provider_name, result1["status"],
                                         action_started, result1["change_quality"].get("issues", []),
                                         change["change_id"], selected_scenario_id or None)
                except Exception as exc:
                    LOGGER.exception("Snowflake unified validation failed")
                    st.error(f"Snowflake validation could not be completed ({type(exc).__name__}). Review the application logs and retry.")
        current_result_key = (change["change_id"], selected_scenario_id, UNIFIED_RESULT_SCHEMA_VERSION)
        if st.session_state.get("snowflake_unified_key") == current_result_key:
            render_snowflake_unified(change, st.session_state.snowflake_unified_result)
    elif provider_name == "snowflake" and lifecycle_mode == "Post-Implementation Validation":
        post_scenarios = bundle.get("post_implementation_scenarios", [])
        if not post_scenarios:
            st.error("Snowflake post-implementation scenarios could not be loaded. Verify data/snowflake/post_implementation_scenarios.json.")
            st.stop()
        post_choices = [""] + [item["scenario_id"] for item in post_scenarios]
        selected_post_id = st.selectbox(
            "Verified Demo Example", post_choices, key="snowflake-post-demo",
            format_func=lambda value: "Manual Entry" if not value else next(
                item["scenario_name"] for item in post_scenarios if item["scenario_id"] == value),
        )
        selected_post = next((item for item in post_scenarios if item["scenario_id"] == selected_post_id), None)
        if st.session_state.get("_snowflake_post_scenario") != selected_post_id:
            st.session_state["snowflake-post-mode"] = "By User ID / Email" if selected_post and selected_post["investigation_mode"] == "user" else "By Change Number"
            if selected_post and selected_post.get("change_id"):
                st.session_state["snowflake-post-change"] = selected_post["change_id"]
            if selected_post and selected_post.get("user_identity"):
                st.session_state["snowflake-post-user"] = selected_post["user_identity"]
            st.session_state.pop("snowflake_post_result", None)
            st.session_state.pop("snowflake_post_key", None)
            st.session_state["_snowflake_post_scenario"] = selected_post_id
        st.markdown("**INVESTIGATION MODE**")
        post_mode = st.radio("Investigation mode", ["By Change Number", "By User ID / Email"], horizontal=True,
                             key="snowflake-post-mode", label_visibility="collapsed")
        if selected_post:
            st.markdown(f"**Demo Evaluation Time:** `{escape(utc_label(parse_utc(selected_post['evaluation_timestamp'])))}`")
        if post_mode == "By Change Number":
            change_ids = [item["change_id"] for item in changes]
            selected_change_id = st.selectbox("Change Number", change_ids, key="snowflake-post-change")
            selected_change = next(item for item in changes if item["change_id"] == selected_change_id)
            with st.expander("Approved Change Record"):
                st.json(selected_change)
            with processing_action(st, "Run Post-Implementation Validation", "run-snowflake-post-change",
                                   "Processing Snowflake audit evidence...") as run_post:
                if run_post:
                    kwargs = ({"evaluation_time": selected_post["evaluation_timestamp"],
                               "query_ids": selected_post["evidence_query_ids"]} if selected_post else {})
                    st.session_state.snowflake_post_result = adapter.evaluate_post_implementation_by_change(selected_change_id, bundle, persist_output=True, **kwargs)
                    st.session_state.snowflake_post_key = ("change", selected_change_id, selected_post_id)
            post_key = ("change", selected_change_id, selected_post_id)
        else:
            user_identifier = st.text_input("User Identifier", key="snowflake-post-user",
                                            placeholder="engineer@example.invalid")
            time_options = {"Last 1 Day": 1, "Last 7 Days": 7, "Last 10 Days": 10,
                            "Last 15 Days": 15, "Last 30 Days": 30, "Custom Date Range": None}
            time_label = st.selectbox("Time Range", list(time_options), index=2, key="snowflake-post-range")
            custom_start = custom_end = None
            if time_label == "Custom Date Range":
                start_col, end_col = st.columns(2)
                custom_start = start_col.date_input("Start date", key="snowflake-post-start")
                custom_end = end_col.date_input("End date", key="snowflake-post-end")
            with processing_action(st, "Investigate User Activity", "run-snowflake-post-user",
                                   "Correlating user activity...", disabled=not bool(user_identifier.strip())) as run_user:
                if run_user:
                    kwargs = {"days": time_options[time_label] or 10}
                    if selected_post:
                        kwargs.update({"evaluation_time": selected_post["evaluation_timestamp"],
                                       "query_ids": selected_post["evidence_query_ids"],
                                       "days": selected_post.get("window_days", kwargs["days"])})
                    elif custom_start and custom_end:
                        kwargs.update({"start": f"{custom_start.isoformat()}T00:00:00Z",
                                       "end": f"{custom_end.isoformat()}T00:00:00Z"})
                    st.session_state.snowflake_post_result = adapter.evaluate_post_implementation_by_user(user_identifier, bundle, persist_output=True, **kwargs)
                    st.session_state.snowflake_post_key = ("user", user_identifier, selected_post_id)
            post_key = ("user", user_identifier, selected_post_id)
        if st.session_state.get("snowflake_post_key") == post_key:
            render_snowflake_post_implementation(st.session_state.snowflake_post_result)
    elif lifecycle_mode == "Stage 1 — Validate Change":
        stage1_demo = demo_selector("stage1", provider_name, "stage1-demo")
        apply_demo_once("stage1", stage1_demo, {
            "stage1-input-mode": stage1_demo["inputs"]["mode"] if stage1_demo else "Existing Change",
            "stage1-details": stage1_demo_text(stage1_demo["inputs"]["variant"]) if stage1_demo else "",
            "stage1-environment": "", "stage1-implementer": "", "stage1-start": "",
            "stage1-resource": "", "stage1-end": "",
        })
        input_mode = st.radio("Change input", ["Existing Change", "Paste Change Details"], horizontal=True, key="stage1-input-mode")
        draft_result = None
        if input_mode == "Existing Change":
            change = change_selector("Existing change record", "stage1-existing-change")
            if provider_name == "snowflake":
                st.markdown(f"""<div class="change-overview"><div class="change-id">{escape(change['change_id'])} · {escape(change.get('state', '').upper())}</div><div class="change-description">{escape(change.get('description') or 'No description supplied')}</div></div>""", unsafe_allow_html=True)
                with st.expander("Selected Snowflake change details"): st.json(change)
            st.caption("Stage 1 runs without PIM approval or execution evidence.")
            with processing_action(st, "Validate change", "validate-existing", "Validating change...") as validate_existing:
                if validate_existing:
                    action_started = perf_counter()
                    extraction_started = perf_counter()
                    if provider_name == "snowflake":
                        provider_result = adapter.evaluate_stage1(change, bundle)
                        st.session_state.stage1_provider_result = provider_result
                        st.session_state.stage1_provider_key = (provider_name, change.get("change_id"))
                    else:
                        draft_result = validate_draft(extract_existing_change(change, provider_name))
                    LOGGER.info("change_extraction provider=deterministic status=success extraction_ms=%.1f",
                                (perf_counter() - extraction_started) * 1000)
                    result_status = provider_result["status"] if provider_name == "snowflake" else draft_result.status
                    result_issues = provider_result.get("issues", ()) if provider_name == "snowflake" else draft_result.issues
                    record_ui_assessment("Stage 1 Validation", provider_name, result_status, action_started,
                                         result_issues, change.get("change_id"))
        else:
            details = st.text_area("Change details", height=260, key="stage1-details", placeholder="Paste the ServiceNow description, implementation plan, or structured change record.")
            c1, c2 = st.columns(2)
            with c1:
                manual_environment = st.text_input("Environment (optional)", key="stage1-environment")
                manual_implementer = st.text_input("Implementer (optional)", key="stage1-implementer")
                manual_start = st.text_input("Start date/time with timezone (optional)", key="stage1-start")
            with c2:
                manual_resource = st.text_input("Resource identifier (optional)", key="stage1-resource")
                manual_end = st.text_input("End date/time with timezone (optional)", key="stage1-end")
                st.caption("Draft details are not saved to the datasets.")
            with processing_action(st, "Validate draft", "validate-pasted", "Validating change...") as validate_pasted:
                if validate_pasted:
                    action_started = perf_counter()
                    try:
                        extraction_started = perf_counter()
                        extracted = get_extractor().extract(details, provider_name, {"environment": manual_environment, "implementer": manual_implementer, "target_resources": manual_resource, "start": manual_start, "end": manual_end})
                        draft_result = validate_draft(extracted)
                        LOGGER.info("change_extraction provider=%s status=success extraction_ms=%.1f",
                                    extracted.extraction_mode, (perf_counter() - extraction_started) * 1000)
                        record_ui_assessment("Stage 1 Validation", provider_name, draft_result.status, action_started,
                                             draft_result.issues, extracted.change_id)
                    except Exception as exc: st.error(f"Change extraction is unavailable ({type(exc).__name__}). No model output was used.")
        if draft_result:
            st.session_state.stage1_draft_result, st.session_state.stage1_draft_provider = draft_result, provider_name
            st.session_state.stage1_original_input = draft_result.extracted_change.raw_text
            st.session_state.smart_draft_generation = st.session_state.get("smart_draft_generation", 0) + 1
            for smart_key in ("smart_draft", "smart_draft_validation", "smart_copy_text", "smart_draft_refinement"):
                st.session_state.pop(smart_key, None)
        if provider_name == "snowflake" and input_mode == "Existing Change" and st.session_state.get("stage1_provider_key") == (provider_name, change.get("change_id")):
            render_snowflake_stage1(change, st.session_state.stage1_provider_result)
        if st.session_state.get("stage1_draft_provider") == provider_name and st.session_state.get("stage1_draft_result"):
            current_result = st.session_state.stage1_draft_result
            render_draft_result(current_result)
            with processing_action(st, "Improve Draft", "improve-stage1-draft", "Improving draft...") as improve_requested:
                if improve_requested:
                    action_started = perf_counter()
                    assessment_id = new_id("assessment")
                    with telemetry_context(environment=provider_name, feature="Improve Draft", stage="Stage 1",
                                           agent_name="Smart Draft Assistant", assessment_id=assessment_id,
                                           change_id=current_result.extracted_change.change_id):
                        outcome = improve_draft_with_status(current_result.extracted_change)
                    st.session_state.smart_draft = outcome.draft
                    st.session_state.smart_draft_validation = current_result
                    st.session_state.smart_copy_text = ""
                    st.session_state.smart_draft_refinement = {
                        "llm_used": outcome.llm_used, "cache_hit": outcome.cache_hit,
                        "status": outcome.status, "timings": outcome.timings,
                    }
                    if not outcome.llm_used and outcome.status == "fallback":
                        st.warning("AI refinement was unavailable. The editable draft below was created deterministically from the extracted information; no LLM-generated wording is shown.")
                    record_ui_assessment("Improve Draft", provider_name, outcome.status.upper(), action_started,
                                         (), current_result.extracted_change.change_id)
            refinement = st.session_state.get("smart_draft_refinement")
            if refinement and refinement.get("cache_hit"):
                st.caption("A previously successful refinement for this exact draft and model configuration was reused.")
            if st.session_state.get("smart_draft"):
                render_smart_draft(st.session_state.smart_draft, st.session_state.get("smart_draft_validation") or current_result, st.session_state.get("smart_draft_generation", 0))
    elif lifecycle_mode == stage2_label:
        st.caption("Runs independently using the selected privileged-access evidence and its referenced change. Stage 1 and Stage 3 are not executed.")
        if provider_name == "snowflake":
            stage2_demo = demo_selector("snowflake_stage2", provider_name, "snowflake-stage2-demo", "Verified Demo Example")
            demo_id = stage2_demo["scenario_id"] if stage2_demo else ""
            if st.session_state.get("_snowflake_stage2_scenario") != demo_id:
                if stage2_demo:
                    st.session_state["snowflake-stage2-change"] = stage2_demo["associated_change_number"]
                    st.session_state["snowflake-demo-evaluation-time"] = stage2_demo["inputs"]["evaluation_time"]
                else:
                    st.session_state.pop("snowflake-demo-evaluation-time", None)
                st.session_state.pop("stage2_result", None)
                st.session_state.pop("stage2_key", None)
                st.session_state["_snowflake_stage2_scenario"] = demo_id
            change = change_selector("Approved Change Record", "snowflake-stage2-change")
            st.markdown(f"""<div class="change-overview"><div class="change-id">{escape(change['change_id'])} · {escape(change.get('state', '').upper())}</div><div class="change-description">{escape(change.get('description') or 'No description supplied')}</div></div>""", unsafe_allow_html=True)
            context = bundle
            if stage2_demo:
                demo_time = stage2_demo["inputs"]["evaluation_time"]
                st.markdown(f"**Demo Evaluation Time:** `{escape(demo_time)}`")
                context = {**bundle, "evaluation_time": demo_time}
            else:
                st.caption("Evaluation time: current UTC time (manual mode)")
            role = change.get("snowflake_context", {}).get("requested_role") or "Not provided"
            operations = change.get("expected") or []
            st.write({"Requested role": role, "Approved window": f"{change.get('start') or 'Not provided'} to {change.get('end') or 'Not provided'}",
                      "Expected operation": [item.get("operation") for item in operations],
                      "Target object": [item.get("resource_id") for item in operations]})
            if st.button("Run Stage 2 Validation", type="primary"):
                action_started = perf_counter()
                result2 = adapter.evaluate_stage2(change, {}, context)
                st.session_state.stage2_result = result2
                st.session_state.stage2_key = (provider_name, change["change_id"], demo_id)
                findings = [result2["window_assessment"], result2["role_assessment"]]
                record_ui_assessment("Stage 2 Snowflake Validation", provider_name, result2["status"],
                                     action_started, findings, change["change_id"])
            if st.session_state.get("stage2_key") == (provider_name, change["change_id"], demo_id):
                render_snowflake_stage2(change, st.session_state.stage2_result)
        elif provider_name == "azure":
            pim_mode = st.radio("PIM input", ["Search by Change Number", "Search by User ID", "Paste PIM Records"], horizontal=True, key="stage2-input-mode")
            feature = {"Search by Change Number": "stage2_change", "Search by User ID": "stage2_user", "Paste PIM Records": "stage2_paste"}[pim_mode]
            stage2_demo = demo_selector(feature, provider_name, f"stage2-demo-{feature}")
            if pim_mode == "Search by Change Number":
                apply_demo_once(feature, stage2_demo, {"stage2-change-number": stage2_demo["associated_change_number"] if stage2_demo else ""})
            elif pim_mode == "Search by User ID":
                apply_demo_once(feature, stage2_demo, {
                    "stage2-user-id": stage2_demo["user_identity"] if stage2_demo else "",
                    "stage2-access-state": stage2_demo["inputs"].get("access_state", "All") if stage2_demo else "All",
                    "stage2-user-change": stage2_demo["associated_change_number"] if stage2_demo else "",
                })
            else:
                apply_demo_once(feature, stage2_demo, {
                    "stage2-pasted-records": pim_records_json(stage2_demo, bundle) if stage2_demo else "",
                    "pasted-change-number": stage2_demo["associated_change_number"] if stage2_demo else "",
                })
            records, selected_change_id = [], ""
            if pim_mode == "Search by Change Number":
                selected_change_id = st.text_input("Change number", key="stage2-change-number", placeholder="CHG-AZ-2021").strip().upper()
                if st.button("Retrieve all PIM requests", type="primary"):
                    raw_matches = find_pim_requests_by_change(bundle, selected_change_id)
                    st.session_state.stage2_multi_records = [record_from_evidence(item) for item in raw_matches]
                    st.session_state.stage2_multi_change = selected_change_id
                    st.session_state.pop("stage2_combined_result", None)
            elif pim_mode == "Search by User ID":
                search_col, filter_col = st.columns([3, 1])
                with search_col: identity_query = st.text_input("Azure UPN or Entra object ID", key="stage2-user-id")
                with filter_col: activation_filter = st.selectbox("Access state", ["All", "Active", "Pending", "Scheduled"], key="stage2-access-state")
                selected_change_id = st.text_input("Change number filter (optional)", key="stage2-user-change").strip().upper()
                if st.button("Search PIM requests", type="primary"):
                    raw_matches = find_pim_requests(bundle, identity_query, activation_filter, investigation_reference)
                    if selected_change_id:
                        allowed = {item.get("pim_request_id") for item in find_pim_requests_by_change(bundle, selected_change_id)}
                        raw_matches = [item for item in raw_matches if item.get("pim_request_id") in allowed]
                    st.session_state.stage2_multi_records = [record_from_evidence(item) for item in raw_matches]
                    matched_changes = {record.change_id for record in st.session_state.stage2_multi_records if record.change_id}
                    st.session_state.stage2_multi_change = selected_change_id or (next(iter(matched_changes)) if len(matched_changes) == 1 else "")
                    st.session_state.pop("stage2_combined_result", None)
            else:
                pasted_pim = st.text_area("PIM records", height=300, key="stage2-pasted-records", placeholder="Paste one JSON object, a JSON array of PIM requests, or one human-readable labeled record.")
                selected_change_id = st.text_input("Change number", key="pasted-change-number").strip().upper()
                if st.button("Parse PIM records", type="primary"):
                    try:
                        parsed = parse_pim_records(pasted_pim)
                        st.session_state.stage2_multi_records = parsed
                        parsed_changes = {record.change_id for record in parsed if record.change_id}
                        st.session_state.stage2_multi_change = selected_change_id or (next(iter(parsed_changes)) if len(parsed_changes) == 1 else "")
                        st.session_state.pop("stage2_combined_result", None)
                    except Exception as exc: st.error(f"PIM records could not be parsed ({type(exc).__name__}). No model output was used.")
            records = st.session_state.get("stage2_multi_records", [])
            selected_change_id = st.session_state.get("stage2_multi_change", selected_change_id)
            change_record = next((item for item in changes if item.get("change_id") == selected_change_id), None)
            if change_record:
                st.markdown(f"""<div class="change-overview"><div class="change-id">{escape(change_record['change_id'])} · {escape(change_record.get('state', '').upper())}</div><div class="change-description">{escape(change_record.get('description', ''))}</div></div>""", unsafe_allow_html=True)
            if records:
                st.dataframe([{"PIM request": item.pim_request_id, "Change": item.change_id, "Principal": item.principal_name or item.principal_id, "Role": item.role_name, "Scope": item.scope, "Reference source": item.reference_source} for item in records], hide_index=True, width="stretch")
                ambiguous = [f"{item.pim_request_id}: {' '.join(item.ambiguous)}" for item in records if item.ambiguous]
                if ambiguous: st.warning("Reference review required: " + " ".join(ambiguous))
                if not selected_change_id: st.warning("Select a change-number filter before combining requests associated with different or missing change references.")
                with processing_action(st, "Validate All PIM Requests", "validate-all-pim", "Evaluating privileges...",
                                       disabled=not bool(selected_change_id)) as validate_all_pim:
                    if validate_all_pim:
                        action_started = perf_counter()
                        st.session_state.stage2_combined_result = assess_combined_pim(selected_change_id, records, bundle, investigation_reference)
                        combined = st.session_state.stage2_combined_result
                        record_ui_assessment("Stage 2 PIM Validation", provider_name, combined.overall_assessment,
                                             action_started, getattr(combined, "individual_assessments", ()), selected_change_id)
                if st.session_state.get("stage2_combined_result"):
                    render_combined_pim_assessment(st.session_state.stage2_combined_result)
            elif selected_change_id or st.session_state.get("stage2_multi_change"):
                st.info("No associated PIM requests were found in the available evidence.")
        else:
            change = change_selector("Validated change", "stage2-change")
            with processing_action(st, "Validate privileges", f"validate-privileges-{provider_name}", "Evaluating privileges...") as validate_privileges:
                if validate_privileges:
                    action_started = perf_counter()
                    st.session_state.stage2_result = adapter.evaluate_stage2(change, adapter.access_for_change(bundle, change["change_id"]), bundle)
                    st.session_state.stage2_key = (provider_name, change["change_id"])
                    result2 = st.session_state.stage2_result
                    record_ui_assessment("Stage 2 PIM Validation", provider_name, result2.get("status", "UNKNOWN"),
                                         action_started, result2.get("issues", ()), change["change_id"])
            if st.session_state.get("stage2_key") == (provider_name, change["change_id"]): result_card("02 · Govern", "Access Governance", "stage2", st.session_state.stage2_result)
    elif lifecycle_mode == "Stage 3 — Verify Execution":
        stage3_demo = demo_selector("stage3", provider_name, "stage3-demo")
        apply_demo_once("stage3", stage3_demo, {"stage3-change": stage3_demo["associated_change_number"] if stage3_demo else changes[0]["change_id"]})
        change = change_selector("Change ID", "stage3-change")
        with processing_action(st, "Verify execution", f"verify-execution-{provider_name}", "Verifying execution evidence...") as verify_execution:
            if verify_execution:
                action_started = perf_counter()
                st.session_state.stage3_result = adapter.evaluate_stage3(change, events, bundle)
                st.session_state.stage3_key = (provider_name, change["change_id"])
                result3 = st.session_state.stage3_result
                record_ui_assessment("Stage 3 Execution Verification", provider_name, result3.get("status", "UNKNOWN"),
                                     action_started, result3.get("events", ()), change["change_id"])
        if st.session_state.get("stage3_key") == (provider_name, change["change_id"]): result_card("03 · Correlate", "Execution Audit", "stage3", st.session_state.stage3_result)
    else:
        automated_demo = demo_selector("automated_investigation", provider_name, "automated-demo")
        apply_demo_once("automated", automated_demo, {"full-lifecycle-change": automated_demo["associated_change_number"] if automated_demo else changes[0]["change_id"]})
        selector, action = st.columns([3, 1], vertical_alignment="bottom")
        with selector: change = change_selector("Approved change record", "full-lifecycle-change")
        cid = change["change_id"]
        with action:
            with processing_action(st, "Run lifecycle analysis", f"run-lifecycle-{provider_name}",
                                   "Running assurance workflow...", width="stretch") as run_analysis:
                if run_analysis:
                    action_started = perf_counter()
                    request = adapter.access_for_change(bundle, cid)
                    st.session_state.analysis_result = build().invoke({"provider": provider_name, "change": change, "access_request": request, "events": events, "context": bundle})
                    st.session_state.analysis_change_id = cid
                    st.session_state.analysis_provider = provider_name
                    lifecycle = st.session_state.analysis_result
                    lifecycle_findings = [item for name in ("stage1", "stage2", "stage3", "investigation") for item in ([lifecycle.get(name)] if lifecycle.get(name) else [])]
                    record_ui_assessment("Full Lifecycle Assessment", provider_name,
                                         lifecycle.get("investigation", lifecycle.get("stage3", {})).get("status", "COMPLETE"),
                                         action_started, lifecycle_findings, cid)
        st.markdown(f"""<div class="change-overview"><div class="change-id">{escape(cid)} · {escape(change['environment'].upper())}</div><div class="change-description">{escape(change['description'])}</div></div>""", unsafe_allow_html=True)
    result = st.session_state.get("analysis_result")
    if result and st.session_state.get("analysis_change_id") == cid and st.session_state.get("analysis_provider") == provider_name:
        left, right = st.columns(2)
        cards = [("01 · Validate", "Change Quality", "stage1"), ("02 · Govern", "Access Governance", "stage2"), ("03 · Correlate", "Execution Audit", "stage3"), ("04 · Investigate", "AI Investigation", "investigation")]
        for i, (step, title, key) in enumerate(cards):
            if key in result:
                with (left if i % 2 == 0 else right): result_card(step, title, key, result[key])
        st.markdown(f"""<div class="assistant-panel"><div class="assistant-label">ARCA Investigation Assistant</div><div class="assistant-title">Audit narrative for {escape(cid)}</div><div class="narrative">{escape(result.get('narrative', 'No narrative was generated.'))}</div></div>""", unsafe_allow_html=True)
        st.text_input("Ask about this assessment", placeholder="Search the evidence or enter a follow-up question…", help="This field does not submit queries to an external model.")
    elif lifecycle_mode == "Full Lifecycle Assessment": st.info("Choose a change record and run the analysis to view the control assessment.")
    feedback_controls(st.session_state.get("latest_assessment"), "lifecycle")

with tab2:
    section_intro("Continuous visibility", "Snowflake Activity Investigation" if provider_name == "snowflake" else "Undocumented Changes", "Governed activity without a sufficiently correlated approved change is a review signal, not proof of unauthorized behavior." if provider_name == "snowflake" else "Successful write events without an exact match in the available approved synthetic records. An unmatched event is a review signal, not proof of unauthorized activity.")
    sf_scope = sf_scope_value = None
    if provider_name == "snowflake":
        sf_scope = st.segmented_control("Investigation scope", ["All governed activities", "Specific user", "Specific role"], default="All governed activities", key="snowflake-agent4-scope")
        if sf_scope == "Specific user": sf_scope_value = st.text_input("Snowflake user", key="snowflake-agent4-user")
        elif sf_scope == "Specific role": sf_scope_value = st.text_input("Snowflake role", key="snowflake-agent4-role")
    undocumented_demo = demo_selector("undocumented", provider_name, f"undocumented-demo-{provider_name}")
    apply_demo_once(f"undocumented-{provider_name}", undocumented_demo, {
        f"undocumented-range-{provider_name}": undocumented_demo["inputs"]["time_range"] if undocumented_demo else "Last 7 Days"
    })
    selected_range = st.segmented_control(
        "Time range",
        options=list(TIME_RANGES),
        selection_mode="single",
        key=f"undocumented-range-{provider_name}",
    ) or "Last 7 Days"
    evidence_window = filter_evidence_window(provider_name, changes, events, selected_range,
                                              mode=evidence_mode, reference_time=investigation_reference)
    if provider_name == "snowflake":
        with processing_action(st, "Run Investigation", "run-undocumented-snowflake",
                               "Correlating Snowflake audit evidence...") as run_undocumented:
            undocumented_started = perf_counter() if run_undocumented else None
            undocumented = adapter.find_unmatched(evidence_window["changes"], evidence_window["events"], bundle)
    else:
        run_undocumented = st.button("Analyze selected period", type="primary", key=f"run-undocumented-{provider_name}")
        undocumented_started = perf_counter() if run_undocumented else None
        undocumented = adapter.find_unmatched(evidence_window["changes"], evidence_window["events"], bundle)
    if provider_name == "snowflake" and sf_scope_value:
        field = "actor" if sf_scope == "Specific user" else "role"
        undocumented = [item for item in undocumented if item.get(field, "").lower() == sf_scope_value.lower()]
    window_status = undocumented_window_status(evidence_window["events"], undocumented)
    if run_undocumented:
        record_ui_assessment("Undocumented Changes", provider_name, window_status,
                             undocumented_started, undocumented)
    st.markdown(
        f"<div class='range-summary'><strong>{escape(selected_range)}</strong><span>{escape(utc_label(evidence_window['start']))} — {escape(utc_label(evidence_window['end']))}</span></div>",
        unsafe_allow_html=True,
    )
    m1, m2, m3 = st.columns([1, 1, 2]); m1.metric("Events for review", len(undocumented)); m2.metric("Activity evaluated", len(evidence_window["events"])); m3.metric("Evidence source", adapter.DISPLAY_NAME)
    if window_status == "UNMATCHED_CHANGES":
        source_by_id = {(item["event_data_id"] if provider_name == "azure" else item["query_id"] if provider_name == "snowflake" else item["eventID"]): item for item in evidence_window["events"]}
        columns = st.columns(2)
        for i, event in enumerate(undocumented):
            source = source_by_id.get(event["event_id"], {})
            actor = source.get("caller") if provider_name == "azure" else source.get("user_name") if provider_name == "snowflake" else source.get("actor")
            with columns[i % 2]:
                with st.container(border=True):
                    st.markdown(f"""<div class="card-head"><div><div class="card-step">Event evidence</div><div class="card-title">{escape(event['operation'])}</div></div><span class="status-badge status-warn">REVIEW</span></div><div class="event-meta"><strong>Event ID</strong><br>{escape(event['event_id'])}<br><br><strong>Actor</strong><br>{escape(actor or 'Not recorded')}</div>""", unsafe_allow_html=True)
                    with st.expander("Technical details"): st.json(event)
    elif window_status == "NO_ACTIVITY":
        st.info("No activity recorded during the selected period.")
    elif window_status == "NO_UNMATCHED_CHANGES":
        st.info("No undocumented changes identified during the selected period.")
    else:
        st.warning("Insufficient evidence is available to evaluate undocumented changes for the selected period.")
    feedback_controls(st.session_state.get("latest_assessment"), "undocumented")

with tab3:
    title_col, reset_col = st.columns([4, 1], vertical_alignment="bottom")
    with title_col:
        section_intro("Conversational investigation", "Ask ARCA — Cloud Investigation Assistant", "Investigate cloud resources, access issues, privileged activities, and infrastructure changes using natural language.")
    with reset_col:
        reset_requested = st.button("Reset Conversation", width="stretch")

    if "investigation_agent" not in st.session_state or st.session_state.get("investigation_provider") != provider_name:
        investigation_tools = (SnowflakeInvestigationTools(bundle=bundle, evidence_mode=evidence_mode)
                               if provider_name == "snowflake" else
                               InvestigationTools(bundle=bundle, provider=provider_name, evidence_mode=evidence_mode))
        st.session_state.investigation_agent = InvestigationAgent(tools=investigation_tools)
        st.session_state.investigation_provider = provider_name
        st.session_state.investigation_thread = "streamlit-0"
        st.session_state.investigation_turns = []
        st.session_state.investigation_generation = 0
        st.session_state.investigation_agent_context = {}
    if reset_requested:
        st.session_state.investigation_generation += 1
        st.session_state.investigation_thread = f"streamlit-{st.session_state.investigation_generation}"
        st.session_state.investigation_turns = []
        st.rerun()

    if provider_name == "snowflake":
        ask_scenarios = bundle.get("investigation_scenarios", [])
        if not ask_scenarios:
            st.error("Snowflake investigation scenarios could not be loaded. Verify data/snowflake/investigation_scenarios.json.")
            st.stop()
        ask_choice = st.selectbox("Verified Demo Example", [""] + [item["scenario_id"] for item in ask_scenarios],
                                  key="ask-demo-snowflake", format_func=lambda value: "Manual Entry" if not value else next(item["scenario_name"] for item in ask_scenarios if item["scenario_id"] == value))
        ask_demo = next((item for item in ask_scenarios if item["scenario_id"] == ask_choice), None)
        if st.session_state.get("_snowflake_ask_scenario") != ask_choice:
            st.session_state["ask-arca-question"] = ask_demo["investigation_prompt"] if ask_demo else ""
            st.session_state.investigation_turns = []
            st.session_state["_snowflake_ask_scenario"] = ask_choice
            if ask_demo: st.session_state.investigation_agent_context = {"evaluation_time": ask_demo["evaluation_timestamp"]}
    else:
        ask_demo = demo_selector("ask_arca", provider_name, f"ask-demo-{provider_name}")
        apply_demo_once(f"ask-{provider_name}", ask_demo, {"ask-arca-question": ask_demo["inputs"]["question"] if ask_demo else ""})
    with st.form("ask-arca-main", clear_on_submit=True):
        st.markdown("<div class='ask-label'>What would you like to investigate?</div><div class='ask-help'>Ask a question about the evidence available in this workspace.</div>", unsafe_allow_html=True)
        main_question = st.text_input(
            "Investigation question",
            key="ask-arca-question",
            placeholder="Ask ARCA anything... e.g., Why did I lose access to my Storage Account?",
            label_visibility="collapsed",
        )
        ask_button_column, ask_progress_column = st.columns([1, 2], vertical_alignment="center")
        with ask_button_column:
            ask_button_slot = st.empty()
            main_submitted = ask_button_slot.form_submit_button("🔎 Ask ARCA", type="primary", width="stretch")
        with ask_progress_column: ask_progress_slot = st.empty()

    st.markdown("**Suggested investigations**")
    suggestions = st.columns(4)
    suggested_prompt = None
    shortcuts = ([
        ("Investigate approved change", "Investigate change CHG-SF-1007."),
        ("Review user activity", "Investigate rogue.engineer@example.invalid for the last 10 days."),
        ("Find unexpected grants", "Find unexpected role grants in the last 10 days."),
        ("Review ACCOUNTADMIN", "Which Snowflake changes were performed using ACCOUNTADMIN in the last 30 days?"),
    ] if provider_name == "snowflake" else [
        ("Investigate access issues", "I cannot access starchprod04. What changed?"),
        ("Show recent infrastructure changes", "Who modified starchprod01 during the last 7 days?"),
        ("Review privileged access", "Who requested Contributor access at subscription scope this week?"),
        ("Find undocumented changes", "Show undocumented production changes in the last 24 hours."),
    ])
    for index, (label, question) in enumerate(shortcuts):
        with suggestions[index]:
            if st.button(label, key=f"suggestion-{index}", width="stretch"): suggested_prompt = question

    for turn in st.session_state.investigation_turns:
        with st.chat_message("user"): st.write(turn["query"])
        with st.chat_message("assistant"):
            st.write(present_response(turn["response"]))
            if turn.get("evidence_refs"):
                with st.expander(f"Evidence references · {len(turn['evidence_refs'])}"):
                    st.write("  \n".join(f"`{reference}`" for reference in turn["evidence_refs"]))
            for label, result in turn.get("tool_results", {}).items():
                if result.get("items"):
                    with st.expander(f"{label.replace('_', ' ').title()} · {result['count']} record(s)"):
                        st.dataframe(result["items"], width="stretch", hide_index=True)

    followup_submitted, followup_question, followup_button_slot, followup_progress_slot = False, "", None, None
    if st.session_state.investigation_turns:
        with st.form("ask-arca-followup", clear_on_submit=True):
            followup_question = st.text_input("Continue the investigation", placeholder="Ask a follow-up question...")
            followup_button_column, followup_progress_column = st.columns([1, 2], vertical_alignment="center")
            with followup_button_column:
                followup_button_slot = st.empty()
                followup_submitted = followup_button_slot.form_submit_button("Send follow-up", type="primary")
            with followup_progress_column: followup_progress_slot = st.empty()

    active_prompt = choose_question(main_submitted=main_submitted, main_text=main_question,
                                    suggested_text=suggested_prompt, followup_submitted=followup_submitted,
                                    followup_text=followup_question)
    if active_prompt:
        action_started = perf_counter()
        assessment_id = new_id("assessment")
        active_button = ask_button_slot if main_submitted else followup_button_slot
        active_progress = ask_progress_slot if main_submitted else followup_progress_slot
        if active_button is not None:
            active_button.empty()
            active_button.form_submit_button("Ask ARCA (processing)" if main_submitted else "Send follow-up (processing)",
                                             disabled=True, width="stretch")
        progress_context = active_progress.container() if active_progress is not None else st.container()
        with progress_context:
            with st.spinner("Analyzing your question...", show_time=True):
                with telemetry_context(environment=provider_name, feature="Ask ARCA", stage="Ask ARCA",
                                       agent_name="Investigation Assistant", assessment_id=assessment_id):
                    state = st.session_state.investigation_agent.ask(
                        active_prompt, st.session_state.investigation_thread,
                        context=st.session_state.get("investigation_agent_context") or None,
                    )
        st.session_state.investigation_turns.append({
            "query": active_prompt, "response": state["response"], "evidence_refs": state.get("evidence_refs", []),
            "tool_results": state.get("tool_results", {}), "status": state.get("status"),
        })
        findings = [item for result in state.get("tool_results", {}).values() for item in result.get("items", [])]
        record_ui_assessment("Ask ARCA", provider_name, state.get("status", "complete").upper(),
                             action_started, findings)
        st.rerun()

    feedback_controls(st.session_state.get("latest_assessment"), "ask-arca")

st.markdown("<p style='text-align:center;color:#7A8798;font-size:.72rem;margin-top:2.5rem'>ARCA · Demonstration evidence · Not a security enforcement system</p>", unsafe_allow_html=True)
