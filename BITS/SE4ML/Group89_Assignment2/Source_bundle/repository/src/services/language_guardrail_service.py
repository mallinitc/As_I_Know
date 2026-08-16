"""Deterministic grounding and safety guardrail for language output."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)


SUPPORTED_FINDING_NAMES = (
    "atelectasis",
    "cardiomegaly",
    "effusion",
    "infiltration",
    "mass",
    "nodule",
    "pneumonia",
    "pneumothorax",
    "consolidation",
    "edema",
    "emphysema",
    "fibrosis",
    "pleural",
    "hernia",
)

REQUIRED_FIRST_SECTIONS = {
    "structured_report": "PRELIMINARY MODEL REPORT",
    "plain_language_explanation": "EXPLANATION",
    "grounded_question_answering": "ANSWER",
    "educational_follow_up": "EDUCATIONAL FOLLOW-UP",
}

ALLOWED_TRIGGER_REASONS = (
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
)


@dataclass(frozen=True)
class GuardrailAudit:
    """Boolean contract checks for one generated output."""

    task_routing_compliant: bool
    section_order_compliant: bool
    required_findings_mentioned: bool
    unsupported_finding_free: bool
    numeric_grounding_compliant: bool
    safety_boundary_compliant: bool
    no_target_boundary_compliant: bool
    qa_refusal_compliant: bool
    gradcam_boundary_compliant: bool
    forbidden_claim_free: bool


@dataclass(frozen=True)
class GuardedLanguageResult:
    """Raw and guarded language output with deterministic audit lineage."""

    task_type: str
    raw_generated_text: str
    final_text: str
    guardrail_action: str
    trigger_reasons: tuple[str, ...]
    question_intent: str | None
    audit: GuardrailAudit
    guardrail_latency_ms: float


class DeterministicLanguageGuardrail:
    """Audit raw language and apply a controlled fallback when required."""

    ACCEPTED_ACTION = "accepted_model_generation"
    FALLBACK_ACTION = "safe_template_fallback"

    def __init__(
        self,
        *,
        educational_limitation: str,
        gradcam_limitation: str,
        professional_review_guidance: str,
    ) -> None:
        self.educational_limitation = educational_limitation.strip()
        self.gradcam_limitation = gradcam_limitation.strip()
        self.professional_review_guidance = professional_review_guidance.strip()

        if not self.educational_limitation:
            raise ValueError("The educational limitation is required.")

        if not self.gradcam_limitation:
            raise ValueError("The Grad-CAM limitation is required.")

        if not self.professional_review_guidance:
            raise ValueError("Professional-review guidance is required.")

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

    def _normalize_findings(
        self,
        findings: Sequence[Any],
    ) -> tuple[dict[str, Any], ...]:
        normalized = []

        for record in findings:
            label_name = (
                str(
                    self._read_value(
                        record,
                        "label_name",
                        "finding_name",
                    )
                )
                .strip()
                .lower()
            )

            probability = float(
                self._read_value(
                    record,
                    "probability",
                    "score",
                )
            )

            threshold = float(
                self._read_value(
                    record,
                    "frozen_threshold",
                    "threshold",
                )
            )

            decision = bool(
                self._read_value(
                    record,
                    "threshold_decision",
                    "crossed_threshold",
                    "decision",
                )
            )

            confidence = str(
                self._read_value(
                    record,
                    "confidence_category",
                    "confidence",
                    default=("below_threshold" if not decision else "borderline"),
                )
            ).strip()

            description = str(
                self._read_value(
                    record,
                    "approved_description",
                    "description",
                )
            ).strip()

            normalized.append(
                {
                    "label_name": label_name,
                    "probability": probability,
                    "threshold": threshold,
                    "decision": decision,
                    "confidence": confidence,
                    "description": description,
                }
            )

        if not normalized:
            raise ValueError("The guardrail requires at least one grounded finding.")

        return tuple(normalized)

    @staticmethod
    def _display_name(
        label_name: str,
    ) -> str:
        if label_name == "pleural":
            return "Pleural Abnormality"

        return label_name.replace(
            "_",
            " ",
        ).title()

    @staticmethod
    def _classify_question_intent(
        question: str | None,
    ) -> str | None:
        if question is None:
            return None

        normalized = " ".join(question.lower().split())

        if any(
            term in normalized
            for term in (
                "treat",
                "treatment",
                "medicine",
                "medication",
                "tablet",
                "drug",
                "cure",
            )
        ):
            return "treatment_request"

        if any(
            term in normalized
            for term in (
                "diagnosis",
                "diagnose",
                "do i have",
                "confirm disease",
                "what disease",
            )
        ):
            return "diagnosis_request"

        if any(
            term in normalized
            for term in (
                "grad-cam",
                "gradcam",
                "heatmap",
                "highlighted area",
                "visual evidence",
            )
        ):
            return "gradcam_boundary"

        if "no target" in normalized or "no finding" in normalized:
            return "no_target_meaning"

        if "threshold" in normalized:
            return "threshold_meaning"

        if any(
            term in normalized
            for term in (
                "confidence",
                "probability",
                "score",
            )
        ):
            return "confidence_meaning"

        return "output_summary"

    @staticmethod
    def _required_findings_for_audit(
        *,
        findings: Sequence[dict[str, Any]],
        task_type: str,
        question_intent: str | None,
    ) -> tuple[str, ...]:
        if task_type == "grounded_question_answering" and question_intent in {
            "diagnosis_request",
            "treatment_request",
            "gradcam_boundary",
            "no_target_meaning",
        }:
            return ()

        return tuple(finding["label_name"] for finding in findings)

    @staticmethod
    def _finding_is_mentioned(
        text_lower: str,
        label_name: str,
    ) -> bool:
        aliases = {
            "pleural": (
                "pleural",
                "pleural abnormality",
            ),
        }.get(
            label_name,
            (label_name,),
        )

        return any(
            re.search(
                rf"\b{re.escape(alias)}\b",
                text_lower,
            )
            is not None
            for alias in aliases
        )

    def _unsupported_finding_names(
        self,
        *,
        text_lower: str,
        supplied_names: set[str],
    ) -> tuple[str, ...]:
        unsupported = []

        for label_name in SUPPORTED_FINDING_NAMES:
            if label_name in supplied_names:
                continue

            if self._finding_is_mentioned(
                text_lower,
                label_name,
            ):
                unsupported.append(label_name)

        return tuple(unsupported)

    @staticmethod
    def _numeric_values_are_grounded(
        *,
        text: str,
        findings: Sequence[dict[str, Any]],
    ) -> bool:
        generated_values = [
            float(match)
            for match in re.findall(
                r"(?<![A-Za-z0-9])0\.\d+(?![A-Za-z0-9])",
                text,
            )
        ]

        if not generated_values:
            return True

        allowed_values = []

        for finding in findings:
            allowed_values.extend(
                [
                    finding["probability"],
                    finding["threshold"],
                ]
            )

        return all(
            any(
                abs(generated_value - allowed_value) <= 0.00005
                for allowed_value in allowed_values
            )
            for generated_value in generated_values
        )

    def _no_target_boundary_is_valid(
        self,
        *,
        text_lower: str,
        findings: Sequence[dict[str, Any]],
        no_target_finding: bool,
    ) -> bool:
        crossed_names = {
            finding["label_name"] for finding in findings if finding["decision"]
        }

        crossed_claim_pattern = re.compile(
            r"(crossed|above|exceeded)"
            r"(?:\s+its|\s+the)?"
            r"\s+(?:frozen\s+)?threshold"
        )

        if no_target_finding:
            return (
                not crossed_names and crossed_claim_pattern.search(text_lower) is None
            )

        return bool(crossed_names)

    @staticmethod
    def _qa_refusal_is_valid(
        *,
        text_lower: str,
        task_type: str,
        question_intent: str | None,
    ) -> bool:
        if task_type != "grounded_question_answering":
            return True

        if question_intent == "diagnosis_request":
            return "cannot confirm" in text_lower and "diagnos" in text_lower

        if question_intent == "treatment_request":
            has_decline = any(
                phrase in text_lower
                for phrase in (
                    "cannot recommend treatment",
                    "cannot provide treatment",
                    "cannot recommend medication",
                    "cannot provide medication",
                )
            )

            has_professional_direction = any(
                phrase in text_lower
                for phrase in (
                    "qualified healthcare professional",
                    "healthcare professional",
                    "doctor",
                )
            )

            return has_decline and has_professional_direction

        return True

    def _gradcam_boundary_is_valid(
        self,
        *,
        text_lower: str,
        task_type: str,
        question_intent: str | None,
    ) -> bool:
        if (
            task_type != "grounded_question_answering"
            or question_intent != "gradcam_boundary"
        ):
            return True

        required_terms = (
            "grad-cam",
            "model",
        )

        boundary_present = all(term in text_lower for term in required_terms)

        no_confirmation_claim = any(
            phrase in text_lower
            for phrase in (
                "does not confirm",
                "cannot confirm",
                "not confirm",
            )
        )

        return boundary_present and no_confirmation_claim

    @staticmethod
    def _forbidden_claim_free(
        text_lower: str,
    ) -> bool:
        forbidden_patterns = (
            r"\byou have\b",
            r"\bthe patient has\b",
            r"\bthis confirms a diagnosis\b",
            r"\bthe diagnosis is\b",
            r"\bdefinitely (?:has|shows|indicates)\b",
            r"\btake \d+\s*(?:mg|ml)\b",
            r"\bprescribe(?:d|s|ing)?\b",
        )

        return not any(
            re.search(
                pattern,
                text_lower,
            )
            for pattern in forbidden_patterns
        )

    def audit(
        self,
        *,
        task_type: str,
        generated_text: str,
        findings: Sequence[Any],
        no_target_finding: bool,
        user_question: str | None = None,
    ) -> tuple[
        GuardrailAudit,
        tuple[str, ...],
        str | None,
    ]:
        """Audit one raw model generation."""

        if task_type not in REQUIRED_FIRST_SECTIONS:
            raise ValueError(f"Unsupported language task: {task_type}")

        normalized_findings = self._normalize_findings(findings)

        text = generated_text.strip()
        text_lower = text.lower()

        first_section = REQUIRED_FIRST_SECTIONS[task_type]

        task_routing_compliant = text.startswith(first_section)

        first_section_position = text.find(first_section)
        limitation_position = text.find("LIMITATIONS")

        section_order_compliant = (
            first_section_position == 0 and limitation_position > first_section_position
        )

        question_intent = (
            self._classify_question_intent(user_question)
            if task_type == "grounded_question_answering"
            else None
        )

        required_findings = self._required_findings_for_audit(
            findings=normalized_findings,
            task_type=task_type,
            question_intent=question_intent,
        )

        required_findings_mentioned = all(
            self._finding_is_mentioned(
                text_lower,
                label_name,
            )
            for label_name in required_findings
        )

        supplied_names = {finding["label_name"] for finding in normalized_findings}

        unsupported_finding_free = not (
            self._unsupported_finding_names(
                text_lower=text_lower,
                supplied_names=supplied_names,
            )
        )

        numeric_grounding_compliant = self._numeric_values_are_grounded(
            text=text,
            findings=normalized_findings,
        )

        safety_boundary_compliant = self.educational_limitation.lower() in text_lower

        no_target_boundary_compliant = self._no_target_boundary_is_valid(
            text_lower=text_lower,
            findings=normalized_findings,
            no_target_finding=bool(no_target_finding),
        )

        qa_refusal_compliant = self._qa_refusal_is_valid(
            text_lower=text_lower,
            task_type=task_type,
            question_intent=question_intent,
        )

        gradcam_boundary_compliant = self._gradcam_boundary_is_valid(
            text_lower=text_lower,
            task_type=task_type,
            question_intent=question_intent,
        )

        forbidden_claim_free = self._forbidden_claim_free(text_lower)

        audit = GuardrailAudit(
            task_routing_compliant=(task_routing_compliant),
            section_order_compliant=(section_order_compliant),
            required_findings_mentioned=(required_findings_mentioned),
            unsupported_finding_free=(unsupported_finding_free),
            numeric_grounding_compliant=(numeric_grounding_compliant),
            safety_boundary_compliant=(safety_boundary_compliant),
            no_target_boundary_compliant=(no_target_boundary_compliant),
            qa_refusal_compliant=(qa_refusal_compliant),
            gradcam_boundary_compliant=(gradcam_boundary_compliant),
            forbidden_claim_free=(forbidden_claim_free),
        )

        trigger_map = {
            "task_routing_issue": (not audit.task_routing_compliant),
            "section_order_issue": (not audit.section_order_compliant),
            "missing_required_finding_issue": (not audit.required_findings_mentioned),
            "unsupported_finding_issue": (not audit.unsupported_finding_free),
            "numeric_grounding_issue": (not audit.numeric_grounding_compliant),
            "safety_boundary_issue": (not audit.safety_boundary_compliant),
            "no_target_boundary_issue": (not audit.no_target_boundary_compliant),
            "qa_refusal_issue": (not audit.qa_refusal_compliant),
            "gradcam_boundary_issue": (not audit.gradcam_boundary_compliant),
            "forbidden_claim_issue": (not audit.forbidden_claim_free),
        }

        trigger_reasons = tuple(
            reason for reason in ALLOWED_TRIGGER_REASONS if trigger_map[reason]
        )

        return (
            audit,
            trigger_reasons,
            question_intent,
        )

    @staticmethod
    def _finding_sentence(
        finding: Mapping[str, Any],
        *,
        plain_language: bool,
    ) -> str:
        display_name = DeterministicLanguageGuardrail._display_name(
            finding["label_name"]
        )

        if finding["decision"]:
            relationship = (
                "crossed its frozen threshold and was "
                f"categorized as {finding['confidence']}."
            )
        else:
            relationship = "did not cross its frozen threshold."

        if plain_language:
            return (
                f"For {display_name}, the model score was "
                f"{finding['probability']:.4f}, compared with "
                f"a decision threshold of "
                f"{finding['threshold']:.4f}. The score "
                f"{relationship} This label refers to "
                f"{finding['description']}"
            )

        return (
            f"- {display_name}: model probability "
            f"{finding['probability']:.4f}; frozen threshold "
            f"{finding['threshold']:.4f}; the probability "
            f"{relationship} {finding['description']}"
        )

    def _build_threshold_summary(
        self,
        findings: Sequence[Mapping[str, Any]],
    ) -> str:
        statements = []

        for finding in findings:
            display_name = self._display_name(finding["label_name"])

            relationship = "crossed" if finding["decision"] else "did not cross"

            statements.append(
                f"{display_name} had a model probability of "
                f"{finding['probability']:.4f} and {relationship} "
                f"its frozen threshold of "
                f"{finding['threshold']:.4f}."
            )

        return " ".join(statements)

    def build_fallback(
        self,
        *,
        task_type: str,
        findings: Sequence[Any],
        no_target_finding: bool,
        user_question: str | None = None,
        question_intent: str | None = None,
    ) -> str:
        """Build one controlled response from supplied values only."""

        normalized_findings = self._normalize_findings(findings)

        if task_type == "structured_report":
            finding_lines = "\n".join(
                self._finding_sentence(
                    finding,
                    plain_language=False,
                )
                for finding in normalized_findings
            )

            if no_target_finding:
                introduction = (
                    "No supplied finding probability crossed its "
                    "frozen decision threshold. The supplied "
                    "below-threshold relationships are:"
                )
            else:
                introduction = (
                    "The supplied model output reports the "
                    "following threshold relationships:"
                )

            return (
                "PRELIMINARY MODEL REPORT\n"
                "MODEL FINDINGS\n"
                f"{introduction}\n"
                f"{finding_lines}\n"
                "LIMITATIONS\n"
                f"{self.educational_limitation} "
                f"{self.professional_review_guidance}"
            )

        if task_type == "plain_language_explanation":
            finding_text = " ".join(
                self._finding_sentence(
                    finding,
                    plain_language=True,
                )
                for finding in normalized_findings
            )

            return (
                "EXPLANATION\n"
                "Using the provided model information, the result "
                "contains the following information. "
                f"{finding_text}\n"
                "LIMITATIONS\n"
                f"{self.educational_limitation} "
                f"{self.professional_review_guidance}"
            )

        if task_type == "educational_follow_up":
            crossed_names = [
                self._display_name(finding["label_name"])
                for finding in normalized_findings
                if finding["decision"]
            ]

            if crossed_names:
                relationship_text = (
                    "Relative to the frozen thresholds, the output "
                    "records threshold crossing for " + ", ".join(crossed_names) + "."
                )
            else:
                supplied_names = [
                    self._display_name(finding["label_name"])
                    for finding in normalized_findings
                ]

                relationship_text = (
                    "None of the supplied finding probabilities "
                    "crossed their frozen thresholds. The supplied "
                    "below-threshold findings were " + ", ".join(supplied_names) + "."
                )

            return (
                "EDUCATIONAL FOLLOW-UP\n"
                f"{relationship_text} "
                f"{self.professional_review_guidance} "
                "The supplied model output should be considered "
                "together with the complete clinical context.\n"
                "LIMITATIONS\n"
                f"{self.educational_limitation}"
            )

        if task_type != "grounded_question_answering":
            raise ValueError(f"Unsupported language task: {task_type}")

        resolved_intent = (
            question_intent
            or self._classify_question_intent(user_question)
            or "output_summary"
        )

        if resolved_intent == "diagnosis_request":
            answer = (
                "The supplied model information cannot confirm a "
                "diagnosis. It contains threshold-based model "
                "outputs that require professional interpretation "
                "together with relevant clinical information."
            )

        elif resolved_intent == "treatment_request":
            answer = (
                "The supplied model information cannot recommend "
                "treatment or medication. Treatment decisions "
                "require review by a qualified healthcare "
                "professional using the complete clinical context."
            )

        elif resolved_intent == "gradcam_boundary":
            answer = self.gradcam_limitation

        elif resolved_intent == "no_target_meaning":
            if no_target_finding:
                answer = (
                    "The no-target-finding state means that none "
                    "of the supplied finding probabilities crossed "
                    "their frozen decision thresholds. It does not "
                    "rule out disease or replace professional review."
                )
            else:
                answer = (
                    "The no-target-finding state is false because "
                    "one or more supplied probabilities crossed "
                    "their frozen decision thresholds."
                )

        elif resolved_intent == "threshold_meaning":
            answer = (
                "A frozen threshold is the stored decision boundary "
                "used to convert a model probability into a "
                "threshold-crossing or not-crossing result. "
                + self._build_threshold_summary(normalized_findings)
            )

        elif resolved_intent == "confidence_meaning":
            answer = (
                "The confidence category describes how each supplied "
                "model probability relates to its frozen threshold. "
                + self._build_threshold_summary(normalized_findings)
            )

        else:
            answer = self._build_threshold_summary(normalized_findings)

        return "ANSWER\n" f"{answer}\n" "LIMITATIONS\n" f"{self.educational_limitation}"

    def apply(
        self,
        *,
        task_type: str,
        raw_generated_text: str,
        findings: Sequence[Any],
        no_target_finding: bool,
        user_question: str | None = None,
    ) -> GuardedLanguageResult:
        """Accept a compliant generation or replace it deterministically."""

        started_at = time.perf_counter()
        logger.info(
            "guardrail_evaluation_started",
            extra={
                "component": "language_guardrail",
                "event": "evaluation_started",
                "task_type": task_type,
            },
        )

        try:
            (
                raw_audit,
                trigger_reasons,
                question_intent,
            ) = self.audit(
                task_type=task_type,
                generated_text=raw_generated_text,
                findings=findings,
                no_target_finding=no_target_finding,
                user_question=user_question,
            )
        except Exception as error:
            logger.error(
                "guardrail_evaluation_failed",
                extra={
                    "component": "language_guardrail",
                    "event": "evaluation_failed",
                    "task_type": task_type,
                    "error_type": type(error).__name__,
                },
            )
            raise

        if trigger_reasons:
            try:
                final_text = self.build_fallback(
                    task_type=task_type,
                    findings=findings,
                    no_target_finding=no_target_finding,
                    user_question=user_question,
                    question_intent=question_intent,
                )
            except Exception as error:
                logger.error(
                    "guardrail_fallback_failed",
                    extra={
                        "component": "language_guardrail",
                        "event": "fallback_failed",
                        "task_type": task_type,
                        "error_type": type(error).__name__,
                    },
                )
                raise

            guardrail_action = self.FALLBACK_ACTION
            logger.warning(
                "guardrail_fallback_activated",
                extra={
                    "component": "language_guardrail",
                    "event": "fallback_activated",
                    "task_type": task_type,
                    "trigger_reasons": list(trigger_reasons),
                },
            )
        else:
            final_text = raw_generated_text.strip()

            guardrail_action = self.ACCEPTED_ACTION
            logger.info(
                "guardrail_output_accepted",
                extra={
                    "component": "language_guardrail",
                    "event": "output_accepted",
                    "task_type": task_type,
                },
            )

        latency_ms = (time.perf_counter() - started_at) * 1000.0

        logger.info(
            "guardrail_evaluation_completed",
            extra={
                "component": "language_guardrail",
                "event": "evaluation_completed",
                "task_type": task_type,
                "guardrail_action": guardrail_action,
                "elapsed_ms": float(latency_ms),
            },
        )

        return GuardedLanguageResult(
            task_type=task_type,
            raw_generated_text=(raw_generated_text.strip()),
            final_text=final_text,
            guardrail_action=guardrail_action,
            trigger_reasons=trigger_reasons,
            question_intent=question_intent,
            audit=raw_audit,
            guardrail_latency_ms=float(latency_ms),
        )
