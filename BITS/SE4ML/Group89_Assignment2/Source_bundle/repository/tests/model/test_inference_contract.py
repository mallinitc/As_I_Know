"""Inference contracts and research-production parity."""

from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
import torch
import torch.nn as nn
import yaml
from PIL import Image
from torchvision import models, transforms

from api.core.errors import InvalidImageError
from src.services.computer_vision_service import ComputerVisionService
from src.services.image_service import ImageValidationService, ValidatedImage

IMAGENET_MEAN = (
    0.485,
    0.456,
    0.406,
)
IMAGENET_STANDARD_DEVIATION = (
    0.229,
    0.224,
    0.225,
)


def png_bytes(
    image: Image.Image,
) -> bytes:
    """Serialize one image without filesystem storage."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def canonical_labels() -> tuple[str, ...]:
    config_path = Path(os.environ["CHESTMNIST_CONFIG_PATH"])
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    label_map = config["dataset"]["labels"]

    return tuple(
        label_map[index]
        for index in sorted(
            label_map,
            key=int,
        )
    )


@pytest.fixture(scope="module")
def validated_image() -> ValidatedImage:
    memmap_root = Path(os.environ["CHESTMNIST_MEMMAP_ROOT"])
    test_images = np.load(
        memmap_root / "test_images.npy",
        mmap_mode="r",
        allow_pickle=False,
    )
    image_array = np.array(
        test_images[0],
        copy=True,
    )
    del test_images

    image = Image.fromarray(image_array).convert("RGB")

    validation_service = ImageValidationService()

    return validation_service.validate_and_decode(
        filename="parity-input.png",
        media_type="image/png",
        content=png_bytes(image),
    )


@pytest.fixture(scope="module")
def production_service() -> ComputerVisionService:
    service = ComputerVisionService(device="cpu")

    assert service.is_ready
    return service


def research_style_probabilities(
    validated_image: ValidatedImage,
) -> np.ndarray:
    """Execute the original inline inference pattern."""
    model = models.resnet18(weights=None)
    model.fc = nn.Sequential(
        nn.Dropout(p=0.2),
        nn.Linear(
            model.fc.in_features,
            14,
        ),
    )

    checkpoint = torch.load(
        Path(os.environ["CHESTMNIST_MODEL_STATE"]),
        map_location="cpu",
        weights_only=True,
    )

    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        state_dict = checkpoint["model_state_dict"]
    else:
        state_dict = checkpoint

    model.load_state_dict(
        state_dict,
        strict=True,
    )
    model.eval()

    preprocessing = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=IMAGENET_MEAN,
                std=(IMAGENET_STANDARD_DEVIATION),
            ),
        ]
    )

    input_tensor = preprocessing(validated_image.rgb_image).unsqueeze(0)

    with torch.inference_mode():
        logits = model(input_tensor)
        probabilities = torch.sigmoid(logits)

    result = probabilities[0].detach().cpu().numpy().astype(np.float64)

    del model
    return result


def test_output_shape_range_and_finiteness(
    production_service: ComputerVisionService,
    validated_image: ValidatedImage,
) -> None:
    result = production_service.predict(validated_image)

    assert result.probabilities.shape == (14,)
    assert tuple(result.logits.shape) == (
        1,
        14,
    )
    assert np.isfinite(result.probabilities).all()
    assert np.logical_and(
        result.probabilities >= 0.0,
        result.probabilities <= 1.0,
    ).all()


def test_inference_is_deterministic(
    production_service: ComputerVisionService,
    validated_image: ValidatedImage,
) -> None:
    first = production_service.predict(validated_image)
    second = production_service.predict(validated_image)

    np.testing.assert_array_equal(
        first.probabilities,
        second.probabilities,
    )
    torch.testing.assert_close(
        first.logits,
        second.logits,
        rtol=0.0,
        atol=0.0,
    )


def test_label_and_threshold_order(
    production_service: ComputerVisionService,
    validated_image: ValidatedImage,
    canonical_labels: tuple[str, ...],
) -> None:
    metadata_path = Path(os.environ["CHESTMNIST_MODEL_METADATA"])
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))

    model_label_map = metadata["output_contract"]["labels"]
    model_labels = tuple(
        model_label_map[index]
        for index in sorted(
            model_label_map,
            key=int,
        )
    )
    model_threshold_map = metadata["output_contract"]["thresholds"]

    result = production_service.predict(validated_image)

    result_labels = tuple(finding.label_name for finding in result.findings)
    result_thresholds = np.asarray(
        [finding.frozen_threshold for finding in result.findings],
        dtype=np.float64,
    )
    expected_thresholds = np.asarray(
        [model_threshold_map[label] for label in canonical_labels],
        dtype=np.float64,
    )

    assert model_labels == canonical_labels
    assert result_labels == canonical_labels
    np.testing.assert_allclose(
        result_thresholds,
        expected_thresholds,
        rtol=0.0,
        atol=0.0,
    )


def test_threshold_decision_shape(
    production_service: ComputerVisionService,
    validated_image: ValidatedImage,
) -> None:
    result = production_service.predict(validated_image)

    decisions = np.asarray(
        [finding.crossed_threshold for finding in result.findings],
        dtype=bool,
    )
    thresholds = np.asarray(
        [finding.frozen_threshold for finding in result.findings],
        dtype=np.float64,
    )

    assert decisions.shape == (result.probabilities.shape)
    np.testing.assert_array_equal(
        decisions,
        result.probabilities >= thresholds,
    )


def test_invalid_inputs_are_controlled() -> None:
    service = ImageValidationService()

    with pytest.raises(InvalidImageError):
        service.validate_and_decode(
            filename="empty.png",
            media_type="image/png",
            content=b"",
        )

    with pytest.raises(InvalidImageError):
        service.validate_and_decode(
            filename="malformed.png",
            media_type="image/png",
            content=b"not-an-image",
        )

    oversized_dimension_image = Image.new(
        mode="L",
        size=(4097, 1),
        color=0,
    )

    with pytest.raises(InvalidImageError):
        service.validate_and_decode(
            filename="wide.png",
            media_type="image/png",
            content=png_bytes(oversized_dimension_image),
        )


def test_research_production_parity(
    production_service: ComputerVisionService,
    validated_image: ValidatedImage,
    canonical_labels: tuple[str, ...],
) -> None:
    research_probabilities = research_style_probabilities(validated_image)
    production_result = production_service.predict(validated_image)
    production_probabilities = production_result.probabilities.astype(np.float64)

    absolute_differences = np.abs(research_probabilities - production_probabilities)
    maximum_absolute_difference = float(absolute_differences.max())
    tolerance = 1e-6

    result = {
        "test_name": ("test_research_production_parity"),
        "execution_device": "cpu",
        "sample_split": "test",
        "sample_index": 0,
        "model_version": ("resnet18-chestmnist-v1"),
        "label_order": list(canonical_labels),
        "probability_shape": list(production_probabilities.shape),
        "absolute_tolerance": tolerance,
        "maximum_absolute_difference": (maximum_absolute_difference),
        "research_probabilities": (research_probabilities.tolist()),
        "production_probabilities": (production_probabilities.tolist()),
        "passed": (maximum_absolute_difference <= tolerance),
        "frozen_checkpoint_modified": False,
    }

    evidence_path = Path(os.environ["SE4ML_PARITY_EVIDENCE"])
    evidence_path.write_text(
        json.dumps(
            result,
            indent=2,
        ),
        encoding="utf-8",
    )

    np.testing.assert_allclose(
        research_probabilities,
        production_probabilities,
        rtol=0.0,
        atol=tolerance,
    )
