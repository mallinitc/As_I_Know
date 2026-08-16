"""Visual explainability response schemas."""

import base64
from typing import Literal

from pydantic import Field, field_validator, model_validator

from api.schemas.common import StrictSchema
from api.schemas.prediction import ClassificationResponse


class ExplainabilityContract(StrictSchema):
    """Frozen Grad-CAM method and interpretation boundary."""

    method: Literal["LayerGradCam"] = "LayerGradCam"
    target_layer: str = Field(min_length=1, max_length=200)
    attribution_target: Literal[
        "finding_specific_pre_sigmoid_logit"
    ] = "finding_specific_pre_sigmoid_logit"
    positive_attributions_only: Literal[True] = True
    heatmap_normalization: Literal[
        "independent_zero_to_one"
    ] = "independent_zero_to_one"
    limitation: str = Field(min_length=1, max_length=1000)


class GradCAMEvidence(StrictSchema):
    """Finding-specific visual evidence returned as PNG content."""

    finding_name: str = Field(min_length=1, max_length=50)
    probability: float = Field(ge=0.0, le=1.0)
    frozen_threshold: float = Field(ge=0.0, le=1.0)
    crossed_threshold: Literal[True] = True
    heatmap_png_base64: str = Field(min_length=12)
    overlay_png_base64: str = Field(min_length=12)
    high_attribution_area_percent: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
    )

    @field_validator(
        "heatmap_png_base64",
        "overlay_png_base64",
    )
    @classmethod
    def validate_png_base64(cls, value: str) -> str:
        try:
            decoded_value = base64.b64decode(
                value,
                validate=True,
            )
        except Exception as error:
            raise ValueError(
                "Visual evidence must contain valid base64."
            ) from error

        if not decoded_value.startswith(
            b"\x89PNG\r\n\x1a\n"
        ):
            raise ValueError(
                "Visual evidence must contain PNG content."
            )

        return value


class ImageAnalysisResponse(ClassificationResponse):
    """Classification response extended with Grad-CAM evidence."""

    explainability: ExplainabilityContract
    visual_evidence: list[GradCAMEvidence]

    @model_validator(mode="after")
    def validate_visual_evidence(
        self,
    ) -> "ImageAnalysisResponse":
        evidence_names = [
            evidence.finding_name
            for evidence in self.visual_evidence
        ]

        if len(evidence_names) != len(
            set(evidence_names)
        ):
            raise ValueError(
                "Visual-evidence finding names must be unique."
            )

        if evidence_names != self.crossed_finding_names:
            raise ValueError(
                "Visual evidence must match the ordered threshold-crossed findings."
            )

        evidence_by_name = {
            evidence.finding_name: evidence
            for evidence in self.visual_evidence
        }

        for finding in self.findings:
            if finding.crossed_threshold:
                evidence = evidence_by_name[
                    finding.label_name
                ]

                if (
                    abs(
                        evidence.probability
                        - finding.probability
                    )
                    > 1e-6
                    or abs(
                        evidence.frozen_threshold
                        - finding.frozen_threshold
                    )
                    > 1e-6
                ):
                    raise ValueError(
                        "Visual evidence must preserve classification values."
                    )

        return self
