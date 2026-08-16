"""Aggregate quality metrics for persisted ChestMNIST data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Sequence

import numpy as np

from src.data.chestmnist_dataset import (
    EXPECTED_SPLIT_COUNTS,
    IMAGE_SIZE,
    NUM_LABELS,
    ChestMNISTDataRepository,
)


@dataclass(frozen=True)
class DataQualityReport:
    """Measured quality and drift evidence."""

    schema_validity_rate: float
    missing_non_finite_rate: float
    binary_label_validity_rate: float
    split_artifact_isolation_rate: float
    maximum_prevalence_shift: float
    maximum_shift_label: str
    maximum_shift_pair: str
    maximum_js_divergence: float
    maximum_js_pair: str
    prevalence_by_split: dict[
        str,
        list[float],
    ]
    js_divergence_by_pair: dict[
        str,
        float,
    ]
    thresholds: dict[str, float]
    checks: dict[str, bool]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class ChestMNISTQualityEvaluator:
    """Measure schema, validity, isolation, and drift."""

    def __init__(
        self,
        *,
        repository: ChestMNISTDataRepository,
        label_names: Sequence[str],
        chunk_size: int = 4096,
        maximum_prevalence_shift: float = 0.03,
        maximum_js_divergence: float = 0.01,
    ) -> None:
        if len(label_names) != NUM_LABELS:
            raise ValueError("Exactly fourteen label names are required.")

        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")

        self.repository = repository
        self.label_names = tuple(label_names)
        self.chunk_size = chunk_size
        self.thresholds = {
            "minimum_schema_validity_rate": 1.0,
            "maximum_missing_non_finite_rate": 0.0,
            "minimum_binary_label_validity_rate": 1.0,
            "minimum_split_artifact_isolation_rate": 1.0,
            "maximum_prevalence_shift": (maximum_prevalence_shift),
            "maximum_js_divergence": (maximum_js_divergence),
        }

    @staticmethod
    def _non_finite_count(
        array: np.ndarray,
        chunk_size: int,
    ) -> int:
        """Count non-finite values without materializing an array."""
        if np.issubdtype(
            array.dtype,
            np.integer,
        ) or np.issubdtype(
            array.dtype,
            np.bool_,
        ):
            return 0

        count = 0

        for start in range(
            0,
            len(array),
            chunk_size,
        ):
            chunk = np.asarray(array[start : start + chunk_size])
            count += int(np.size(chunk) - np.isfinite(chunk).sum())

        return count

    @staticmethod
    def _js_divergence(
        first: np.ndarray,
        second: np.ndarray,
    ) -> float:
        """Calculate Jensen-Shannon divergence."""
        first_distribution = first / first.sum()
        second_distribution = second / second.sum()
        midpoint = (first_distribution + second_distribution) / 2.0

        first_mask = first_distribution > 0.0
        second_mask = second_distribution > 0.0

        first_kl = np.sum(
            first_distribution[first_mask]
            * np.log(first_distribution[first_mask] / midpoint[first_mask])
        )
        second_kl = np.sum(
            second_distribution[second_mask]
            * np.log(second_distribution[second_mask] / midpoint[second_mask])
        )

        return float(0.5 * (first_kl + second_kl))

    def evaluate(
        self,
    ) -> DataQualityReport:
        """Evaluate all fixed partitions."""
        split_names = (
            "train",
            "val",
            "test",
        )

        schema_valid_artifacts = 0
        required_artifacts = 6
        total_elements = 0
        non_finite_elements = 0
        total_label_values = 0
        valid_binary_values = 0
        prevalence_by_split: dict[
            str,
            list[float],
        ] = {}
        resolved_artifacts: set[str] = set()

        for split in split_names:
            paths = self.repository.array_paths(split)
            resolved_artifacts.update(
                {
                    str(paths.images.resolve()),
                    str(paths.labels.resolve()),
                }
            )

            images, labels = self.repository.open_split(split)

            try:
                expected_count = EXPECTED_SPLIT_COUNTS[split]

                image_schema_valid = bool(
                    images.shape
                    == (
                        expected_count,
                        IMAGE_SIZE,
                        IMAGE_SIZE,
                    )
                    and images.dtype == np.uint8
                    and isinstance(
                        images,
                        np.memmap,
                    )
                )

                label_schema_valid = bool(
                    labels.shape
                    == (
                        expected_count,
                        NUM_LABELS,
                    )
                    and labels.dtype == np.uint8
                    and isinstance(
                        labels,
                        np.memmap,
                    )
                )

                schema_valid_artifacts += int(image_schema_valid)
                schema_valid_artifacts += int(label_schema_valid)

                total_elements += int(images.size + labels.size)
                non_finite_elements += self._non_finite_count(
                    images,
                    self.chunk_size,
                )
                non_finite_elements += self._non_finite_count(
                    labels,
                    self.chunk_size,
                )

                positive_counts = np.zeros(
                    NUM_LABELS,
                    dtype=np.int64,
                )

                for start in range(
                    0,
                    len(labels),
                    self.chunk_size,
                ):
                    label_chunk = np.asarray(labels[start : start + self.chunk_size])

                    binary_mask = np.logical_or(
                        label_chunk == 0,
                        label_chunk == 1,
                    )

                    valid_binary_values += int(binary_mask.sum())
                    total_label_values += int(label_chunk.size)
                    positive_counts += label_chunk.sum(
                        axis=0,
                        dtype=np.int64,
                    )

                prevalence_by_split[split] = (
                    positive_counts.astype(np.float64) / float(len(labels))
                ).tolist()

            finally:
                del images
                del labels

        schema_validity_rate = schema_valid_artifacts / required_artifacts
        missing_non_finite_rate = non_finite_elements / total_elements
        binary_label_validity_rate = valid_binary_values / total_label_values
        isolation_rate = len(resolved_artifacts) / required_artifacts

        maximum_shift = -1.0
        maximum_shift_label = ""
        maximum_shift_pair = ""
        js_by_pair: dict[str, float] = {}

        for first_split, second_split in combinations(split_names, 2):
            first_prevalence = np.asarray(
                prevalence_by_split[first_split],
                dtype=np.float64,
            )
            second_prevalence = np.asarray(
                prevalence_by_split[second_split],
                dtype=np.float64,
            )

            absolute_shift = np.abs(first_prevalence - second_prevalence)
            label_index = int(absolute_shift.argmax())
            pair_name = f"{first_split}_vs_" f"{second_split}"
            pair_maximum = float(absolute_shift[label_index])

            if pair_maximum > maximum_shift:
                maximum_shift = pair_maximum
                maximum_shift_label = self.label_names[label_index]
                maximum_shift_pair = pair_name

            js_by_pair[pair_name] = self._js_divergence(
                first_prevalence,
                second_prevalence,
            )

        maximum_js_pair = max(
            js_by_pair,
            key=js_by_pair.get,
        )
        maximum_js_divergence = js_by_pair[maximum_js_pair]

        checks = {
            "schema_validity": (
                schema_validity_rate >= self.thresholds["minimum_schema_validity_rate"]
            ),
            "missing_non_finite": (
                missing_non_finite_rate
                <= self.thresholds["maximum_missing_non_finite_rate"]
            ),
            "binary_label_validity": (
                binary_label_validity_rate
                >= self.thresholds["minimum_binary_label_validity_rate"]
            ),
            "split_artifact_isolation": (
                isolation_rate
                >= self.thresholds["minimum_split_artifact_isolation_rate"]
            ),
            "maximum_prevalence_shift": (
                maximum_shift <= self.thresholds["maximum_prevalence_shift"]
            ),
            "maximum_js_divergence": (
                maximum_js_divergence <= self.thresholds["maximum_js_divergence"]
            ),
        }

        return DataQualityReport(
            schema_validity_rate=float(schema_validity_rate),
            missing_non_finite_rate=float(missing_non_finite_rate),
            binary_label_validity_rate=float(binary_label_validity_rate),
            split_artifact_isolation_rate=float(isolation_rate),
            maximum_prevalence_shift=float(maximum_shift),
            maximum_shift_label=(maximum_shift_label),
            maximum_shift_pair=(maximum_shift_pair),
            maximum_js_divergence=float(maximum_js_divergence),
            maximum_js_pair=maximum_js_pair,
            prevalence_by_split=(prevalence_by_split),
            js_divergence_by_pair=(js_by_pair),
            thresholds=self.thresholds,
            checks=checks,
        )
