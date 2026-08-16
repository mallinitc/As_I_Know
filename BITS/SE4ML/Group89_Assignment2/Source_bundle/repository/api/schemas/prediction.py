"""Classification and finding-evidence response schemas."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from api.schemas.common import StrictSchema, SuccessResponseBase


class ImageMetadata(StrictSchema):
    """Validated metadata for an accepted uploaded image."""

    filename: str = Field(min_length=1, max_length=255)
    media_type: Literal["image/png", "image/jpeg"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    original_mode: str = Field(min_length=1, max_length=20)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class FindingEvidence(StrictSchema):
    """One model finding with its frozen decision evidence."""

    label_id: int = Field(ge=0, le=13)
    label_name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    probability: float = Field(ge=0.0, le=1.0)
    frozen_threshold: float = Field(ge=0.0, le=1.0)
    crossed_threshold: bool
    confidence_category: Literal[
        "below_threshold",
        "borderline",
        "moderate",
        "higher",
    ]
    approved_description: str = Field(
        min_length=1,
        max_length=500,
    )


class ClassificationResponse(SuccessResponseBase):
    """Complete multilabel classification response."""

    prediction_id: UUID
    image: ImageMetadata
    findings: list[FindingEvidence] = Field(
        min_length=14,
        max_length=14,
    )
    crossed_finding_names: list[str]
    no_target_finding: bool
    interpretation: str = Field(
        min_length=1,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_finding_contract(
        self,
    ) -> "ClassificationResponse":
        label_ids = [finding.label_id for finding in self.findings]
        label_names = [finding.label_name for finding in self.findings]

        if len(set(label_ids)) != 14:
            raise ValueError("Finding label identifiers must be unique.")

        if len(set(label_names)) != 14:
            raise ValueError("Finding label names must be unique.")

        expected_crossed_names = [
            finding.label_name for finding in self.findings if finding.crossed_threshold
        ]

        if self.crossed_finding_names != expected_crossed_names:
            raise ValueError(
                "Crossed finding names must match the ordered finding decisions."
            )

        expected_no_target_state = len(expected_crossed_names) == 0

        if self.no_target_finding != expected_no_target_state:
            raise ValueError(
                "The no-target-finding state conflicts with finding decisions."
            )

        return self
