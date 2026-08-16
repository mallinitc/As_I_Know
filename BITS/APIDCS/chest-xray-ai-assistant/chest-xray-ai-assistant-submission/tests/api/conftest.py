
"""Shared fixtures for FastAPI integration tests."""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.main import app


@pytest.fixture(
    scope="session"
)
def client():
    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as test_client:
        yield test_client


@pytest.fixture(
    scope="session"
)
def valid_png_bytes():
    horizontal = np.linspace(
        32,
        224,
        224,
        dtype=np.uint8,
    )

    image_array = np.tile(
        horizontal,
        (224, 1),
    )

    image = Image.fromarray(
        image_array,
        mode="L",
    )

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG",
    )

    return buffer.getvalue()


@pytest.fixture(
    scope="session"
)
def classification_payload(
    client,
    valid_png_bytes,
):
    response = client.post(
        "/api/v1/image/classify",
        files={
            "image": (
                "pytest-classification.png",
                valid_png_bytes,
                "image/png",
            )
        },
    )

    assert response.status_code == 200

    return response.json()
