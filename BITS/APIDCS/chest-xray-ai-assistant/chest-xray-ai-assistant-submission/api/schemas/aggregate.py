"""Combined workflow and stored prediction schemas."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from api.schemas.common import StrictSchema
from api.schemas.explainability import (
    ExplainabilityContract,
    GradCAMEvidence,
    ImageAnalysisResponse,
)
from api.schemas.language import (
    GuardrailAction,
    GuardrailTrigger,
    LanguageTask,
)
from api.schemas.prediction import ClassificationResponse


class EmbeddedLanguageOutput(StrictSchema):
    """One language result embedded in a larger API response."""

    task_type: LanguageTask
    question: str | None = Field(
        default=None,
        min_length=3,
        max_length=500,
    )
    output_text: str = Field(
        min_length=1,
        max_length=10000,
    )
    guardrail_action: GuardrailAction
    trigger_reasons: list[GuardrailTrigger] = Field(
        default_factory=list
    )
    generated_tokens: int = Field(ge=1)
    generation_latency_ms: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_embedded_output(
        self,
    ) -> "EmbeddedLanguageOutput":
        if (
            self.guardrail_action
            == "accepted_model_generation"
            and self.trigger_reasons
        ):
            raise ValueError(
                "Accepted embedded outputs cannot contain guardrail triggers."
            )

        if (
            self.guardrail_action
            == "safe_template_fallback"
            and not self.trigger_reasons
        ):
            raise ValueError(
                "Fallback embedded outputs require trigger reasons."
            )

        required_sections = {
            "structured_report": [
                "PRELIMINARY MODEL REPORT",
                "MODEL FINDINGS",
                "LIMITATIONS",
            ],
            "plain_language_explanation": [
                "EXPLANATION",
                "LIMITATIONS",
            ],
            "grounded_question_answering": [
                "ANSWER",
                "LIMITATIONS",
            ],
            "educational_follow_up": [
                "EDUCATIONAL FOLLOW-UP",
                "LIMITATIONS",
            ],
        }[self.task_type]

        section_positions = [
            self.output_text.find(section)
            for section in required_sections
        ]

        if (
            any(
                position < 0
                for position in section_positions
            )
            or section_positions
            != sorted(section_positions)
        ):
            raise ValueError(
                "Embedded output sections are incomplete or out of order."
            )

        if (
            self.task_type
            == "grounded_question_answering"
            and self.question is None
        ):
            raise ValueError(
                "Embedded question answering requires a question."
            )

        return self


class CompleteAnalysisResponse(ImageAnalysisResponse):
    """Complete image, visual, and guarded language workflow."""

    language_outputs: list[
        EmbeddedLanguageOutput
    ] = Field(
        min_length=3,
        max_length=4,
    )

    @model_validator(mode="after")
    def validate_complete_language_tasks(
        self,
    ) -> "CompleteAnalysisResponse":
        task_names = [
            output.task_type
            for output in self.language_outputs
        ]

        if len(task_names) != len(set(task_names)):
            raise ValueError(
                "Combined language task names must be unique."
            )

        mandatory_tasks = {
            "structured_report",
            "plain_language_explanation",
            "educational_follow_up",
        }

        if not mandatory_tasks.issubset(
            set(task_names)
        ):
            raise ValueError(
                "The combined response is missing a mandatory language task."
            )

        allowed_tasks = mandatory_tasks | {
            "grounded_question_answering"
        }

        if not set(task_names).issubset(
            allowed_tasks
        ):
            raise ValueError(
                "The combined response contains an unsupported language task."
            )

        return self


class StoredPredictionResponse(ClassificationResponse):
    """Retrievable classification with optional later-stage outputs."""

    created_at_utc: datetime
    explainability: ExplainabilityContract | None = None
    visual_evidence: list[GradCAMEvidence] = Field(
        default_factory=list
    )
    language_outputs: list[
        EmbeddedLanguageOutput
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_stored_extensions(
        self,
    ) -> "StoredPredictionResponse":
        if (
            self.explainability is None
            and self.visual_evidence
        ):
            raise ValueError(
                "Stored visual evidence requires an explainability contract."
            )

        if self.visual_evidence:
            evidence_names = [
                evidence.finding_name
                for evidence in self.visual_evidence
            ]

            if evidence_names != self.crossed_finding_names:
                raise ValueError(
                    "Stored visual evidence must match crossed findings."
                )

        language_task_names = [
            output.task_type
            for output in self.language_outputs
        ]

        if len(language_task_names) != len(
            set(language_task_names)
        ):
            raise ValueError(
                "Stored language task names must be unique."
            )

        return self
