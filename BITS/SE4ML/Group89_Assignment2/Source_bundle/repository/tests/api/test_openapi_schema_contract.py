from __future__ import annotations

from typing import Any

import pytest

from api.main import app

EXPECTED_OPERATIONS = {
    "/health": "get",
    "/api/v1/model/info": "get",
    "/api/v1/model/metrics": "get",
    "/api/v1/llmops/metrics": "get",
    "/api/v1/image/classify": "post",
    "/api/v1/image/analyze": "post",
    "/api/v1/report/generate": "post",
    "/api/v1/explanation/generate": "post",
    "/api/v1/question/answer": "post",
    "/api/v1/follow-up/recommend": "post",
    "/api/v1/analyze-complete": "post",
    "/api/v1/predictions/{prediction_id}": "get",
}

EXPECTED_RESPONSE_SCHEMAS = {
    ("/health", "get"): "HealthResponse",
    ("/api/v1/model/info", "get"): "ModelInfoResponse",
    ("/api/v1/model/metrics", "get"): "ModelMetricsResponse",
    (
        "/api/v1/llmops/metrics",
        "get",
    ): "OperationalMetricsResponse",
    (
        "/api/v1/image/classify",
        "post",
    ): "ClassificationResponse",
    (
        "/api/v1/image/analyze",
        "post",
    ): "ImageAnalysisResponse",
    (
        "/api/v1/report/generate",
        "post",
    ): "LanguageGenerationResponse",
    (
        "/api/v1/explanation/generate",
        "post",
    ): "LanguageGenerationResponse",
    (
        "/api/v1/question/answer",
        "post",
    ): "LanguageGenerationResponse",
    (
        "/api/v1/follow-up/recommend",
        "post",
    ): "LanguageGenerationResponse",
    (
        "/api/v1/analyze-complete",
        "post",
    ): "CompleteAnalysisResponse",
    (
        "/api/v1/predictions/{prediction_id}",
        "get",
    ): "StoredPredictionResponse",
}


@pytest.fixture(scope="module")
def openapi_schema() -> dict[str, Any]:
    return app.openapi()


def response_schema_name(
    operation: dict[str, Any],
) -> str:
    response_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]

    reference = response_schema.get("$ref")

    if reference is not None:
        return reference.rsplit("/", maxsplit=1)[-1]

    for composition_key in (
        "allOf",
        "anyOf",
        "oneOf",
    ):
        entries = response_schema.get(
            composition_key,
            [],
        )

        for entry in entries:
            reference = entry.get("$ref")

            if reference is not None:
                return reference.rsplit(
                    "/",
                    maxsplit=1,
                )[-1]

    raise AssertionError(
        "The successful response does not reference "
        "a named OpenAPI component schema."
    )


def test_exact_path_and_method_contract(
    openapi_schema: dict[str, Any],
) -> None:
    paths = openapi_schema["paths"]

    assert set(paths) == set(EXPECTED_OPERATIONS)

    for path, expected_method in EXPECTED_OPERATIONS.items():
        registered_methods = {
            method.lower()
            for method in paths[path]
            if method.lower()
            in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
            }
        }

        assert registered_methods == {expected_method}


def test_success_response_schema_bindings(
    openapi_schema: dict[str, Any],
) -> None:
    for (
        path,
        method,
    ), expected_schema in EXPECTED_RESPONSE_SCHEMAS.items():
        operation = openapi_schema["paths"][path][method]

        assert response_schema_name(operation) == expected_schema


@pytest.mark.parametrize(
    ("path", "expected_media_type"),
    [
        (
            "/api/v1/image/classify",
            "multipart/form-data",
        ),
        (
            "/api/v1/image/analyze",
            "multipart/form-data",
        ),
        (
            "/api/v1/analyze-complete",
            "multipart/form-data",
        ),
        (
            "/api/v1/report/generate",
            "application/json",
        ),
        (
            "/api/v1/explanation/generate",
            "application/json",
        ),
        (
            "/api/v1/question/answer",
            "application/json",
        ),
        (
            "/api/v1/follow-up/recommend",
            "application/json",
        ),
    ],
)
def test_request_media_type_contract(
    openapi_schema: dict[str, Any],
    path: str,
    expected_media_type: str,
) -> None:
    request_content = openapi_schema["paths"][path]["post"]["requestBody"]["content"]

    assert expected_media_type in request_content


def test_operation_ids_and_prediction_identifier(
    openapi_schema: dict[str, Any],
) -> None:
    operation_ids = [
        openapi_schema["paths"][path][method]["operationId"]
        for path, method in EXPECTED_OPERATIONS.items()
    ]

    assert len(operation_ids) == 12
    assert len(set(operation_ids)) == 12
    assert all(operation_ids)

    prediction_operation = openapi_schema["paths"][
        "/api/v1/predictions/{prediction_id}"
    ]["get"]

    prediction_parameters = {
        parameter["name"]: parameter for parameter in prediction_operation["parameters"]
    }

    prediction_id = prediction_parameters["prediction_id"]

    assert prediction_id["in"] == "path"
    assert prediction_id["required"] is True
    assert prediction_id["schema"]["format"] == "uuid"
