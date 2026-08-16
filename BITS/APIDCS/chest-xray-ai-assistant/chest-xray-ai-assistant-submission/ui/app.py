from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import streamlit as st
import yaml

from api_client import (
    APIClientError,
    ChestXRayAPIClient,
)
from components import (
    render_finding_summary,
    render_grounded_question_response,
    render_language_outputs,
    render_stored_prediction_summary,
    render_visual_evidence,
)


SOLUTION_ROOT = Path(__file__).resolve().parents[1]
UI_CONFIG_PATH = SOLUTION_ROOT / "configs" / "ui_config.yaml"


def load_ui_configuration(
    config_path: Path,
) -> dict[str, Any]:
    """Load the persisted UI configuration."""
    if not config_path.is_file():
        raise FileNotFoundError(
            f"UI configuration was not found: {config_path}"
        )

    with config_path.open("r", encoding="utf-8") as file:
        configuration = yaml.safe_load(file) or {}

    if not isinstance(configuration, dict):
        raise TypeError(
            "The UI configuration must contain a YAML mapping."
        )

    return configuration


def format_file_size(
    size_bytes: int,
) -> str:
    """Format a file size using binary units."""
    return f"{size_bytes / (1024 ** 2):.2f} MiB"


def initialize_session_state() -> None:
    """Initialize all UI-local workflow state."""
    default_state = {
        "upload_signature": None,
        "uploaded_filename": None,
        "uploaded_media_type": None,
        "uploaded_image_bytes": None,
        "upload_ready": False,
        "analysis_response": None,
        "active_prediction_id": None,
        "question_response": None,
        "stored_prediction_response": None,
        "last_api_error": None,
    }

    for key, default_value in default_state.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def reset_analysis_state() -> None:
    """Clear outputs when the selected image changes."""
    st.session_state.analysis_response = None
    st.session_state.active_prediction_id = None
    st.session_state.question_response = None
    st.session_state.stored_prediction_response = None
    st.session_state.last_api_error = None


@st.cache_resource(show_spinner=False)
def get_api_client(
    base_url: str,
) -> ChestXRayAPIClient:
    """Create one reusable HTTP client."""
    return ChestXRayAPIClient(
        base_url=base_url,
        timeout_seconds=120.0,
    )


def render_api_error(
    error_details: dict[str, Any],
) -> None:
    """Render only controlled, UI-safe error information."""
    st.error(
        error_details.get(
            "message",
            "The request could not be completed.",
        )
    )

    with st.expander(
        "Technical error details",
        expanded=False,
    ):
        st.write(
            f"**Error code:** "
            f"{error_details.get('error_code', 'UNKNOWN')}"
        )

        status_code = error_details.get("status_code")

        if status_code is not None:
            st.write(
                f"**HTTP status:** {status_code}"
            )

        request_id = error_details.get("request_id")

        if request_id:
            st.write(
                f"**Request ID:** `{request_id}`"
            )

        safe_details = error_details.get("details")

        if isinstance(safe_details, dict) and safe_details:
            st.json(safe_details)


def render_sidebar(
    api_base_url: str,
    upload_config: dict[str, Any],
    safety_config: dict[str, Any],
) -> None:
    """Render system-boundary information."""
    with st.sidebar:
        st.header("System Boundary")

        st.info(
            "The interface communicates with the FastAPI backend "
            "through HTTP. It does not load the models, Grad-CAM "
            "service, or prediction store directly."
        )

        st.subheader("Backend Address")
        st.code(
            api_base_url,
            language=None,
        )

        st.subheader("Accepted Uploads")
        st.caption(
            "PNG or JPEG • Maximum "
            f"{upload_config['maximum_size_mib']} MiB"
        )

        st.subheader("Professional Review")
        st.caption(
            safety_config[
                "professional_review_guidance"
            ]
        )


def render_upload(
    upload_config: dict[str, Any],
) -> None:
    """Render image selection, size awareness, and preview."""
    st.divider()
    st.subheader("1. Select a Chest X-Ray Image")

    uploaded_file = st.file_uploader(
        "Choose a PNG or JPEG image",
        type=upload_config[
            "supported_extensions"
        ],
        accept_multiple_files=False,
        help=(
            "The backend accepts image/png and image/jpeg files "
            f"up to {upload_config['maximum_size_mib']} MiB."
        ),
    )

    if uploaded_file is None:
        if st.session_state.upload_signature is not None:
            reset_analysis_state()

        st.session_state.upload_signature = None
        st.session_state.uploaded_filename = None
        st.session_state.uploaded_media_type = None
        st.session_state.uploaded_image_bytes = None
        st.session_state.upload_ready = False

        st.info(
            "Select an image to enable API submission."
        )
        return

    uploaded_image_bytes = uploaded_file.getvalue()
    uploaded_size_bytes = len(
        uploaded_image_bytes
    )
    uploaded_media_type = uploaded_file.type or ""

    upload_signature = hashlib.sha256(
        uploaded_image_bytes
    ).hexdigest()

    if (
        st.session_state.upload_signature
        != upload_signature
    ):
        reset_analysis_state()

    st.session_state.upload_signature = (
        upload_signature
    )
    st.session_state.uploaded_filename = (
        uploaded_file.name
    )
    st.session_state.uploaded_media_type = (
        uploaded_media_type
    )
    st.session_state.uploaded_image_bytes = (
        uploaded_image_bytes
    )

    size_within_limit = (
        uploaded_size_bytes
        <= upload_config["maximum_size_bytes"]
    )

    media_type_supported = (
        uploaded_media_type
        in upload_config["supported_media_types"]
    )

    st.session_state.upload_ready = (
        size_within_limit
        and media_type_supported
    )

    preview_column, details_column = st.columns(
        [1.4, 1.0],
        gap="large",
    )

    with preview_column:
        st.image(
            uploaded_image_bytes,
            caption=uploaded_file.name,
            use_container_width=True,
        )

    with details_column:
        st.markdown("#### Selected Image")
        st.write(
            f"**Filename:** {uploaded_file.name}"
        )
        st.write(
            f"**Media type:** "
            f"{uploaded_media_type or 'Not reported'}"
        )
        st.write(
            f"**File size:** "
            f"{format_file_size(uploaded_size_bytes)}"
        )
        st.write(
            f"**Backend size limit:** "
            f"{upload_config['maximum_size_mib']} MiB"
        )

        if not size_within_limit:
            st.error(
                "The selected file exceeds the backend's "
                f"{upload_config['maximum_size_mib']} MiB limit."
            )
        elif not media_type_supported:
            st.error(
                "The selected file does not report a supported "
                "PNG or JPEG media type."
            )
        else:
            st.success(
                "The file is ready for secure backend "
                "validation and analysis."
            )

    st.caption(
        "The preview and size check do not validate medical "
        "content. Image validation remains authoritative in "
        "the FastAPI backend."
    )


def render_analysis_submission(
    api_base_url: str,
) -> None:
    """Submit the selected image only on explicit user action."""
    st.divider()
    st.subheader("2. Run Complete Analysis")

    initial_question = st.text_area(
        "Optional grounded question",
        placeholder=(
            "Example: Which findings crossed their "
            "frozen thresholds?"
        ),
        help=(
            "The question is answered only from the structured "
            "model evidence and safety limitations."
        ),
        disabled=not st.session_state.upload_ready,
    )

    submit_analysis = st.button(
        "Run Complete Analysis",
        type="primary",
        use_container_width=True,
        disabled=not st.session_state.upload_ready,
    )

    if not submit_analysis:
        return

    st.session_state.last_api_error = None
    st.session_state.question_response = None
    st.session_state.stored_prediction_response = None

    try:
        with st.spinner(
            "Submitting the image to the FastAPI "
            "analysis workflow..."
        ):
            api_client = get_api_client(
                api_base_url
            )

            response = api_client.analyze_complete(
                filename=st.session_state.uploaded_filename,
                media_type=st.session_state.uploaded_media_type,
                image_content=st.session_state.uploaded_image_bytes,
                question=(
                    initial_question
                    if initial_question.strip()
                    else None
                ),
            )

        st.session_state.analysis_response = response
        st.session_state.active_prediction_id = (
            response.get("prediction_id")
        )

    except APIClientError as exc:
        st.session_state.analysis_response = None
        st.session_state.active_prediction_id = None
        st.session_state.last_api_error = (
            exc.to_display_dict()
        )

    except ValueError as exc:
        st.session_state.analysis_response = None
        st.session_state.active_prediction_id = None
        st.session_state.last_api_error = {
            "error_code": "INVALID_UI_REQUEST",
            "message": str(exc),
            "status_code": None,
            "request_id": None,
            "details": {},
        }

    except Exception:
        st.session_state.analysis_response = None
        st.session_state.active_prediction_id = None
        st.session_state.last_api_error = {
            "error_code": "UI_EXECUTION_ERROR",
            "message": (
                "The analysis request could not be completed. "
                "Confirm that the backend is healthy and try again."
            ),
            "status_code": None,
            "request_id": None,
            "details": {},
        }


def render_response_metadata(
    response: dict[str, Any],
) -> None:
    """Render identifiers, latency, and model lineage."""
    st.success(
        "The complete-analysis response was received and "
        "preserved in this interface session."
    )

    metadata_columns = st.columns(4)

    metadata_columns[0].metric(
        "Status",
        str(
            response.get(
                "status",
                "success",
            )
        ),
    )

    latency = response.get("latency_ms")

    metadata_columns[1].metric(
        "Request Latency",
        (
            f"{latency:.2f} ms"
            if isinstance(latency, (int, float))
            else "Unavailable"
        ),
    )

    metadata_columns[2].metric(
        "Prediction ID",
        "Available"
        if response.get("prediction_id")
        else "Unavailable",
    )

    language_outputs = response.get(
        "language_outputs",
        [],
    )

    metadata_columns[3].metric(
        "Language Outputs",
        len(language_outputs)
        if isinstance(language_outputs, list)
        else 0,
    )

    with st.expander(
        "Request and lineage identifiers",
        expanded=False,
    ):
        st.write(
            f"**Request ID:** "
            f"`{response.get('request_id', 'Unavailable')}`"
        )
        st.write(
            f"**Prediction ID:** "
            f"`{response.get('prediction_id', 'Unavailable')}`"
        )
        st.write(
            f"**API version:** "
            f"{response.get('api_version', 'Unavailable')}"
        )
        st.write(
            f"**Prompt-registry version:** "
            f"{response.get('prompt_registry_version', 'Unavailable')}"
        )
        st.write("**Model versions:**")
        st.json(
            response.get(
                "model_versions",
                {},
            )
        )


def render_follow_up_workflow(
    api_base_url: str,
) -> None:
    """Submit a grounded question for the active prediction."""
    st.divider()
    st.subheader("6. Ask a Grounded Follow-Up Question")

    st.caption(
        "Only the active prediction ID and question are sent. "
        "The interface cannot submit grounding evidence."
    )

    question = st.text_input(
        "Question about the active prediction",
        placeholder=(
            "Example: What does the crossed-threshold "
            "result mean?"
        ),
        key="follow_up_question_input",
    )

    submit_question = st.button(
        "Ask Grounded Question",
        use_container_width=True,
        disabled=(
            not st.session_state.active_prediction_id
            or not question.strip()
        ),
    )

    if submit_question:
        try:
            with st.spinner(
                "Generating an answer from the active "
                "prediction evidence..."
            ):
                api_client = get_api_client(
                    api_base_url
                )

                response = api_client.answer_question(
                    prediction_id=(
                        st.session_state.active_prediction_id
                    ),
                    question=question,
                )

            st.session_state.question_response = response

        except APIClientError as exc:
            st.session_state.question_response = None
            render_api_error(
                exc.to_display_dict()
            )

        except Exception:
            st.session_state.question_response = None
            render_api_error(
                {
                    "error_code": "UI_EXECUTION_ERROR",
                    "message": (
                        "The grounded question could not be "
                        "completed. Try again after confirming "
                        "backend health."
                    ),
                    "status_code": None,
                    "request_id": None,
                    "details": {},
                }
            )

    if st.session_state.question_response:
        render_grounded_question_response(
            st.session_state.question_response
        )


def render_retrieval_workflow(
    api_base_url: str,
) -> None:
    """Retrieve the active stored prediction without rerunning models."""
    st.divider()
    st.subheader("7. Retrieve the Stored Prediction")

    st.caption(
        "Retrieve the active record from the backend's in-memory "
        "prediction store without repeating analysis."
    )

    retrieve_prediction = st.button(
        "Retrieve Active Prediction",
        use_container_width=True,
        disabled=not st.session_state.active_prediction_id,
    )

    if retrieve_prediction:
        try:
            with st.spinner(
                "Retrieving the active prediction record..."
            ):
                api_client = get_api_client(
                    api_base_url
                )

                response = api_client.get_prediction(
                    st.session_state.active_prediction_id
                )

            st.session_state.stored_prediction_response = (
                response
            )

            st.success(
                "The prediction record was retrieved without "
                "repeating model execution."
            )

        except APIClientError as exc:
            st.session_state.stored_prediction_response = None
            render_api_error(
                exc.to_display_dict()
            )

        except Exception:
            st.session_state.stored_prediction_response = None
            render_api_error(
                {
                    "error_code": "UI_EXECUTION_ERROR",
                    "message": (
                        "The stored prediction could not be "
                        "retrieved. It may have expired or the "
                        "backend may be unavailable."
                    ),
                    "status_code": None,
                    "request_id": None,
                    "details": {},
                }
            )

    stored_response = (
        st.session_state.stored_prediction_response
    )

    if (
        isinstance(stored_response, dict)
        and stored_response.get("prediction_id")
        == st.session_state.active_prediction_id
    ):
        render_stored_prediction_summary(
            stored_response
        )


def render_operational_metrics_workflow(
    api_base_url: str,
) -> None:
    """Retrieve and render operational metrics on explicit request."""
    if "operational_metrics_response" not in st.session_state:
        st.session_state.operational_metrics_response = None

    with st.sidebar:
        st.divider()
        st.subheader("Operational and LLMOps Metrics")

        refresh_metrics = st.button(
            "Refresh Operational Metrics",
            use_container_width=True,
        )

        if refresh_metrics:
            try:
                with st.spinner(
                    "Retrieving operational metrics..."
                ):
                    api_client = get_api_client(
                        api_base_url
                    )

                    metrics_response = (
                        api_client.llmops_metrics()
                    )

                st.session_state.operational_metrics_response = (
                    metrics_response
                )

            except APIClientError as exc:
                st.session_state.operational_metrics_response = None
                render_api_error(
                    exc.to_display_dict()
                )

            except Exception:
                st.session_state.operational_metrics_response = None
                render_api_error(
                    {
                        "error_code": "UI_EXECUTION_ERROR",
                        "message": (
                            "Operational metrics could not be "
                            "retrieved. Confirm backend health "
                            "and try again."
                        ),
                        "status_code": None,
                        "request_id": None,
                        "details": {},
                    }
                )

        metrics_response = (
            st.session_state.operational_metrics_response
        )

        if not isinstance(metrics_response, dict):
            st.caption(
                "Select refresh to retrieve the current "
                "backend operational snapshot."
            )
            return

        total_requests = metrics_response.get(
            "total_requests",
            0,
        )

        successful_requests = metrics_response.get(
            "successful_requests",
            0,
        )

        failed_requests = metrics_response.get(
            "failed_requests",
            0,
        )

        language_requests = metrics_response.get(
            "language_generation_requests",
            0,
        )

        st.metric(
            "Total Requests",
            total_requests,
        )

        success_column, failure_column = st.columns(2)

        success_column.metric(
            "Successful",
            successful_requests,
        )

        failure_column.metric(
            "Failed",
            failed_requests,
        )

        st.metric(
            "Language Generations",
            language_requests,
        )

        guardrail_actions = metrics_response.get(
            "guardrail_action_counts",
            {},
        )

        endpoint_counts = metrics_response.get(
            "endpoint_request_counts",
            {},
        )

        endpoint_latency = metrics_response.get(
            "endpoint_average_latency_ms",
            {},
        )

        with st.expander(
            "Guardrail actions",
            expanded=False,
        ):
            if (
                isinstance(guardrail_actions, dict)
                and guardrail_actions
            ):
                st.json(guardrail_actions)
            else:
                st.caption(
                    "No guardrail actions have been recorded."
                )

        with st.expander(
            "Endpoint request counts",
            expanded=False,
        ):
            if (
                isinstance(endpoint_counts, dict)
                and endpoint_counts
            ):
                st.json(endpoint_counts)
            else:
                st.caption(
                    "No endpoint request counts are available."
                )

        with st.expander(
            "Average endpoint latency",
            expanded=False,
        ):
            if (
                isinstance(endpoint_latency, dict)
                and endpoint_latency
            ):
                st.json(endpoint_latency)
            else:
                st.caption(
                    "No endpoint latency records are available."
                )

        st.caption(
            "Service started: "
            f"{metrics_response.get('service_started_at_utc', 'Unavailable')}"
        )

        st.caption(
            "Metrics request ID: "
            f"{metrics_response.get('request_id', 'Unavailable')}"
        )

def main() -> None:
    """Run the Streamlit interface."""
    ui_config = load_ui_configuration(
        UI_CONFIG_PATH
    )

    page_config = ui_config["page"]
    api_config = ui_config["api"]
    safety_config = ui_config["safety"]
    upload_config = ui_config["upload"]

    api_base_url = os.getenv(
        api_config[
            "base_url_environment_variable"
        ],
        api_config["default_base_url"],
    ).strip().rstrip("/")

    st.set_page_config(
        page_title=page_config["title"],
        page_icon=page_config["icon"],
        layout=page_config["layout"],
        initial_sidebar_state=(
            page_config[
                "initial_sidebar_state"
            ]
        ),
    )

    initialize_session_state()

    st.title(page_config["title"])
    st.caption(page_config["subtitle"])

    st.warning(
        safety_config[
            "educational_limitation"
        ],
        icon="⚠️",
    )

    st.markdown(
        """
        Upload a supported chest X-ray image to request a complete,
        API-driven analysis. Findings are determined only by the
        frozen computer-vision model and persisted thresholds.
        Language outputs use only the resulting structured evidence.
        """
    )

    render_sidebar(
        api_base_url,
        upload_config,
        safety_config,
    )

    render_upload(
        upload_config
    )

    render_analysis_submission(
        api_base_url
    )

    if st.session_state.last_api_error:
        render_api_error(
            st.session_state.last_api_error
        )


    render_operational_metrics_workflow(
        api_base_url
    )

    active_response = (
        st.session_state.analysis_response
    )

    if not isinstance(active_response, dict):
        return

    render_response_metadata(
        active_response
    )

    render_finding_summary(
        active_response
    )

    render_visual_evidence(
        active_response,
        safety_config[
            "gradcam_limitation"
        ],
    )

    render_language_outputs(
        active_response
    )

    render_follow_up_workflow(
        api_base_url
    )

    render_retrieval_workflow(
        api_base_url
    )


if __name__ == "__main__":
    main()
