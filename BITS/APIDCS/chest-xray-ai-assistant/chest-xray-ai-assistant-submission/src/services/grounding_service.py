
"""Grounded language input serialization for API inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


TASK_PREFIXES = {
    "structured_report": "generate structured report:",
    "plain_language_explanation": "explain in simple language:",
    "grounded_question_answering": "answer grounded question:",
    "educational_follow_up": "generate educational follow-up:",
}

INPUT_FIELD_ORDER = (
    "task_type",
    "finding_names",
    "probabilities",
    "frozen_thresholds",
    "threshold_decisions",
    "no_target_finding",
    "confidence_categories",
    "model_version",
    "approved_descriptions",
    "limitation_boundary",
    "user_question",
)


@dataclass(frozen=True)
class GroundedFinding:
    """One finding supplied to the grounded language model."""

    label_id: int
    label_name: str
    probability: float
    frozen_threshold: float
    threshold_decision: bool
    confidence_category: str
    approved_description: str


@dataclass(frozen=True)
class SerializedGroundingInput:
    """Versioned language-model input and its grounding lineage."""

    task_type: str
    instruction_prefix: str
    serialized_input: str
    finding_names: tuple[str, ...]
    no_target_finding: bool
    model_version: str
    user_question: str | None


class GroundedInputSerializer:
    """Serialize frozen model output using the training-time contract."""

    def __init__(
        self,
        *,
        language_model_version: str,
        limitation_boundary: str,
        optional_value_marker: str,
        task_prefixes: Mapping[str, str] | None = None,
    ) -> None:
        self.language_model_version = (
            language_model_version.strip()
        )
        self.limitation_boundary = (
            limitation_boundary.strip()
        )
        self.optional_value_marker = (
            optional_value_marker.strip()
        )
        self.task_prefixes = dict(
            task_prefixes or TASK_PREFIXES
        )

        if not self.language_model_version:
            raise ValueError(
                "A language-model version is required."
            )

        if not self.limitation_boundary:
            raise ValueError(
                "The educational limitation is required."
            )

        if not self.optional_value_marker:
            raise ValueError(
                "The optional-value marker is required."
            )

        if set(self.task_prefixes) != set(TASK_PREFIXES):
            raise ValueError(
                "Exactly four registered language tasks are required."
            )

        if any(
            not prefix.endswith(":")
            for prefix in self.task_prefixes.values()
        ):
            raise ValueError(
                "Every language-task prefix must end with a colon."
            )

    @staticmethod
    def _read_value(
        record: Any,
        *field_names: str,
        default: Any = None,
    ) -> Any:
        """Read a value from a mapping or object."""

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
    def _derive_confidence_category(
        *,
        probability: float,
        frozen_threshold: float,
        threshold_decision: bool,
    ) -> str:
        """Apply the frozen confidence-category relationship."""

        if not threshold_decision:
            return "below_threshold"

        threshold_margin = (
            probability - frozen_threshold
        )

        if threshold_margin <= 0.02:
            return "borderline"

        if threshold_margin <= 0.10:
            return "moderate"

        return "higher"

    def normalize_finding(
        self,
        record: Any,
    ) -> GroundedFinding:
        """Normalize one service or Pydantic finding record."""

        label_id = self._read_value(
            record,
            "label_id",
            "finding_id",
        )

        label_name = self._read_value(
            record,
            "label_name",
            "finding_name",
        )

        probability = self._read_value(
            record,
            "probability",
            "score",
        )

        frozen_threshold = self._read_value(
            record,
            "frozen_threshold",
            "threshold",
        )

        threshold_decision = self._read_value(
            record,
            "threshold_decision",
            "crossed_threshold",
            "decision",
        )

        approved_description = self._read_value(
            record,
            "approved_description",
            "description",
        )

        confidence_category = self._read_value(
            record,
            "confidence_category",
            "confidence",
        )

        required_values = {
            "label_id": label_id,
            "label_name": label_name,
            "probability": probability,
            "frozen_threshold": frozen_threshold,
            "threshold_decision": threshold_decision,
            "approved_description": approved_description,
        }

        missing_fields = [
            field_name
            for field_name, value
            in required_values.items()
            if value is None
        ]

        if missing_fields:
            raise ValueError(
                "Finding record is missing required fields: "
                + ", ".join(missing_fields)
            )

        label_id = int(label_id)
        label_name = str(label_name).strip()
        probability = float(probability)
        frozen_threshold = float(
            frozen_threshold
        )
        threshold_decision = bool(
            threshold_decision
        )
        approved_description = str(
            approved_description
        ).strip()

        if not 0 <= label_id < 14:
            raise ValueError(
                "Finding label ID must be between zero and thirteen."
            )

        if not label_name:
            raise ValueError(
                "Finding label name cannot be blank."
            )

        if not 0.0 <= probability <= 1.0:
            raise ValueError(
                "Finding probability must be between zero and one."
            )

        if not 0.0 <= frozen_threshold <= 1.0:
            raise ValueError(
                "Frozen threshold must be between zero and one."
            )

        expected_decision = (
            probability >= frozen_threshold
        )

        if threshold_decision != expected_decision:
            raise ValueError(
                f"Threshold decision is inconsistent for {label_name}."
            )

        if not approved_description:
            raise ValueError(
                f"Approved description is missing for {label_name}."
            )

        if confidence_category is None:
            confidence_category = (
                self._derive_confidence_category(
                    probability=probability,
                    frozen_threshold=frozen_threshold,
                    threshold_decision=threshold_decision,
                )
            )
        else:
            confidence_category = str(
                confidence_category
            ).strip()

        allowed_categories = {
            "below_threshold",
            "borderline",
            "moderate",
            "higher",
        }

        if confidence_category not in allowed_categories:
            raise ValueError(
                f"Unsupported confidence category for {label_name}: "
                f"{confidence_category}"
            )

        if (
            not threshold_decision
            and confidence_category != "below_threshold"
        ):
            raise ValueError(
                f"Below-threshold finding {label_name} must use "
                "the below_threshold confidence category."
            )

        return GroundedFinding(
            label_id=label_id,
            label_name=label_name,
            probability=probability,
            frozen_threshold=frozen_threshold,
            threshold_decision=threshold_decision,
            confidence_category=confidence_category,
            approved_description=approved_description,
        )

    def serialize(
        self,
        *,
        task_type: str,
        findings: Sequence[Any],
        no_target_finding: bool,
        user_question: str | None = None,
    ) -> SerializedGroundingInput:
        """Build one deterministic training-compatible model input."""

        if task_type not in self.task_prefixes:
            raise ValueError(
                f"Unsupported language task: {task_type}"
            )

        normalized_findings = tuple(
            self.normalize_finding(
                finding
            )
            for finding in findings
        )

        if not normalized_findings:
            raise ValueError(
                "At least one grounded finding record is required."
            )

        label_ids = [
            finding.label_id
            for finding in normalized_findings
        ]

        label_names = [
            finding.label_name
            for finding in normalized_findings
        ]

        if len(label_ids) != len(set(label_ids)):
            raise ValueError(
                "Duplicate finding label IDs are not allowed."
            )

        if len(label_names) != len(set(label_names)):
            raise ValueError(
                "Duplicate finding label names are not allowed."
            )

        crossed_findings = [
            finding
            for finding in normalized_findings
            if finding.threshold_decision
        ]

        if bool(no_target_finding) != (
            len(crossed_findings) == 0
        ):
            raise ValueError(
                "The no-target-finding state contradicts "
                "the supplied threshold decisions."
            )

        if task_type == "grounded_question_answering":
            if user_question is None:
                raise ValueError(
                    "Grounded question answering requires a question."
                )

            normalized_question = " ".join(
                str(user_question).split()
            )

            if not normalized_question:
                raise ValueError(
                    "Grounded question cannot be blank."
                )
        else:
            if (
                user_question is not None
                and str(user_question).strip()
            ):
                raise ValueError(
                    "Only grounded question answering accepts a question."
                )

            normalized_question = (
                self.optional_value_marker
            )

        finding_names_value = " | ".join(
            finding.label_name
            for finding in normalized_findings
        )

        probabilities_value = " | ".join(
            (
                f"{finding.label_name}="
                f"{finding.probability:.4f}"
            )
            for finding in normalized_findings
        )

        thresholds_value = " | ".join(
            (
                f"{finding.label_name}="
                f"{finding.frozen_threshold:.4f}"
            )
            for finding in normalized_findings
        )

        decisions_value = " | ".join(
            (
                f"{finding.label_name}="
                f"{'crossed' if finding.threshold_decision else 'not_crossed'}"
            )
            for finding in normalized_findings
        )

        confidence_value = " | ".join(
            (
                f"{finding.label_name}="
                f"{finding.confidence_category}"
            )
            for finding in normalized_findings
        )

        descriptions_value = " || ".join(
            (
                f"{finding.label_name}: "
                f"{finding.approved_description}"
            )
            for finding in normalized_findings
        )

        field_values = {
            "task_type": task_type,
            "finding_names": finding_names_value,
            "probabilities": probabilities_value,
            "frozen_thresholds": thresholds_value,
            "threshold_decisions": decisions_value,
            "no_target_finding": str(
                bool(no_target_finding)
            ).lower(),
            "confidence_categories": confidence_value,
            "model_version": self.language_model_version,
            "approved_descriptions": descriptions_value,
            "limitation_boundary": self.limitation_boundary,
            "user_question": normalized_question,
        }

        serialized_lines = [
            self.task_prefixes[task_type]
        ]

        serialized_lines.extend(
            f"{field_name}: {field_values[field_name]}"
            for field_name in INPUT_FIELD_ORDER
        )

        serialized_input = "\n".join(
            serialized_lines
        )

        return SerializedGroundingInput(
            task_type=task_type,
            instruction_prefix=self.task_prefixes[
                task_type
            ],
            serialized_input=serialized_input,
            finding_names=tuple(label_names),
            no_target_finding=bool(
                no_target_finding
            ),
            model_version=self.language_model_version,
            user_question=(
                normalized_question
                if task_type
                == "grounded_question_answering"
                else None
            ),
        )
