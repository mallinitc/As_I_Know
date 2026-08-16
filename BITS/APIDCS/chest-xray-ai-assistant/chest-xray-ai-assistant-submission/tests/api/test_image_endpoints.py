
"""Image ingestion and explainability endpoint tests."""

from __future__ import annotations

import pytest

from api.schemas import (
    APIErrorResponse,
    ClassificationResponse,
    ImageAnalysisResponse,
    StoredPredictionResponse,
)


def test_valid_png_classification(
    classification_payload,
):
    parsed = (
        ClassificationResponse
        .model_validate(
            classification_payload
        )
    )

    assert len(parsed.findings) == 14

    crossed_names = [
        finding.label_name
        for finding in parsed.findings
        if finding.crossed_threshold
    ]

    assert (
        crossed_names
        == parsed.crossed_finding_names
    )

    assert (
        parsed.no_target_finding
        == (
            len(
                parsed.crossed_finding_names
            )
            == 0
        )
    )


def test_classification_can_be_retrieved(
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

    assert str(
        parsed.prediction_id
    ) == prediction_id

    assert len(
        parsed.findings
    ) == 14


def test_valid_png_analysis(
    client,
    valid_png_bytes,
):
    response = client.post(
        "/api/v1/image/analyze",
        files={
            "image": (
                "pytest-analysis.png",
                valid_png_bytes,
                "image/png",
            )
        },
    )

    assert response.status_code == 200

    parsed = ImageAnalysisResponse.model_validate(
        response.json()
    )

    assert len(parsed.findings) == 14

    evidence_names = [
        evidence.finding_name
        for evidence
        in parsed.visual_evidence
    ]

    assert (
        evidence_names
        == parsed.crossed_finding_names
    )


@pytest.mark.parametrize(
    (
        "filename",
        "content",
        "media_type",
        "expected_status",
        "expected_code",
    ),
    [
        (
            "unsupported.txt",
            b"not-an-image",
            "text/plain",
            415,
            "UNSUPPORTED_MEDIA_TYPE",
        ),
        (
            "invalid.png",
            b"not-a-valid-png",
            "image/png",
            400,
            "INVALID_IMAGE",
        ),
    ],
)
def test_invalid_image_requests_are_controlled(
    client,
    filename,
    content,
    media_type,
    expected_status,
    expected_code,
):
    response = client.post(
        "/api/v1/image/classify",
        files={
            "image": (
                filename,
                content,
                media_type,
            )
        },
    )

    assert response.status_code == expected_status

    parsed = APIErrorResponse.model_validate(
        response.json()
    )

    assert parsed.error_code == expected_code
    assert parsed.educational_use_only is True


def test_spoofed_media_type_is_rejected(
    client,
    valid_png_bytes,
):
    response = client.post(
        "/api/v1/image/classify",
        files={
            "image": (
                "spoofed.jpg",
                valid_png_bytes,
                "image/jpeg",
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
