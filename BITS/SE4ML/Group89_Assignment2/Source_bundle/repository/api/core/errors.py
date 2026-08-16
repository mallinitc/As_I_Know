"""Typed client-safe exceptions for API services."""

from typing import Any

SENSITIVE_DETAIL_TERMS = {
    "traceback",
    "stack_trace",
    "filesystem_path",
    "file_path",
    "model_path",
    "internal_exception",
}


def sanitize_client_details(
    details: dict[str, Any] | None,
) -> dict[str, Any]:
    """Remove internal paths and exception details from public errors."""

    if not details:
        return {}

    sanitized_details: dict[str, Any] = {}

    for key, value in details.items():
        normalized_key = key.lower()

        if any(
            sensitive_term in normalized_key
            for sensitive_term in SENSITIVE_DETAIL_TERMS
        ):
            continue

        if isinstance(value, dict):
            sanitized_details[key] = sanitize_client_details(value)
        elif isinstance(value, (list, tuple)):
            sanitized_details[key] = [
                item
                for item in value
                if not (
                    isinstance(item, str)
                    and item.startswith(("/home/", "/root/", "/workspace/"))
                )
            ]
        elif isinstance(value, str) and value.startswith(
            ("/home/", "/root/", "/workspace/")
        ):
            continue
        elif (
            isinstance(
                value,
                (str, int, float, bool),
            )
            or value is None
        ):
            sanitized_details[key] = value
        else:
            sanitized_details[key] = str(value)

    return sanitized_details


class ServiceError(Exception):
    """Base exception with a stable public error contract."""

    status_code = 500
    error_code = "SERVICE_ERROR"
    default_message = "The service could not complete the request."

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = sanitize_client_details(details)
        super().__init__(self.message)


class InvalidImageError(ServiceError):
    status_code = 400
    error_code = "INVALID_IMAGE"
    default_message = "The uploaded content is not a valid image."


class UnsupportedMediaTypeError(ServiceError):
    status_code = 415
    error_code = "UNSUPPORTED_MEDIA_TYPE"
    default_message = "The uploaded image media type is not supported."


class UploadTooLargeError(ServiceError):
    status_code = 413
    error_code = "UPLOAD_TOO_LARGE"
    default_message = "The uploaded image exceeds the permitted size."


class PredictionNotFoundError(ServiceError):
    status_code = 404
    error_code = "PREDICTION_NOT_FOUND"
    default_message = "The requested prediction was not found."


class ModelNotReadyError(ServiceError):
    status_code = 503
    error_code = "MODEL_NOT_READY"
    default_message = "A required model service is not ready."


class GroundingContractError(ServiceError):
    status_code = 500
    error_code = "GROUNDING_CONTRACT_VIOLATION"
    default_message = "The generated output did not satisfy the grounding contract."


class ServiceExecutionError(ServiceError):
    status_code = 500
    error_code = "SERVICE_EXECUTION_ERROR"
    default_message = "The service encountered an internal execution failure."
