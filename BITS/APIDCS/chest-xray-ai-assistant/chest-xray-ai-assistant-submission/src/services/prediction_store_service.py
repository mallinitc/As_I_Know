"""Bounded thread-safe in-memory prediction storage."""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from api.core.errors import PredictionNotFoundError
from api.schemas.aggregate import (
    EmbeddedLanguageOutput,
    StoredPredictionResponse,
)
from api.schemas.explainability import (
    ExplainabilityContract,
    GradCAMEvidence,
)
from api.schemas.prediction import (
    FindingEvidence,
    ImageMetadata,
)


@dataclass
class PredictionRecord:
    """Internal mutable state for one validated prediction."""

    prediction_id: UUID
    created_at_utc: datetime
    image: ImageMetadata
    findings: list[FindingEvidence]
    crossed_finding_names: list[str]
    no_target_finding: bool
    interpretation: str
    explainability: ExplainabilityContract | None = None
    visual_evidence: list[GradCAMEvidence] = field(
        default_factory=list
    )
    language_outputs: list[
        EmbeddedLanguageOutput
    ] = field(default_factory=list)


class PredictionStoreService:
    """Retain a bounded set of prediction results in memory."""

    def __init__(
        self,
        *,
        maximum_records: int = 1000,
        retention_hours: int = 24,
    ) -> None:
        if maximum_records <= 0:
            raise ValueError(
                "Maximum records must be positive."
            )

        if retention_hours <= 0:
            raise ValueError(
                "Retention hours must be positive."
            )

        self.maximum_records = maximum_records
        self.retention = timedelta(
            hours=retention_hours
        )
        self._records: dict[
            UUID,
            PredictionRecord,
        ] = {}
        self._lock = threading.RLock()

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def _remove_stale_records(
        self,
        current_time: datetime,
    ) -> int:
        stale_ids = [
            prediction_id
            for prediction_id, record
            in self._records.items()
            if (
                current_time
                - record.created_at_utc
                > self.retention
            )
        ]

        for prediction_id in stale_ids:
            self._records.pop(
                prediction_id,
                None,
            )

        return len(stale_ids)

    def _enforce_capacity(self) -> None:
        while len(self._records) >= (
            self.maximum_records
        ):
            oldest_prediction_id = min(
                self._records,
                key=lambda prediction_id: (
                    self._records[
                        prediction_id
                    ].created_at_utc
                ),
            )
            self._records.pop(
                oldest_prediction_id,
                None,
            )

    def create(
        self,
        *,
        image: ImageMetadata,
        findings: list[FindingEvidence],
        crossed_finding_names: list[str],
        no_target_finding: bool,
        interpretation: str,
        prediction_id: UUID | None = None,
        created_at_utc: datetime | None = None,
    ) -> PredictionRecord:
        """Create and retain one classification record."""

        with self._lock:
            current_time = (
                created_at_utc
                or self.utc_now()
            )

            self._remove_stale_records(
                current_time
            )
            self._enforce_capacity()

            resolved_prediction_id = (
                prediction_id or uuid4()
            )

            record = PredictionRecord(
                prediction_id=(
                    resolved_prediction_id
                ),
                created_at_utc=current_time,
                image=image,
                findings=list(findings),
                crossed_finding_names=list(
                    crossed_finding_names
                ),
                no_target_finding=(
                    no_target_finding
                ),
                interpretation=interpretation,
            )

            self._records[
                resolved_prediction_id
            ] = record

            return record

    def get(
        self,
        prediction_id: UUID,
    ) -> PredictionRecord:
        """Return one retained prediction or a controlled not-found error."""

        with self._lock:
            self._remove_stale_records(
                self.utc_now()
            )

            record = self._records.get(
                prediction_id
            )

            if record is None:
                raise PredictionNotFoundError(
                    details={
                        "prediction_id": str(
                            prediction_id
                        )
                    }
                )

            return record

    def attach_visual_evidence(
        self,
        *,
        prediction_id: UUID,
        explainability: ExplainabilityContract,
        visual_evidence: list[GradCAMEvidence],
    ) -> PredictionRecord:
        """Attach validated Grad-CAM evidence."""

        with self._lock:
            record = self.get(
                prediction_id
            )
            record.explainability = (
                explainability
            )
            record.visual_evidence = list(
                visual_evidence
            )
            return record

    def upsert_language_output(
        self,
        *,
        prediction_id: UUID,
        language_output: EmbeddedLanguageOutput,
    ) -> PredictionRecord:
        """Insert or replace one task-specific language output."""

        with self._lock:
            record = self.get(
                prediction_id
            )

            retained_outputs = [
                output
                for output
                in record.language_outputs
                if output.task_type
                != language_output.task_type
            ]

            retained_outputs.append(
                language_output
            )

            record.language_outputs = (
                retained_outputs
            )

            return record

    def build_response(
        self,
        *,
        prediction_id: UUID,
        response_metadata: dict[str, Any],
    ) -> StoredPredictionResponse:
        """Build the strict retrievable prediction response."""

        record = self.get(
            prediction_id
        )

        return StoredPredictionResponse(
            **response_metadata,
            prediction_id=(
                record.prediction_id
            ),
            created_at_utc=(
                record.created_at_utc
            ),
            image=record.image,
            findings=record.findings,
            crossed_finding_names=(
                record.crossed_finding_names
            ),
            no_target_finding=(
                record.no_target_finding
            ),
            interpretation=(
                record.interpretation
            ),
            explainability=(
                record.explainability
            ),
            visual_evidence=(
                record.visual_evidence
            ),
            language_outputs=(
                record.language_outputs
            ),
        )

    def snapshot_metrics(
        self,
    ) -> dict[str, int]:
        """Return non-sensitive store measurements."""

        with self._lock:
            removed_stale_records = (
                self._remove_stale_records(
                    self.utc_now()
                )
            )

            return {
                "active_records": len(
                    self._records
                ),
                "maximum_records": (
                    self.maximum_records
                ),
                "removed_stale_records": (
                    removed_stale_records
                ),
            }
