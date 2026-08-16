
"""System and controlled-error endpoint tests."""

from __future__ import annotations

from uuid import uuid4

from api.schemas import (
    APIErrorResponse,
    HealthResponse,
    ModelInfoResponse,
    ModelMetricsResponse,
    OperationalMetricsResponse,
)


def test_health_endpoint(client):
    response = client.get(
        "/health"
    )

    assert response.status_code == 200

    parsed = HealthResponse.model_validate(
        response.json()
    )

    assert parsed.status == "success"
    assert parsed.uptime_seconds >= 0.0
    assert parsed.educational_use_only is True


def test_model_info_endpoint(client):
    response = client.get(
        "/api/v1/model/info"
    )

    assert response.status_code == 200

    parsed = ModelInfoResponse.model_validate(
        response.json()
    )

    assert parsed.status == "success"
    assert parsed.educational_use_only is True


def test_model_metrics_endpoint(client):
    response = client.get(
        "/api/v1/model/metrics"
    )

    assert response.status_code == 200

    parsed = ModelMetricsResponse.model_validate(
        response.json()
    )

    assert parsed.status == "success"


def test_operational_metrics_endpoint(client):
    response = client.get(
        "/api/v1/llmops/metrics"
    )

    assert response.status_code == 200

    parsed = OperationalMetricsResponse.model_validate(
        response.json()
    )

    assert parsed.total_requests >= 0
    assert parsed.successful_requests >= 0
    assert parsed.failed_requests >= 0


def test_openapi_contains_twelve_paths(client):
    response = client.get(
        "/openapi.json"
    )

    assert response.status_code == 200
    assert len(
        response.json()["paths"]
    ) == 12


def test_missing_prediction_is_controlled(client):
    response = client.get(
        f"/api/v1/predictions/{uuid4()}"
    )

    assert response.status_code == 404

    parsed = APIErrorResponse.model_validate(
        response.json()
    )

    assert (
        parsed.error_code
        == "PREDICTION_NOT_FOUND"
    )
    assert parsed.educational_use_only is True


def test_malformed_prediction_id_is_controlled(
    client,
):
    response = client.get(
        "/api/v1/predictions/not-a-uuid"
    )

    assert response.status_code == 422

    parsed = APIErrorResponse.model_validate(
        response.json()
    )

    assert (
        parsed.error_code
        == "REQUEST_VALIDATION_ERROR"
    )
