"""Data-contract and quality tests for ChestMNIST."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml
from torchvision import transforms

from src.data.chestmnist_dataset import (
    EXPECTED_SPLIT_COUNTS,
    ChestMNISTDataRepository,
    ChestMNISTMemmapDataset,
)
from src.data.quality_metrics import ChestMNISTQualityEvaluator


@pytest.fixture(scope="module")
def data_root() -> Path:
    return Path(os.environ["CHESTMNIST_MEMMAP_ROOT"])


@pytest.fixture(scope="module")
def label_names() -> tuple[str, ...]:
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


def test_required_split_contracts(
    data_root: Path,
) -> None:
    repository = ChestMNISTDataRepository(data_root)

    results = repository.validate_all()

    assert len(results) == 3
    assert all(result.passed for result in results)
    assert {
        result.split: result.image_shape[0] for result in results
    } == EXPECTED_SPLIT_COUNTS


def test_dataset_and_model_label_order_match(
    label_names: tuple[str, ...],
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

    assert len(label_names) == 14
    assert model_labels == label_names


def test_split_artifact_paths_are_isolated(
    data_root: Path,
) -> None:
    repository = ChestMNISTDataRepository(data_root)

    resolved_paths = {
        str(path.resolve())
        for split in (
            "train",
            "val",
            "test",
        )
        for path in (
            repository.array_paths(split).images,
            repository.array_paths(split).labels,
        )
    }

    assert len(resolved_paths) == 6


def test_preprocessing_is_deterministic(
    data_root: Path,
) -> None:
    transform = transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize(
                mean=(
                    0.485,
                    0.456,
                    0.406,
                ),
                std=(
                    0.229,
                    0.224,
                    0.225,
                ),
            ),
        ]
    )
    dataset = ChestMNISTMemmapDataset(
        data_root=data_root,
        split="test",
        transform=transform,
    )

    first_image, first_target, _ = dataset[0]
    second_image, second_target, _ = dataset[0]

    assert first_image.shape == (
        3,
        224,
        224,
    )
    assert first_target.shape == (14,)
    assert torch.isfinite(first_image).all()
    assert torch.equal(
        first_image,
        second_image,
    )
    assert torch.equal(
        first_target,
        second_target,
    )


def test_invalid_split_is_rejected(
    data_root: Path,
) -> None:
    repository = ChestMNISTDataRepository(data_root)

    with pytest.raises(
        ValueError,
        match="Unsupported split",
    ):
        repository.open_split("development")


def test_quality_metrics_pass(
    data_root: Path,
    label_names: tuple[str, ...],
) -> None:
    repository = ChestMNISTDataRepository(data_root)
    evaluator = ChestMNISTQualityEvaluator(
        repository=repository,
        label_names=label_names,
    )

    report = evaluator.evaluate()

    assert report.schema_validity_rate == 1.0
    assert report.missing_non_finite_rate == 0.0
    assert report.binary_label_validity_rate == 1.0
    assert report.split_artifact_isolation_rate == 1.0
    assert all(report.checks.values())
    assert np.isfinite(report.maximum_js_divergence)
