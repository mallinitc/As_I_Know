"""Memory-mapped ChestMNIST data access and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

SplitName = Literal["train", "val", "test"]

EXPECTED_SPLIT_COUNTS: dict[str, int] = {
    "train": 78_468,
    "val": 11_219,
    "test": 22_433,
}
IMAGE_SIZE = 224
NUM_LABELS = 14


@dataclass(frozen=True)
class SplitArrayPaths:
    """Filesystem locations for one persisted split."""

    images: Path
    labels: Path


@dataclass(frozen=True)
class SplitValidationResult:
    """Observed contract for one memory-mapped split."""

    split: str
    image_shape: tuple[int, ...]
    label_shape: tuple[int, ...]
    image_dtype: str
    label_dtype: str
    images_memory_mapped: bool
    labels_memory_mapped: bool
    binary_labels_valid: bool
    passed: bool


class ChestMNISTDataRepository:
    """Open and validate fixed ChestMNIST partitions."""

    valid_splits = frozenset(
        EXPECTED_SPLIT_COUNTS
    )

    def __init__(
        self,
        data_root: str | Path,
    ) -> None:
        self.data_root = Path(
            data_root
        ).expanduser().resolve()

        if not self.data_root.is_dir():
            raise FileNotFoundError(
                "ChestMNIST memory-map directory "
                f"does not exist: {self.data_root}"
            )

    def validate_split_name(
        self,
        split: str,
    ) -> SplitName:
        """Validate and return a canonical split name."""
        if split not in self.valid_splits:
            raise ValueError(
                f"Unsupported split: {split}. "
                "Expected train, val, or test."
            )

        return split  # type: ignore[return-value]

    def array_paths(
        self,
        split: str,
    ) -> SplitArrayPaths:
        """Resolve the two persisted arrays for one split."""
        canonical_split = (
            self.validate_split_name(split)
        )

        paths = SplitArrayPaths(
            images=(
                self.data_root
                / f"{canonical_split}_images.npy"
            ),
            labels=(
                self.data_root
                / f"{canonical_split}_labels.npy"
            ),
        )

        missing_paths = [
            str(path)
            for path in (
                paths.images,
                paths.labels,
            )
            if not path.is_file()
        ]

        if missing_paths:
            raise FileNotFoundError(
                "Missing ChestMNIST split artifacts: "
                + ", ".join(missing_paths)
            )

        return paths

    def open_split(
        self,
        split: str,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Open image and label arrays without loading them."""
        paths = self.array_paths(split)

        images = np.load(
            paths.images,
            mmap_mode="r",
            allow_pickle=False,
        )
        labels = np.load(
            paths.labels,
            mmap_mode="r",
            allow_pickle=False,
        )

        return images, labels

    def validate_arrays(
        self,
        split: str,
        images: np.ndarray,
        labels: np.ndarray,
    ) -> SplitValidationResult:
        """Validate shape, dtype, mapping, and label values."""
        canonical_split = (
            self.validate_split_name(split)
        )
        expected_count = EXPECTED_SPLIT_COUNTS[
            canonical_split
        ]
        expected_image_shape = (
            expected_count,
            IMAGE_SIZE,
            IMAGE_SIZE,
        )
        expected_label_shape = (
            expected_count,
            NUM_LABELS,
        )

        binary_labels_valid = bool(
            np.logical_or(
                labels == 0,
                labels == 1,
            ).all()
        )

        passed = bool(
            images.shape
            == expected_image_shape
            and labels.shape
            == expected_label_shape
            and images.dtype == np.uint8
            and labels.dtype == np.uint8
            and isinstance(images, np.memmap)
            and isinstance(labels, np.memmap)
            and len(images) == len(labels)
            and binary_labels_valid
        )

        return SplitValidationResult(
            split=canonical_split,
            image_shape=tuple(images.shape),
            label_shape=tuple(labels.shape),
            image_dtype=str(images.dtype),
            label_dtype=str(labels.dtype),
            images_memory_mapped=isinstance(
                images,
                np.memmap,
            ),
            labels_memory_mapped=isinstance(
                labels,
                np.memmap,
            ),
            binary_labels_valid=(
                binary_labels_valid
            ),
            passed=passed,
        )

    def validate_split(
        self,
        split: str,
    ) -> SplitValidationResult:
        """Open and validate one persisted partition."""
        images, labels = self.open_split(
            split
        )

        try:
            return self.validate_arrays(
                split,
                images,
                labels,
            )
        finally:
            del images
            del labels

    def validate_all(
        self,
    ) -> tuple[SplitValidationResult, ...]:
        """Validate all fixed partitions."""
        return tuple(
            self.validate_split(split)
            for split in (
                "train",
                "val",
                "test",
            )
        )


class ChestMNISTMemmapDataset(Dataset):
    """PyTorch dataset backed by read-only NumPy maps."""

    def __init__(
        self,
        data_root: str | Path,
        split: str,
        transform: Callable[
            [Image.Image],
            Any,
        ]
        | None = None,
    ) -> None:
        self.repository = (
            ChestMNISTDataRepository(
                data_root
            )
        )
        self.split = (
            self.repository
            .validate_split_name(split)
        )
        self.transform = transform
        self.images, self.labels = (
            self.repository.open_split(
                self.split
            )
        )

        validation = (
            self.repository.validate_arrays(
                self.split,
                self.images,
                self.labels,
            )
        )

        if not validation.passed:
            raise ValueError(
                "ChestMNIST split contract failed "
                f"for {self.split}: {validation}"
            )

    def __len__(self) -> int:
        return int(len(self.images))

    def __getitem__(
        self,
        index: int,
    ) -> tuple[Any, torch.Tensor, int]:
        if not 0 <= index < len(self):
            raise IndexError(
                f"Dataset index out of range: {index}"
            )

        image_array = np.asarray(
            self.images[index],
            dtype=np.uint8,
        )
        image = Image.fromarray(
            image_array
        ).convert("RGB")

        if self.transform is not None:
            image = self.transform(image)

        target = torch.tensor(
            np.asarray(
                self.labels[index],
                dtype=np.float32,
            ),
            dtype=torch.float32,
        )

        return image, target, int(index)
