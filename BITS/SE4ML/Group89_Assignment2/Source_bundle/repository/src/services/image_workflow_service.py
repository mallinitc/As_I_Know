"""Classification and visual-explainability workflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from api.schemas import (
    ClassificationResponse,
    ExplainabilityContract,
    GradCAMEvidence,
    ImageAnalysisResponse,
    ImageMetadata,
)


@dataclass(frozen=True)
class ImageWorkflowExecution:
    """Internal image workflow result and endpoint response."""

    response: ClassificationResponse | ImageAnalysisResponse
    prediction_id: Any
    classification_result: Any
    visual_evidence_count: int


class ImageAnalysisWorkflow:
    """Compose classification, storage, and controlled Grad-CAM evidence."""

    def __init__(
        self,
        *,
        computer_vision_service: Any,
        gradcam_service: Any,
        prediction_store: Any,
        operational_metrics: Any,
        metadata_builder: Callable[..., dict[str, Any]],
        explainability_contract: ExplainabilityContract,
        evidence_template: GradCAMEvidence,
    ) -> None:
        self.computer_vision_service = computer_vision_service
        self.gradcam_service = gradcam_service
        self.prediction_store = prediction_store
        self.operational_metrics = operational_metrics
        self.metadata_builder = metadata_builder
        self.explainability_contract = explainability_contract
        self.evidence_template = evidence_template

    @staticmethod
    def _construct_schema(
        schema_class: type,
        candidate_values: Mapping[str, Any],
        template: Any | None = None,
    ) -> Any:
        """Construct a schema using declared fields and optional defaults."""

        if template is None:
            payload = {}
        else:
            payload = template.model_dump(mode="python")

        for field_name in schema_class.model_fields:
            if field_name in candidate_values:
                payload[field_name] = candidate_values[field_name]

        return schema_class.model_validate(payload)

    @staticmethod
    def _build_image_metadata(
        validated_image: Any,
    ) -> ImageMetadata:
        image_values = {
            "filename": (validated_image.filename),
            "media_type": (validated_image.media_type),
            "original_mode": (validated_image.original_mode),
            "width": (validated_image.width),
            "height": (validated_image.height),
            "sha256": (validated_image.sha256),
        }

        return ImageMetadata.model_validate(image_values)

    def _classify_and_store(
        self,
        validated_image: Any,
    ) -> tuple[
        Any,
        ImageMetadata,
        Any,
    ]:
        classification_result = self.computer_vision_service.predict(validated_image)

        self.operational_metrics.record_service_invocation("computer_vision")

        image_metadata = self._build_image_metadata(validated_image)

        stored_record = self.prediction_store.create(
            image=image_metadata,
            findings=list(classification_result.findings),
            crossed_finding_names=list(classification_result.crossed_finding_names),
            no_target_finding=(classification_result.no_target_finding),
            interpretation=(classification_result.interpretation),
        )

        self.operational_metrics.record_service_invocation("prediction_store")

        return (
            classification_result,
            image_metadata,
            stored_record,
        )

    def classify(
        self,
        *,
        validated_image: Any,
        request_context: Any,
    ) -> ImageWorkflowExecution:
        """Execute classification and persist its frozen output."""

        (
            classification_result,
            image_metadata,
            stored_record,
        ) = self._classify_and_store(validated_image)

        response_metadata = self.metadata_builder(
            request_context,
            include_language=False,
            include_explainability=False,
        )

        response = ClassificationResponse.model_validate(
            {
                **response_metadata,
                "prediction_id": (stored_record.prediction_id),
                "image": image_metadata,
                "findings": list(classification_result.findings),
                "crossed_finding_names": list(
                    classification_result.crossed_finding_names
                ),
                "no_target_finding": (classification_result.no_target_finding),
                "interpretation": (classification_result.interpretation),
            }
        )

        return ImageWorkflowExecution(
            response=response,
            prediction_id=(stored_record.prediction_id),
            classification_result=(classification_result),
            visual_evidence_count=0,
        )

    def _convert_gradcam_result(
        self,
        result: Any,
    ) -> GradCAMEvidence:
        evidence_values = {
            "label_id": result.label_id,
            "finding_id": result.label_id,
            "label_name": result.label_name,
            "finding_name": result.label_name,
            "probability": result.probability,
            "frozen_threshold": (result.frozen_threshold),
            "threshold": (result.frozen_threshold),
            "threshold_decision": (result.threshold_decision),
            "crossed_threshold": (result.threshold_decision),
            "method": result.method,
            "target_layer": (result.target_layer),
            "heatmap_png_base64": (result.heatmap_png_base64),
            "heatmap_base64": (result.heatmap_png_base64),
            "overlay_png_base64": (result.overlay_png_base64),
            "overlay_base64": (result.overlay_png_base64),
            "generation_latency_ms": (result.generation_latency_ms),
            "limitation": (result.limitation),
            "limitation_boundary": (result.limitation),
        }

        return self._construct_schema(
            GradCAMEvidence,
            evidence_values,
            template=self.evidence_template,
        )

    def analyze(
        self,
        *,
        validated_image: Any,
        request_context: Any,
    ) -> ImageWorkflowExecution:
        """Execute classification, Grad-CAM, persistence, and response."""

        (
            classification_result,
            image_metadata,
            stored_record,
        ) = self._classify_and_store(validated_image)

        gradcam_results = self.gradcam_service.generate_for_crossed_findings(
            image=(validated_image.rgb_image),
            findings=(classification_result.findings),
        )

        self.operational_metrics.record_service_invocation("gradcam")

        visual_evidence = [
            self._convert_gradcam_result(result) for result in gradcam_results
        ]

        self.prediction_store.attach_visual_evidence(
            prediction_id=(stored_record.prediction_id),
            explainability=(self.explainability_contract),
            visual_evidence=(visual_evidence),
        )

        self.operational_metrics.record_service_invocation("prediction_store")

        response_metadata = self.metadata_builder(
            request_context,
            include_language=False,
            include_explainability=True,
        )

        response = ImageAnalysisResponse.model_validate(
            {
                **response_metadata,
                "prediction_id": (stored_record.prediction_id),
                "image": image_metadata,
                "findings": list(classification_result.findings),
                "crossed_finding_names": list(
                    classification_result.crossed_finding_names
                ),
                "no_target_finding": (classification_result.no_target_finding),
                "interpretation": (classification_result.interpretation),
                "explainability": (self.explainability_contract),
                "visual_evidence": (visual_evidence),
            }
        )

        return ImageWorkflowExecution(
            response=response,
            prediction_id=(stored_record.prediction_id),
            classification_result=(classification_result),
            visual_evidence_count=len(visual_evidence),
        )
