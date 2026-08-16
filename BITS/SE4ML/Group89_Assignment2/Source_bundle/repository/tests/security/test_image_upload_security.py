"""Security tests for the image-upload boundary."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from api.core.errors import (
    InvalidImageError,
    UnsupportedMediaTypeError,
    UploadTooLargeError,
)
from src.services.image_service import ImageValidationService


def encoded_image(
    *,
    image_format: str,
    size: tuple[int, int] = (32, 32),
) -> bytes:
    """Create deterministic encoded image content."""
    image = Image.new(
        mode="RGB",
        size=size,
        color=(32, 64, 96),
    )
    buffer = BytesIO()
    image.save(
        buffer,
        format=image_format,
    )
    return buffer.getvalue()


def test_empty_upload_is_rejected() -> None:
    service = ImageValidationService()

    with pytest.raises(InvalidImageError) as error:
        service.validate_and_decode(
            filename="empty.png",
            media_type="image/png",
            content=b"",
        )

    assert error.value.error_code == ("INVALID_IMAGE")
    assert "empty.png" not in str(error.value.details)


def test_malformed_upload_is_rejected() -> None:
    service = ImageValidationService()
    malformed_content = b"not-a-valid-image-payload"

    with pytest.raises(InvalidImageError) as error:
        service.validate_and_decode(
            filename="malformed.png",
            media_type="image/png",
            content=malformed_content,
        )

    assert malformed_content.decode() not in str(error.value.details)


def test_spoofed_media_type_is_rejected() -> None:
    service = ImageValidationService()
    jpeg_content = encoded_image(image_format="JPEG")

    with pytest.raises(UnsupportedMediaTypeError) as error:
        service.validate_and_decode(
            filename="spoofed.png",
            media_type="image/png",
            content=jpeg_content,
        )

    assert error.value.details["declared_media_type"] == "image/png"
    assert error.value.details["detected_format"] == "JPEG"


def test_oversized_payload_is_rejected_before_decode() -> None:
    service = ImageValidationService()
    maximum_bytes = service.settings.maximum_upload_bytes
    oversized_content = b"x" * (maximum_bytes + 1)

    with pytest.raises(UploadTooLargeError) as error:
        service.validate_and_decode(
            filename="oversized.png",
            media_type="image/png",
            content=oversized_content,
        )

    assert error.value.details["received_bytes"] == maximum_bytes + 1
    assert error.value.details["maximum_bytes"] == maximum_bytes


def test_excessive_dimensions_are_rejected() -> None:
    service = ImageValidationService()
    wide_content = encoded_image(
        image_format="PNG",
        size=(4097, 1),
    )

    with pytest.raises(InvalidImageError) as error:
        service.validate_and_decode(
            filename="wide.png",
            media_type="image/png",
            content=wide_content,
        )

    assert error.value.details["width"] == 4097
    assert error.value.details["maximum_width"] == 4096


def test_path_traversal_filename_is_sanitized() -> None:
    service = ImageValidationService()
    png_content = encoded_image(image_format="PNG")

    result = service.validate_and_decode(
        filename=("../../../../private/" "patient-image.png"),
        media_type="image/png",
        content=png_content,
    )

    assert result.filename == ("patient-image.png")
    assert "/" not in result.filename
    assert "\\" not in result.filename
    assert result.rgb_image.mode == "RGB"
