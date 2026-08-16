"""Secure validation and decoding for uploaded images."""

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from api.core.config import ServiceSettings, get_settings
from api.core.errors import (
    InvalidImageError,
    UnsupportedMediaTypeError,
    UploadTooLargeError,
)
from api.schemas.prediction import ImageMetadata


MAXIMUM_IMAGE_WIDTH = 4096
MAXIMUM_IMAGE_HEIGHT = 4096
MAXIMUM_IMAGE_PIXELS = (
    MAXIMUM_IMAGE_WIDTH
    * MAXIMUM_IMAGE_HEIGHT
)

MEDIA_TYPE_TO_FORMAT = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
}


@dataclass
class ValidatedImage:
    """Decoded image and its client-safe metadata."""

    filename: str
    media_type: str
    original_mode: str
    width: int
    height: int
    sha256: str
    rgb_image: Image.Image

    def response_metadata(
        self,
    ) -> ImageMetadata:
        """Build the strict image response metadata."""

        return ImageMetadata(
            filename=self.filename,
            media_type=self.media_type,
            width=self.width,
            height=self.height,
            original_mode=self.original_mode,
            sha256=self.sha256,
        )


class ImageValidationService:
    """Validate upload boundaries and decode safe RGB content."""

    def __init__(
        self,
        settings: ServiceSettings | None = None,
    ) -> None:
        self.settings = (
            settings or get_settings()
        )

    def validate_and_decode(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> ValidatedImage:
        """Validate one upload and return decoded RGB image content."""

        if media_type not in (
            self.settings
            .supported_image_media_types
        ):
            raise UnsupportedMediaTypeError(
                details={
                    "received_media_type": media_type,
                    "supported_media_types": list(
                        self.settings
                        .supported_image_media_types
                    ),
                }
            )

        if not content:
            raise InvalidImageError(
                details={
                    "reason": (
                        "The uploaded file is empty."
                    )
                }
            )

        if len(content) > (
            self.settings
            .maximum_upload_bytes
        ):
            raise UploadTooLargeError(
                details={
                    "received_bytes": len(content),
                    "maximum_bytes": (
                        self.settings
                        .maximum_upload_bytes
                    ),
                }
            )

        safe_filename = (
            Path(filename).name.strip()
            if filename
            else "uploaded-image"
        )

        if not safe_filename:
            safe_filename = "uploaded-image"

        try:
            with Image.open(
                BytesIO(content)
            ) as verification_image:
                detected_format = (
                    verification_image.format
                )
                verification_image.verify()

            with Image.open(
                BytesIO(content)
            ) as decoded_image:
                decoded_image.load()

                width, height = (
                    decoded_image.size
                )
                original_mode = (
                    decoded_image.mode
                )
                rgb_image = (
                    decoded_image.convert(
                        "RGB"
                    )
                )

        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
        ) as error:
            raise InvalidImageError(
                details={
                    "reason": (
                        "Image decoding or integrity "
                        "validation failed."
                    )
                }
            ) from error

        expected_format = (
            MEDIA_TYPE_TO_FORMAT[
                media_type
            ]
        )

        if detected_format != expected_format:
            raise UnsupportedMediaTypeError(
                message=(
                    "The declared media type does not "
                    "match the decoded image format."
                ),
                details={
                    "declared_media_type": media_type,
                    "detected_format": (
                        detected_format
                    ),
                },
            )

        if (
            width <= 0
            or height <= 0
            or width > MAXIMUM_IMAGE_WIDTH
            or height > MAXIMUM_IMAGE_HEIGHT
            or width * height
            > MAXIMUM_IMAGE_PIXELS
        ):
            raise InvalidImageError(
                details={
                    "reason": (
                        "Image dimensions exceed "
                        "the supported boundary."
                    ),
                    "width": width,
                    "height": height,
                    "maximum_width": (
                        MAXIMUM_IMAGE_WIDTH
                    ),
                    "maximum_height": (
                        MAXIMUM_IMAGE_HEIGHT
                    ),
                }
            )

        return ValidatedImage(
            filename=safe_filename,
            media_type=media_type,
            original_mode=original_mode,
            width=width,
            height=height,
            sha256=hashlib.sha256(
                content
            ).hexdigest(),
            rgb_image=rgb_image,
        )
