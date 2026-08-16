"""Pydantic request contracts for grounded language endpoints."""

from uuid import UUID

from pydantic import Field, field_validator

from api.schemas.common import StrictSchema


class GroundedGenerationRequest(StrictSchema):
    """Request a language task using an existing prediction context."""

    prediction_id: UUID


class GroundedQuestionRequest(StrictSchema):
    """Request grounded question answering for an existing prediction."""

    prediction_id: UUID
    question: str = Field(min_length=3, max_length=500)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned_value = value.strip()

        if len(cleaned_value) < 3:
            raise ValueError(
                "The question must contain at least three non-whitespace characters."
            )

        if any(
            ord(character) < 32 and character not in {"\t", "\n", "\r"}
            for character in cleaned_value
        ):
            raise ValueError("The question contains unsupported control characters.")

        return cleaned_value


class CompleteAnalysisOptions(StrictSchema):
    """Validated optional form values for the combined workflow."""

    question: str | None = Field(
        default=None,
        max_length=500,
    )

    @field_validator("question")
    @classmethod
    def validate_optional_question(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        cleaned_value = value.strip()

        if not cleaned_value:
            return None

        if len(cleaned_value) < 3:
            raise ValueError(
                "The optional question must contain at least three characters."
            )

        if any(
            ord(character) < 32 and character not in {"\t", "\n", "\r"}
            for character in cleaned_value
        ):
            raise ValueError(
                "The optional question contains unsupported control characters."
            )

        return cleaned_value
