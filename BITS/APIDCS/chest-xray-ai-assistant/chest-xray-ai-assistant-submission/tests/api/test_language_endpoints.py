
"""Grounded language endpoint tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from api.schemas import (
    APIErrorResponse,
    LanguageGenerationResponse,
    StoredPredictionResponse,
)


LANGUAGE_ROUTES = (
    (
        "structured_report",
        "/api/v1/report/generate",
    ),
    (
        "plain_language_explanation",
        "/api/v1/explanation/generate",
    ),
    (
        "grounded_question_answering",
        "/api/v1/question/answer",
    ),
    (
        "educational_follow_up",
        "/api/v1/follow-up/recommend",
    ),
)


@pytest.mark.parametrize(
    (
        "task_type",
        "path",
    ),
    LANGUAGE_ROUTES,
)
def test_grounded_language_endpoint(
    client,
    classification_payload,
    task_type,
    path,
):
    request_payload = {
        "prediction_id": (
            classification_payload[
                "prediction_id"
            ]
        )
    }

    if (
        task_type
        == "grounded_question_answering"
    ):
        request_payload[
            "question"
        ] = (
            "What does the supplied model "
            "information indicate?"
        )

    response = client.post(
        path,
        json=request_payload,
    )

    assert response.status_code == 200

    parsed = (
        LanguageGenerationResponse
        .model_validate(
            response.json()
        )
    )

    assert parsed.task_type == task_type
    assert parsed.output_text.strip()
    assert "LIMITATIONS" in parsed.output_text

    assert parsed.guardrail_action in {
        "accepted_model_generation",
        "safe_template_fallback",
    }

    if (
        parsed.guardrail_action
        == "safe_template_fallback"
    ):
        assert parsed.trigger_reasons
    else:
        assert not parsed.trigger_reasons


def test_language_outputs_are_upserted(
    client,
    classification_payload,
):
    prediction_id = (
        classification_payload[
            "prediction_id"
        ]
    )

    response = client.get(
        f"/api/v1/predictions/{prediction_id}"
    )

    assert response.status_code == 200

    parsed = StoredPredictionResponse.model_validate(
        response.json()
    )

    task_names = [
        output.task_type
        for output
        in parsed.language_outputs
    ]

    assert set(task_names) == {
        task_type
        for task_type, _
        in LANGUAGE_ROUTES
    }

    assert len(task_names) == len(
        set(task_names)
    )


def test_blank_question_is_rejected(
    client,
    classification_payload,
):
    response = client.post(
        "/api/v1/question/answer",
        json={
            "prediction_id": (
                classification_payload[
                    "prediction_id"
                ]
            ),
            "question": "   ",
        },
    )

    assert response.status_code == 422

    parsed = APIErrorResponse.model_validate(
        response.json()
    )

    assert (
        parsed.error_code
        == "REQUEST_VALIDATION_ERROR"
    )


def test_missing_language_prediction_is_controlled(
    client,
):
    response = client.post(
        "/api/v1/report/generate",
        json={
            "prediction_id": str(
                uuid4()
            )
        },
    )

    assert response.status_code == 404

    parsed = APIErrorResponse.model_validate(
        response.json()
    )

    assert (
        parsed.error_code
        == "PREDICTION_NOT_FOUND"
    )
