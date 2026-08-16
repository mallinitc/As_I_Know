"""Deterministic controls for shadow model evaluation."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ShadowDeploymentPolicy:
    """Configuration and gates for isolated candidate evaluation."""

    enabled: bool = True
    sample_rate: float = 0.10
    minimum_observations: int = 1_000
    maximum_candidate_error_rate: float = 0.005
    maximum_mean_probability_delta: float = 0.03
    maximum_decision_disagreement_rate: float = 0.02
    maximum_p95_latency_overhead_ms: float = 75.0

    def __post_init__(self) -> None:
        probability_fields = {
            "sample_rate": self.sample_rate,
            "maximum_candidate_error_rate": (self.maximum_candidate_error_rate),
            "maximum_mean_probability_delta": (self.maximum_mean_probability_delta),
            "maximum_decision_disagreement_rate": (
                self.maximum_decision_disagreement_rate
            ),
        }

        for field_name, value in probability_fields.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between zero and one.")

        if self.minimum_observations < 1:
            raise ValueError("minimum_observations must be positive.")

        if self.maximum_p95_latency_overhead_ms < 0.0:
            raise ValueError("maximum_p95_latency_overhead_ms " "cannot be negative.")

    def should_shadow(self, request_id: str) -> bool:
        """Select a request without mutable routing state."""

        normalized_request_id = request_id.strip()

        if not self.enabled or self.sample_rate == 0.0 or not normalized_request_id:
            return False

        digest = hashlib.sha256(normalized_request_id.encode("utf-8")).digest()

        bucket = int.from_bytes(
            digest[:8],
            byteorder="big",
            signed=False,
        )

        normalized_bucket = bucket / float(2**64)

        return normalized_bucket < self.sample_rate

    def configuration(self) -> dict[str, object]:
        """Return a serializable policy representation."""

        return asdict(self)

    def evaluate(
        self,
        observations: Iterable[Mapping[str, object]],
    ) -> dict[str, object]:
        """Evaluate aggregate shadow observations against gates."""

        records = list(observations)
        observation_count = len(records)

        candidate_error_count = sum(
            bool(record.get("candidate_error", False)) for record in records
        )

        probability_deltas = [
            float(record["probability_abs_delta"])
            for record in records
            if record.get("probability_abs_delta") is not None
        ]

        decision_disagreements = [
            bool(record["decision_disagreement"])
            for record in records
            if record.get("decision_disagreement") is not None
        ]

        latency_overheads = [
            float(record["latency_overhead_ms"])
            for record in records
            if record.get("latency_overhead_ms") is not None
        ]

        candidate_error_rate = (
            candidate_error_count / observation_count if observation_count else 0.0
        )

        mean_probability_delta = (
            sum(probability_deltas) / len(probability_deltas)
            if probability_deltas
            else None
        )

        decision_disagreement_rate = (
            sum(decision_disagreements) / len(decision_disagreements)
            if decision_disagreements
            else None
        )

        p95_latency_overhead_ms = self._nearest_rank_percentile(
            latency_overheads,
            percentile=0.95,
        )

        gates = {
            "minimum_observations": (observation_count >= self.minimum_observations),
            "candidate_error_rate": (
                candidate_error_rate <= self.maximum_candidate_error_rate
            ),
            "mean_probability_delta": (
                mean_probability_delta is not None
                and mean_probability_delta <= self.maximum_mean_probability_delta
            ),
            "decision_disagreement_rate": (
                decision_disagreement_rate is not None
                and decision_disagreement_rate
                <= self.maximum_decision_disagreement_rate
            ),
            "p95_latency_overhead_ms": (
                p95_latency_overhead_ms is not None
                and p95_latency_overhead_ms <= self.maximum_p95_latency_overhead_ms
            ),
        }

        if not gates["minimum_observations"]:
            decision = "INSUFFICIENT_EVIDENCE"
        elif all(gates.values()):
            decision = "ELIGIBLE_FOR_CONTROLLED_CANARY"
        else:
            decision = "RETAIN_ACTIVE_MODEL"

        return {
            "observation_count": observation_count,
            "comparable_probability_count": len(probability_deltas),
            "comparable_decision_count": len(decision_disagreements),
            "latency_observation_count": len(latency_overheads),
            "candidate_error_count": candidate_error_count,
            "candidate_error_rate": candidate_error_rate,
            "mean_probability_delta": mean_probability_delta,
            "decision_disagreement_rate": (decision_disagreement_rate),
            "p95_latency_overhead_ms": (p95_latency_overhead_ms),
            "gates": gates,
            "decision": decision,
        }

    @staticmethod
    def _nearest_rank_percentile(
        values: list[float],
        percentile: float,
    ) -> float | None:
        if not values:
            return None

        ordered_values = sorted(values)
        rank = max(
            1,
            math.ceil(percentile * len(ordered_values)),
        )

        return ordered_values[rank - 1]
