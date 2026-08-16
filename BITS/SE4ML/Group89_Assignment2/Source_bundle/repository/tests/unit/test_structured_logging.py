"""Runtime tests for structured service logging."""

from __future__ import annotations

import logging
from io import BytesIO

import pytest
import torch
from PIL import Image

from api.core.errors import (
    InvalidImageError,
    ModelNotReadyError,
    UnsupportedMediaTypeError,
)
from src.services.computer_vision_service import ComputerVisionService
from src.services.image_service import ImageValidationService
from src.services.language_guardrail_service import DeterministicLanguageGuardrail


def build_png_bytes() -> bytes:
    """Create a deterministic in-memory PNG fixture."""
    image = Image.new(
        mode="RGB",
        size=(16, 16),
        color=(64, 96, 128),
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def event_records(
    caplog: pytest.LogCaptureFixture,
    component: str,
) -> list[logging.LogRecord]:
    """Return structured records for one component."""
    return [
        record
        for record in caplog.records
        if getattr(record, "component", None) == component
    ]


def test_image_validation_logs_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A valid image emits start and completion events."""
    service = ImageValidationService()
    payload = build_png_bytes()

    caplog.set_level(
        logging.INFO,
        logger=("src.services.image_service"),
    )

    result = service.validate_and_decode(
        filename="../../private-image.png",
        media_type="image/png",
        content=payload,
    )

    records = event_records(
        caplog,
        "image_validation",
    )
    events = {getattr(record, "event", None) for record in records}

    assert result.width == 16
    assert result.height == 16
    assert result.filename == "private-image.png"
    assert "validation_started" in events
    assert "validation_completed" in events
    assert payload.hex() not in caplog.text
    assert "../../private-image.png" not in caplog.text


def test_image_validation_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unsupported content types emit a warning event."""
    service = ImageValidationService()

    caplog.set_level(
        logging.WARNING,
        logger=("src.services.image_service"),
    )

    with pytest.raises(UnsupportedMediaTypeError):
        service.validate_and_decode(
            filename="upload.pdf",
            media_type="application/pdf",
            content=b"controlled-input",
        )

    records = event_records(
        caplog,
        "image_validation",
    )

    assert any(
        record.levelno == logging.WARNING
        and getattr(record, "event", None) == "unsupported_media_type"
        for record in records
    )
    assert "upload.pdf" not in caplog.text
    assert "controlled-input" not in caplog.text


def test_image_validation_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed image content emits an error event."""
    service = ImageValidationService()

    caplog.set_level(
        logging.ERROR,
        logger=("src.services.image_service"),
    )

    with pytest.raises(InvalidImageError):
        service.validate_and_decode(
            filename="malformed.png",
            media_type="image/png",
            content=b"not-a-valid-image",
        )

    records = event_records(
        caplog,
        "image_validation",
    )

    assert any(
        record.levelno == logging.ERROR
        and getattr(record, "event", None) == "decoding_failed"
        for record in records
    )
    assert "malformed.png" not in caplog.text
    assert "not-a-valid-image" not in caplog.text


def test_cv_unavailable_logs_lifecycle(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unavailable model emits start and warning events."""
    service = object.__new__(ComputerVisionService)
    service.device = torch.device("cpu")
    service._ready = False
    service.model = None

    caplog.set_level(
        logging.INFO,
        logger=("src.services." "computer_vision_service"),
    )

    with pytest.raises(ModelNotReadyError):
        service.predict(None)

    records = event_records(
        caplog,
        "computer_vision",
    )
    events = {getattr(record, "event", None) for record in records}

    assert "inference_started" in events
    assert "model_unavailable" in events
    assert any(record.levelno == logging.WARNING for record in records)


def test_guardrail_failure_logs_error(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An audit failure is logged and propagated unchanged."""
    guardrail = object.__new__(DeterministicLanguageGuardrail)

    def fail_audit(**_: object) -> object:
        raise RuntimeError("controlled-guardrail-failure")

    monkeypatch.setattr(
        guardrail,
        "audit",
        fail_audit,
    )

    private_generated_text = "private generated language"
    private_question = "private user question"

    caplog.set_level(
        logging.INFO,
        logger=("src.services." "language_guardrail_service"),
    )

    with pytest.raises(
        RuntimeError,
        match="controlled-guardrail-failure",
    ):
        guardrail.apply(
            task_type="structured_report",
            raw_generated_text=(private_generated_text),
            findings=(),
            no_target_finding=True,
            user_question=private_question,
        )

    records = event_records(
        caplog,
        "language_guardrail",
    )
    events = {getattr(record, "event", None) for record in records}

    assert "evaluation_started" in events
    assert "evaluation_failed" in events
    assert any(record.levelno == logging.ERROR for record in records)
    assert private_generated_text not in caplog.text
    assert private_question not in caplog.text


def test_guardrail_fallback_logs_warning(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deterministic fallback emits a warning and completion."""
    guardrail = object.__new__(DeterministicLanguageGuardrail)

    monkeypatch.setattr(
        guardrail,
        "audit",
        lambda **_: (
            None,
            ("safety_boundary_issue",),
            None,
        ),
    )
    monkeypatch.setattr(
        guardrail,
        "build_fallback",
        lambda **_: ("Deterministic safe fallback."),
    )

    caplog.set_level(
        logging.INFO,
        logger=("src.services." "language_guardrail_service"),
    )

    result = guardrail.apply(
        task_type="structured_report",
        raw_generated_text=("unsupported generated output"),
        findings=(),
        no_target_finding=True,
    )

    records = event_records(
        caplog,
        "language_guardrail",
    )
    events = {getattr(record, "event", None) for record in records}

    assert result.guardrail_action == (guardrail.FALLBACK_ACTION)
    assert result.final_text == ("Deterministic safe fallback.")
    assert "fallback_activated" in events
    assert "evaluation_completed" in events
    assert any(record.levelno == logging.WARNING for record in records)
    assert "unsupported generated output" not in caplog.text
