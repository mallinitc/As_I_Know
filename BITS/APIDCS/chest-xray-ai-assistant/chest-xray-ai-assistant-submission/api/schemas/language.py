"""Grounded language generation response schemas."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from api.schemas.common import SuccessResponseBase


LanguageTask = Literal[
    "structured_report",
    "plain_language_explanation",
    "grounded_question_answering",
    "educational_follow_up",
]

GuardrailAction = Literal[
    "accepted_model_generation",
    "safe_template_fallback",
]

GuardrailTrigger = Literal[
    "task_routing_issue",
    "section_order_issue",
    "missing_required_finding_issue",
    "unsupported_finding_issue",
    "numeric_grounding_issue",
    "safety_boundary_issue",
    "no_target_boundary_issue",
    "qa_refusal_issue",
    "gradcam_boundary_issue",
    "forbidden_claim_issue",
]


class LanguageGenerationResponse(SuccessResponseBase):
    """Guarded output from one grounded language task."""

    prediction_id: UUID
    task_type: LanguageTask
    question: str | None = Field(
        default=None,
        min_length=3,
        max_length=500,
    )
    grounded_finding_names: list[str]
    no_target_finding: bool
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
    def validate_language_contract(
        self,
    ) -> "LanguageGenerationResponse":
        if self.model_versions.language is None:
            raise ValueError(
                "A language-model version is required."
            )

        if (
            self.guardrail_action
            == "accepted_model_generation"
            and self.trigger_reasons
        ):
            raise ValueError(
                "Accepted generations cannot contain guardrail triggers."
            )

        if (
            self.guardrail_action
            == "safe_template_fallback"
            and not self.trigger_reasons
        ):
            raise ValueError(
                "Fallback responses require at least one trigger reason."
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
                "The generated output does not preserve its task sections."
            )

        if (
            self.task_type
            == "grounded_question_answering"
            and self.question is None
        ):
            raise ValueError(
                "Grounded question answering requires a question."
            )

        return self
