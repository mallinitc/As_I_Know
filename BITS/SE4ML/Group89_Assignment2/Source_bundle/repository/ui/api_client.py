from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import httpx

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 120.0


class APIClientError(RuntimeError):
    """Controlled error exposed by the UI HTTP boundary."""

    def __init__(
        self,
        *,
        message: str,
        error_code: str,
        status_code: int | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.request_id = request_id
        self.details = details or {}

    def to_display_dict(self) -> dict[str, Any]:
        """Return safe structured details for Streamlit rendering."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "status_code": self.status_code,
            "request_id": self.request_id,
            "details": self.details,
        }


class ChestXRayAPIClient:
    """HTTP-only client for the persisted FastAPI application."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        resolved_base_url = (
            (
                base_url
                or os.getenv(
                    "CHEST_XRAY_API_BASE_URL",
                    DEFAULT_API_BASE_URL,
                )
            )
            .strip()
            .rstrip("/")
        )

        if not resolved_base_url:
            raise ValueError("The API base URL cannot be blank.")

        if timeout_seconds <= 0:
            raise ValueError("The HTTP timeout must be greater than zero.")

        self.base_url = resolved_base_url
        self.timeout_seconds = float(timeout_seconds)

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )

    @staticmethod
    def _decode_json_response(
        response: httpx.Response,
    ) -> dict[str, Any] | None:
        """Decode JSON only when the response declares JSON content."""
        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if "application/json" not in content_type:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        return payload if isinstance(payload, dict) else None

    def _request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute one request and enforce a UI-safe JSON boundary."""
        try:
            response = self._client.request(
                method=method,
                url=path,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise APIClientError(
                error_code="API_TIMEOUT",
                message=(
                    "The backend did not respond within the " "configured time limit."
                ),
            ) from exc
        except httpx.RequestError as exc:
            raise APIClientError(
                error_code="API_UNAVAILABLE",
                message=("The FastAPI backend is currently unavailable."),
            ) from exc

        payload = self._decode_json_response(response)

        if not 200 <= response.status_code < 300:
            if payload is not None:
                error_code = str(
                    payload.get(
                        "error_code",
                        "API_REQUEST_FAILED",
                    )
                )
                message = str(
                    payload.get(
                        "message",
                        "The API request could not be completed.",
                    )
                )
                request_id_value = payload.get("request_id")
                details_value = payload.get("details")

                raise APIClientError(
                    error_code=error_code,
                    message=message,
                    status_code=response.status_code,
                    request_id=(
                        str(request_id_value) if request_id_value is not None else None
                    ),
                    details=(details_value if isinstance(details_value, dict) else {}),
                )

            raise APIClientError(
                error_code="NON_JSON_API_ERROR",
                message=(
                    "The backend returned an unexpected " "non-JSON error response."
                ),
                status_code=response.status_code,
            )

        if payload is None:
            raise APIClientError(
                error_code="INVALID_API_RESPONSE",
                message=(
                    "The backend returned an invalid or " "non-JSON success response."
                ),
                status_code=response.status_code,
            )

        return payload

    def health(self) -> dict[str, Any]:
        return self._request_json(
            "GET",
            "/health",
        )

    def model_info(self) -> dict[str, Any]:
        return self._request_json(
            "GET",
            "/api/v1/model/info",
        )

    def model_metrics(self) -> dict[str, Any]:
        return self._request_json(
            "GET",
            "/api/v1/model/metrics",
        )

    def analyze_complete(
        self,
        *,
        filename: str,
        media_type: str,
        image_content: bytes,
        question: str | None = None,
    ) -> dict[str, Any]:
        if not filename.strip():
            raise ValueError("The image filename cannot be blank.")

        if not media_type.strip():
            raise ValueError("The image media type cannot be blank.")

        if not image_content:
            raise ValueError("The uploaded image cannot be empty.")

        files = {
            "image": (
                filename,
                image_content,
                media_type,
            )
        }

        data: dict[str, str] = {}

        if question is not None and question.strip():
            data["question"] = question.strip()

        return self._request_json(
            "POST",
            "/api/v1/analyze-complete",
            files=files,
            data=data,
        )

    def answer_question(
        self,
        *,
        prediction_id: str | UUID,
        question: str,
    ) -> dict[str, Any]:
        normalized_question = question.strip()

        if not normalized_question:
            raise ValueError("The question cannot be blank.")

        return self._request_json(
            "POST",
            "/api/v1/question/answer",
            json={
                "prediction_id": str(prediction_id),
                "question": normalized_question,
            },
        )

    def get_prediction(
        self,
        prediction_id: str | UUID,
    ) -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"/api/v1/predictions/{prediction_id}",
        )

    def llmops_metrics(self) -> dict[str, Any]:
        return self._request_json(
            "GET",
            "/api/v1/llmops/metrics",
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ChestXRayAPIClient":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()
