"""Complete image, explainability, and grounded-language workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.schemas import CompleteAnalysisResponse

MANDATORY_LANGUAGE_TASKS = (
    "structured_report",
    "plain_language_explanation",
    "educational_follow_up",
)

OPTIONAL_QUESTION_TASK = "grounded_question_answering"


@dataclass(frozen=True)
class CompleteWorkflowExecution:
    """Complete response and its internal execution summary."""

    response: CompleteAnalysisResponse
    prediction_id: Any
    executed_language_tasks: tuple[str, ...]
    guardrail_actions: dict[str, str]
    visual_evidence_count: int


class CompleteAnalysisWorkflow:
    """Compose the complete educational decision-support workflow."""

    def __init__(
        self,
        *,
        image_workflow: Any,
        language_workflow: Any,
        prediction_store: Any,
        operational_metrics: Any,
        metadata_builder: Callable[..., dict[str, Any]],
    ) -> None:
        self.image_workflow = image_workflow
        self.language_workflow = language_workflow
        self.prediction_store = prediction_store
        self.operational_metrics = operational_metrics
        self.metadata_builder = metadata_builder

    def analyze_complete(
        self,
        *,
        validated_image: Any,
        request_context: Any,
        question: str | None = None,
    ) -> CompleteWorkflowExecution:
        """Execute image analysis and all requested language tasks."""

        normalized_question = None

        if question is not None:
            normalized_question = " ".join(str(question).split())

            if not normalized_question:
                normalized_question = None

        image_execution = self.image_workflow.analyze(
            validated_image=(validated_image),
            request_context=(request_context),
        )

        prediction_id = image_execution.prediction_id

        executed_tasks = list(MANDATORY_LANGUAGE_TASKS)

        if normalized_question is not None:
            executed_tasks.append(OPTIONAL_QUESTION_TASK)

        language_executions = {}

        for task_type in executed_tasks:
            language_executions[task_type] = self.language_workflow.generate(
                prediction_id=(prediction_id),
                task_type=task_type,
                request_context=(request_context),
                question=(
                    normalized_question if task_type == OPTIONAL_QUESTION_TASK else None
                ),
            )

        stored_record = self.prediction_store.get(prediction_id)

        self.operational_metrics.record_service_invocation("prediction_store")

        response_metadata = self.metadata_builder(
            request_context,
            include_language=True,
            include_explainability=True,
        )

        response = CompleteAnalysisResponse.model_validate(
            {
                **response_metadata,
                "prediction_id": (stored_record.prediction_id),
                "image": (stored_record.image),
                "findings": list(stored_record.findings),
                "crossed_finding_names": list(stored_record.crossed_finding_names),
                "no_target_finding": (stored_record.no_target_finding),
                "interpretation": (stored_record.interpretation),
                "explainability": (stored_record.explainability),
                "visual_evidence": list(stored_record.visual_evidence),
                "language_outputs": list(stored_record.language_outputs),
            }
        )

        guardrail_actions = {
            task_type: (execution.guardrail_action)
            for task_type, execution in language_executions.items()
        }

        return CompleteWorkflowExecution(
            response=response,
            prediction_id=prediction_id,
            executed_language_tasks=tuple(executed_tasks),
            guardrail_actions=(guardrail_actions),
            visual_evidence_count=len(stored_record.visual_evidence),
        )
