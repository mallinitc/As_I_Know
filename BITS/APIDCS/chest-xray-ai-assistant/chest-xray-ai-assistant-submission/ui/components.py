from __future__ import annotations

import base64
import binascii
from typing import Any

import pandas as pd
import streamlit as st


def build_finding_table(
    findings: list[dict[str, Any]],
) -> pd.DataFrame:
    """Build an ordered table from authoritative API finding records."""
    rows = []

    for finding in findings:
        rows.append(
            {
                "Label ID": finding.get("label_id"),
                "Finding": finding.get(
                    "display_name",
                    finding.get("label_name", "Unavailable"),
                ),
                "Probability": finding.get("probability"),
                "Frozen Threshold": finding.get(
                    "frozen_threshold"
                ),
                "Crossed Threshold": finding.get(
                    "crossed_threshold"
                ),
                "Confidence": finding.get(
                    "confidence_category",
                    "Unavailable",
                ),
            }
        )

    finding_table = pd.DataFrame(rows)

    if (
        not finding_table.empty
        and "Label ID" in finding_table.columns
    ):
        finding_table = (
            finding_table
            .sort_values("Label ID")
            .reset_index(drop=True)
        )

    return finding_table


def render_finding_summary(
    response: dict[str, Any],
) -> None:
    """Render model findings without adding clinical interpretation."""
    st.divider()
    st.subheader("3. Finding Summary")

    findings = response.get(
        "findings",
        [],
    )

    crossed_finding_names = response.get(
        "crossed_finding_names",
        [],
    )

    no_target_finding = response.get(
        "no_target_finding",
        False,
    )

    interpretation = response.get(
        "interpretation",
        "",
    )

    if not isinstance(findings, list):
        st.error(
            "The API response does not contain a valid finding list."
        )
        return

    finding_table = build_finding_table(
        findings
    )

    summary_columns = st.columns(3)

    summary_columns[0].metric(
        "Target Findings Evaluated",
        len(findings),
    )

    summary_columns[1].metric(
        "Thresholds Crossed",
        len(crossed_finding_names)
        if isinstance(crossed_finding_names, list)
        else 0,
    )

    summary_columns[2].metric(
        "No Target Finding",
        "Yes" if no_target_finding else "No",
    )

    if no_target_finding:
        st.info(
            "None of the fourteen ChestMNIST target findings crossed "
            "their frozen thresholds. This state must not be interpreted "
            "as confirmation of a clinically normal chest radiograph."
        )
    else:
        crossed_display = (
            ", ".join(crossed_finding_names)
            if isinstance(crossed_finding_names, list)
            else "Unavailable"
        )

        st.warning(
            "One or more model outputs crossed their frozen "
            f"thresholds: {crossed_display}. Threshold crossing is "
            "a model decision and is not a clinical diagnosis."
        )

    if interpretation:
        st.markdown("#### Backend Interpretation")
        st.write(interpretation)

    if finding_table.empty:
        st.warning(
            "No finding records were returned by the backend."
        )
        return

    st.dataframe(
        finding_table,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Label ID": st.column_config.NumberColumn(
                "Label ID",
                format="%d",
            ),
            "Finding": st.column_config.TextColumn(
                "Finding",
            ),
            "Probability": st.column_config.NumberColumn(
                "Probability",
                format="%.4f",
            ),
            "Frozen Threshold": st.column_config.NumberColumn(
                "Frozen Threshold",
                format="%.4f",
            ),
            "Crossed Threshold": st.column_config.CheckboxColumn(
                "Crossed Threshold",
            ),
            "Confidence": st.column_config.TextColumn(
                "Confidence",
            ),
        },
    )

    crossed_findings = [
        finding
        for finding in findings
        if finding.get("crossed_threshold") is True
    ]

    if crossed_findings:
        with st.expander(
            "Approved descriptions for crossed findings",
            expanded=False,
        ):
            for finding in crossed_findings:
                display_name = finding.get(
                    "display_name",
                    finding.get(
                        "label_name",
                        "Finding",
                    ),
                )

                approved_description = finding.get(
                    "approved_description",
                    "No approved description was returned.",
                )

                st.markdown(
                    f"**{display_name}**"
                )
                st.write(
                    approved_description
                )


def decode_base64_image(
    encoded_image: Any,
) -> bytes | None:
    """Decode an API-provided base64 image without modifying it."""
    if not isinstance(encoded_image, str):
        return None

    normalized_value = encoded_image.strip()

    if not normalized_value:
        return None

    if "," in normalized_value and normalized_value.startswith(
        "data:"
    ):
        normalized_value = normalized_value.split(
            ",",
            maxsplit=1,
        )[1]

    try:
        decoded_image = base64.b64decode(
            normalized_value
        )
    except (
        ValueError,
        binascii.Error,
    ):
        return None

    return decoded_image or None


def render_visual_evidence(
    response: dict[str, Any],
    fallback_limitation: str,
) -> None:
    """Render API-provided Grad-CAM only for crossed findings."""
    st.divider()
    st.subheader("4. Grad-CAM Visual Evidence")

    explainability = response.get(
        "explainability",
        {},
    )

    visual_evidence = response.get(
        "visual_evidence",
        [],
    )

    no_target_finding = response.get(
        "no_target_finding",
        False,
    )

    if not isinstance(explainability, dict):
        explainability = {}

    if not isinstance(visual_evidence, list):
        visual_evidence = []

    crossed_visual_evidence = [
        evidence
        for evidence in visual_evidence
        if isinstance(evidence, dict)
        and evidence.get("crossed_threshold") is True
    ]

    limitation = explainability.get(
        "limitation"
    )

    if not isinstance(limitation, str) or not limitation.strip():
        limitation = fallback_limitation

    st.warning(
        limitation,
        icon="⚠️",
    )

    method_columns = st.columns(2)

    method_columns[0].write(
        f"**Method:** "
        f"{explainability.get('method', 'Unavailable')}"
    )

    method_columns[1].write(
        f"**Target layer:** "
        f"{explainability.get('target_layer', 'Unavailable')}"
    )

    if no_target_finding:
        st.info(
            "No Grad-CAM overlay is displayed because none of the "
            "fourteen target findings crossed its frozen threshold."
        )
        return

    if not crossed_visual_evidence:
        st.warning(
            "No crossed-finding visual evidence was returned by "
            "the backend."
        )
        return

    st.caption(
        "The following images show regions that influenced each "
        "crossed model output. They do not identify or confirm a "
        "lesion or anatomical abnormality."
    )

    for evidence in crossed_visual_evidence:
        finding_name = evidence.get(
            "finding_name",
            "Finding",
        )

        probability = evidence.get(
            "probability"
        )

        frozen_threshold = evidence.get(
            "frozen_threshold"
        )

        with st.expander(
            f"{finding_name} visual evidence",
            expanded=True,
        ):
            evidence_columns = st.columns(
                2,
                gap="large",
            )

            overlay_bytes = decode_base64_image(
                evidence.get(
                    "overlay_png_base64"
                )
            )

            heatmap_bytes = decode_base64_image(
                evidence.get(
                    "heatmap_png_base64"
                )
            )

            with evidence_columns[0]:
                st.markdown(
                    "**Grad-CAM Overlay**"
                )

                if overlay_bytes is not None:
                    st.image(
                        overlay_bytes,
                        caption=(
                            f"{finding_name} model-influence overlay"
                        ),
                        use_container_width=True,
                    )
                else:
                    st.error(
                        "The overlay image could not be decoded."
                    )

            with evidence_columns[1]:
                st.markdown(
                    "**Attribution Heatmap**"
                )

                if heatmap_bytes is not None:
                    st.image(
                        heatmap_bytes,
                        caption=(
                            f"{finding_name} attribution heatmap"
                        ),
                        use_container_width=True,
                    )
                else:
                    st.error(
                        "The heatmap image could not be decoded."
                    )

            detail_columns = st.columns(3)

            detail_columns[0].metric(
                "Probability",
                (
                    f"{probability:.4f}"
                    if isinstance(
                        probability,
                        (int, float),
                    )
                    else "Unavailable"
                ),
            )

            detail_columns[1].metric(
                "Frozen Threshold",
                (
                    f"{frozen_threshold:.4f}"
                    if isinstance(
                        frozen_threshold,
                        (int, float),
                    )
                    else "Unavailable"
                ),
            )

            footprint = evidence.get(
                "high_attribution_area_percent"
            )

            detail_columns[2].metric(
                "High-Attribution Area",
                (
                    f"{footprint:.2f}%"
                    if isinstance(
                        footprint,
                        (int, float),
                    )
                    else "Not provided"
                ),
            )

            st.caption(limitation)


LANGUAGE_TASK_LABELS = {
    "structured_report": "Structured Preliminary Report",
    "plain_language_explanation": "Plain-Language Explanation",
    "educational_follow_up": "Educational Follow-Up",
    "grounded_question_answering": "Grounded Question Answer",
}

LANGUAGE_TASK_ORDER = (
    "structured_report",
    "plain_language_explanation",
    "educational_follow_up",
    "grounded_question_answering",
)


def render_language_outputs(
    response: dict[str, Any],
) -> None:
    """Render API-grounded language outputs and guardrail metadata."""
    st.divider()
    st.subheader("5. Grounded Language Outputs")

    language_outputs = response.get(
        "language_outputs",
        [],
    )

    if not isinstance(language_outputs, list):
        st.error(
            "The API response does not contain a valid "
            "language-output collection."
        )
        return

    valid_outputs = [
        output
        for output in language_outputs
        if isinstance(output, dict)
    ]

    if not valid_outputs:
        st.info(
            "No grounded language outputs were returned "
            "for this prediction."
        )
        return

    task_order = {
        task_name: index
        for index, task_name in enumerate(
            LANGUAGE_TASK_ORDER
        )
    }

    ordered_outputs = sorted(
        valid_outputs,
        key=lambda output: task_order.get(
            output.get("task_type"),
            len(task_order),
        ),
    )

    tab_labels = [
        LANGUAGE_TASK_LABELS.get(
            output.get("task_type"),
            str(
                output.get(
                    "task_type",
                    "Language Output",
                )
            ).replace("_", " ").title(),
        )
        for output in ordered_outputs
    ]

    output_tabs = st.tabs(
        tab_labels
    )

    for output_tab, output in zip(
        output_tabs,
        ordered_outputs,
    ):
        with output_tab:
            task_type = output.get(
                "task_type",
                "unknown",
            )

            question = output.get(
                "question"
            )

            if (
                task_type
                == "grounded_question_answering"
                and isinstance(question, str)
                and question.strip()
            ):
                st.markdown(
                    "**Grounded question**"
                )
                st.write(question)

            st.markdown(
                "**API-generated output**"
            )

            output_text = output.get(
                "output_text",
                "No output text was returned.",
            )

            st.write(output_text)

            guardrail_action = output.get(
                "guardrail_action",
                "Unavailable",
            )

            trigger_reasons = output.get(
                "trigger_reasons",
                [],
            )

            if (
                guardrail_action
                == "safe_template_fallback"
            ):
                st.info(
                    "The deterministic language guardrail "
                    "replaced the raw model generation with "
                    "a grounded safety template."
                )

            with st.expander(
                "Generation and guardrail details",
                expanded=False,
            ):
                detail_columns = st.columns(3)

                detail_columns[0].metric(
                    "Generated Tokens",
                    output.get(
                        "generated_tokens",
                        "Unavailable",
                    ),
                )

                generation_latency = output.get(
                    "generation_latency_ms"
                )

                detail_columns[1].metric(
                    "Generation Latency",
                    (
                        f"{generation_latency:.2f} ms"
                        if isinstance(
                            generation_latency,
                            (int, float),
                        )
                        else "Unavailable"
                    ),
                )

                detail_columns[2].metric(
                    "Guardrail Action",
                    str(guardrail_action),
                )

                st.write(
                    f"**Task type:** `{task_type}`"
                )

                if (
                    isinstance(trigger_reasons, list)
                    and trigger_reasons
                ):
                    st.write(
                        "**Fallback trigger reasons:**"
                    )

                    for reason in trigger_reasons:
                        st.write(
                            f"- `{reason}`"
                        )
                else:
                    st.write(
                        "**Fallback trigger reasons:** None"
                    )

    st.caption(
        "All displayed language outputs are grounded only in the "
        "structured API evidence and remain subject to the educational "
        "use limitation shown at the top of the interface."
    )


def render_grounded_question_response(
    response: dict[str, Any],
) -> None:
    """Render a grounded-question response and its guardrail details."""
    st.markdown("#### Grounded Answer")

    question = response.get(
        "question"
    )

    if isinstance(question, str) and question.strip():
        st.markdown("**Question**")
        st.write(question)

    st.markdown("**API-generated answer**")
    st.write(
        response.get(
            "output_text",
            "No answer text was returned.",
        )
    )

    guardrail_action = response.get(
        "guardrail_action",
        "Unavailable",
    )

    trigger_reasons = response.get(
        "trigger_reasons",
        [],
    )

    if guardrail_action == "safe_template_fallback":
        st.info(
            "The deterministic language guardrail replaced the raw "
            "model generation with a grounded safety template."
        )

    metric_columns = st.columns(3)

    metric_columns[0].metric(
        "Generated Tokens",
        response.get(
            "generated_tokens",
            "Unavailable",
        ),
    )

    generation_latency = response.get(
        "generation_latency_ms"
    )

    metric_columns[1].metric(
        "Generation Latency",
        (
            f"{generation_latency:.2f} ms"
            if isinstance(
                generation_latency,
                (int, float),
            )
            else "Unavailable"
        ),
    )

    metric_columns[2].metric(
        "Guardrail Action",
        str(guardrail_action),
    )

    with st.expander(
        "Question-response details",
        expanded=False,
    ):
        st.write(
            f"**Task type:** "
            f"`{response.get('task_type', 'Unavailable')}`"
        )
        st.write(
            f"**Request ID:** "
            f"`{response.get('request_id', 'Unavailable')}`"
        )
        st.write(
            f"**Prediction ID:** "
            f"`{response.get('prediction_id', 'Unavailable')}`"
        )
        st.write(
            f"**Request latency:** "
            f"{response.get('latency_ms', 'Unavailable')} ms"
        )

        if (
            isinstance(trigger_reasons, list)
            and trigger_reasons
        ):
            st.write(
                "**Fallback trigger reasons:**"
            )

            for reason in trigger_reasons:
                st.write(
                    f"- `{reason}`"
                )
        else:
            st.write(
                "**Fallback trigger reasons:** None"
            )

    st.caption(
        "This answer is grounded only in the active prediction's "
        "structured evidence and does not independently inspect "
        "the uploaded image."
    )


def render_stored_prediction_summary(
    response: dict[str, Any],
) -> None:
    """Render a compact summary of a retrieved prediction record."""
    st.markdown("#### Retrieved Prediction Record")

    findings = response.get("findings", [])
    visual_evidence = response.get(
        "visual_evidence",
        [],
    )
    language_outputs = response.get(
        "language_outputs",
        [],
    )
    crossed_finding_names = response.get(
        "crossed_finding_names",
        [],
    )

    summary_columns = st.columns(4)

    summary_columns[0].metric(
        "Stored Findings",
        len(findings)
        if isinstance(findings, list)
        else 0,
    )

    summary_columns[1].metric(
        "Thresholds Crossed",
        len(crossed_finding_names)
        if isinstance(crossed_finding_names, list)
        else 0,
    )

    summary_columns[2].metric(
        "Visual Evidence",
        len(visual_evidence)
        if isinstance(visual_evidence, list)
        else 0,
    )

    summary_columns[3].metric(
        "Language Outputs",
        len(language_outputs)
        if isinstance(language_outputs, list)
        else 0,
    )

    with st.expander(
        "Stored-record identifiers",
        expanded=False,
    ):
        st.write(
            f"**Prediction ID:** "
            f"`{response.get('prediction_id', 'Unavailable')}`"
        )
        st.write(
            f"**Record created:** "
            f"{response.get('created_at_utc', 'Unavailable')}"
        )
        st.write(
            f"**Retrieval request ID:** "
            f"`{response.get('request_id', 'Unavailable')}`"
        )
        st.write(
            f"**Retrieval latency:** "
            f"{response.get('latency_ms', 'Unavailable')} ms"
        )
        st.write(
            f"**No target finding:** "
            f"{response.get('no_target_finding', 'Unavailable')}"
        )

    st.caption(
        "This view summarizes the existing backend record. "
        "Retrieval does not repeat model inference or generation."
    )
