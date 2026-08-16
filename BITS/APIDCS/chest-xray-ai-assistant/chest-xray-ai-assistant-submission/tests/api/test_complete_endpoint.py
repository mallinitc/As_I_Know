
"""Complete-analysis endpoint tests."""

from __future__ import annotations

from api.schemas import (
    APIErrorResponse,
    CompleteAnalysisResponse,
    StoredPredictionResponse,
)


def test_complete_analysis_with_question(
    client,
    valid_png_bytes,
):
    question = (
        "What does the supplied model "
        "information indicate?"
    )

    response = client.post(
        "/api/v1/analyze-complete",
        files={
            "image": (
                "pytest-complete.png",
                valid_png_bytes,
                "image/png",
            )
        },
        data={
            "question": question
        },
    )

    assert response.status_code == 200

    parsed = CompleteAnalysisResponse.model_validate(
        response.json()
    )

    assert len(parsed.findings) == 14

    task_names = [
        output.task_type
        for output
        in parsed.language_outputs
    ]

    assert task_names == [
        "structured_report",
        "plain_language_explanation",
        "educational_follow_up",
        "grounded_question_answering",
    ]

    qa_output = next(
        output
        for output
        in parsed.language_outputs
        if output.task_type
        == "grounded_question_answering"
    )

    assert qa_output.question == question

    stored_response = client.get(
        f"/api/v1/predictions/"
        f"{parsed.prediction_id}"
    )

    assert stored_response.status_code == 200

    stored = StoredPredictionResponse.model_validate(
        stored_response.json()
    )

    assert (
        stored.prediction_id
        == parsed.prediction_id
    )

    assert [
        output.task_type
        for output
        in stored.language_outputs
    ] == task_names


def test_complete_analysis_without_question(
    client,
    valid_png_bytes,
):
    response = client.post(
        "/api/v1/analyze-complete",
        files={
            "image": (
                "pytest-complete-no-qa.png",
                valid_png_bytes,
                "image/png",
            )
        },
    )

    assert response.status_code == 200

    parsed = CompleteAnalysisResponse.model_validate(
        response.json()
    )

    assert [
        output.task_type
        for output
        in parsed.language_outputs
    ] == [
        "structured_report",
        "plain_language_explanation",
        "educational_follow_up",
    ]


def test_complete_invalid_media_is_controlled(
    client,
):
    response = client.post(
        "/api/v1/analyze-complete",
        files={
            "image": (
                "invalid.txt",
                b"not-an-image",
                "text/plain",
            )
        },
    )

    assert response.status_code == 415

    parsed = APIErrorResponse.model_validate(
        response.json()
    )

    assert (
        parsed.error_code
        == "UNSUPPORTED_MEDIA_TYPE"
    )
