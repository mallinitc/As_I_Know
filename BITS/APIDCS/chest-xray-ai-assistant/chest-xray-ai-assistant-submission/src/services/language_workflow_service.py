
"""Orchestration for stored-prediction grounded language generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
from uuid import UUID

from api.schemas import (
    EmbeddedLanguageOutput,
    LanguageGenerationResponse,
)


SUPPORTED_LANGUAGE_TASKS = (
    "structured_report",
    "plain_language_explanation",
    "grounded_question_answering",
    "educational_follow_up",
)


@dataclass(frozen=True)
class LanguageWorkflowExecution:
    """Internal execution result and endpoint response."""

    response: LanguageGenerationResponse
    stored_output: EmbeddedLanguageOutput
    selected_finding_names: tuple[str, ...]
    guardrail_action: str
    trigger_reasons: tuple[str, ...]


class StoredPredictionLanguageWorkflow:
    """Generate guarded language strictly from stored prediction data."""

    def __init__(
        self,
        *,
        prediction_store: Any,
        grounding_serializer: Any,
        language_model_service: Any,
        language_guardrail: Any,
        operational_metrics: Any,
        metadata_builder: Callable[..., dict[str, Any]],
    ) -> None:
        self.prediction_store = prediction_store
        self.grounding_serializer = grounding_serializer
        self.language_model_service = (
            language_model_service
        )
        self.language_guardrail = language_guardrail
        self.operational_metrics = operational_metrics
        self.metadata_builder = metadata_builder

    @staticmethod
    def _read_value(
        record: Any,
        *field_names: str,
        default: Any = None,
    ) -> Any:
        for field_name in field_names:
            if isinstance(record, Mapping):
                if field_name in record:
                    return record[field_name]
            elif hasattr(record, field_name):
                return getattr(
                    record,
                    field_name,
                )

        return default

    @staticmethod
    def _construct_schema(
        schema_class: type,
        candidate_values: Mapping[str, Any],
    ) -> Any:
        """Construct a Pydantic model using its declared fields only."""

        payload = {
            field_name: candidate_values[
                field_name
            ]
            for field_name
            in schema_class.model_fields
            if field_name in candidate_values
        }

        return schema_class.model_validate(
            payload
        )

    def _select_grounding_findings(
        self,
        findings: Any,
    ) -> tuple[Any, ...]:
        """Preserve crossed findings or the two strongest below-threshold records."""

        finding_records = tuple(
            findings
        )

        if not finding_records:
            raise ValueError(
                "Stored prediction does not contain finding records."
            )

        crossed_findings = tuple(
            finding
            for finding in finding_records
            if bool(
                self._read_value(
                    finding,
                    "threshold_decision",
                    "crossed_threshold",
                    "decision",
                )
            )
        )

        if crossed_findings:
            return crossed_findings

        ranked_findings = sorted(
            finding_records,
            key=lambda finding: float(
                self._read_value(
                    finding,
                    "probability",
                    "score",
                    default=0.0,
                )
            ),
            reverse=True,
        )

        return tuple(
            ranked_findings[:2]
        )

    def generate(
        self,
        *,
        prediction_id: UUID,
        task_type: str,
        request_context: Any,
        question: str | None = None,
    ) -> LanguageWorkflowExecution:
        """Execute one complete stored-prediction language workflow."""

        if task_type not in SUPPORTED_LANGUAGE_TASKS:
            raise ValueError(
                f"Unsupported language task: {task_type}"
            )

        if (
            task_type
            == "grounded_question_answering"
        ):
            if question is None or not str(
                question
            ).strip():
                raise ValueError(
                    "Grounded question answering requires a question."
                )

            normalized_question = " ".join(
                str(question).split()
            )
        else:
            if (
                question is not None
                and str(question).strip()
            ):
                raise ValueError(
                    "Only grounded question answering accepts a question."
                )

            normalized_question = None

        stored_prediction = (
            self.prediction_store.get(
                prediction_id
            )
        )

        selected_findings = (
            self._select_grounding_findings(
                stored_prediction.findings
            )
        )

        serialized_input = (
            self.grounding_serializer.serialize(
                task_type=task_type,
                findings=selected_findings,
                no_target_finding=(
                    stored_prediction
                    .no_target_finding
                ),
                user_question=(
                    normalized_question
                ),
            )
        )

        self.operational_metrics.record_service_invocation(
            "prediction_store"
        )
        self.operational_metrics.record_service_invocation(
            "grounded_language"
        )

        raw_generation = (
            self.language_model_service.generate(
                serialized_input
            )
        )

        self.operational_metrics.record_service_invocation(
            "language_guardrail"
        )

        guarded_generation = (
            self.language_guardrail.apply(
                task_type=task_type,
                raw_generated_text=(
                    raw_generation.generated_text
                ),
                findings=selected_findings,
                no_target_finding=(
                    stored_prediction
                    .no_target_finding
                ),
                user_question=(
                    normalized_question
                ),
            )
        )

        self.operational_metrics.record_language_action(
            guarded_generation.guardrail_action
        )

        selected_finding_names = tuple(
            str(
                self._read_value(
                    finding,
                    "label_name",
                    "finding_name",
                )
            )
            for finding in selected_findings
        )

        language_values = {
            "task_type": task_type,
            "question": normalized_question,
            "grounded_finding_names": list(
                selected_finding_names
            ),
            "finding_names": list(
                selected_finding_names
            ),
            "no_target_finding": (
                stored_prediction
                .no_target_finding
            ),
            "output_text": (
                guarded_generation.final_text
            ),
            "generated_text": (
                guarded_generation.final_text
            ),
            "raw_generated_text": (
                guarded_generation
                .raw_generated_text
            ),
            "guardrail_action": (
                guarded_generation
                .guardrail_action
            ),
            "trigger_reasons": list(
                guarded_generation
                .trigger_reasons
            ),
            "generated_tokens": (
                raw_generation.generated_tokens
            ),
            "generation_latency_ms": (
                raw_generation
                .generation_latency_ms
            ),
            "guardrail_latency_ms": (
                guarded_generation
                .guardrail_latency_ms
            ),
            "language_model_version": (
                raw_generation
                .language_model_version
            ),
            "model_version": (
                raw_generation
                .language_model_version
            ),
            "decoding_strategy": (
                raw_generation
                .decoding_strategy
            ),
        }

        stored_output = self._construct_schema(
            EmbeddedLanguageOutput,
            language_values,
        )

        self.prediction_store.upsert_language_output(
            prediction_id=prediction_id,
            language_output=stored_output,
        )

        self.operational_metrics.record_service_invocation(
            "prediction_store"
        )

        response_metadata = self.metadata_builder(
            request_context,
            include_language=True,
            include_explainability=False,
        )

        response_values = {
            **response_metadata,
            "prediction_id": prediction_id,
            **language_values,
        }

        response = self._construct_schema(
            LanguageGenerationResponse,
            response_values,
        )

        return LanguageWorkflowExecution(
            response=response,
            stored_output=stored_output,
            selected_finding_names=(
                selected_finding_names
            ),
            guardrail_action=(
                guarded_generation
                .guardrail_action
            ),
            trigger_reasons=(
                guarded_generation
                .trigger_reasons
            ),
        )
