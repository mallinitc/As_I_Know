from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JudgeDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(ge=1, le=5)
    justification: str = Field(min_length=1, max_length=500)


class JudgeOutput(BaseModel):
    """Untrusted, optional judge output. It never changes an ARCA decision."""

    model_config = ConfigDict(extra="forbid")
    correctness: JudgeDimension
    groundedness: JudgeDimension
    relevance: JudgeDimension
    clarity: JudgeDimension
    concision: JudgeDimension
    actionability: JudgeDimension
    unsupported_claims: bool
    contradicts_deterministic_findings: bool
    cited_evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    overall_result: Literal["PASS", "FAIL", "REVIEW"]


def validate_judge_output(value: dict, available_evidence_ids: list[str]) -> dict:
    result = JudgeOutput.model_validate(value)
    available = set(available_evidence_ids)
    invalid = sorted(set(result.cited_evidence_ids) - available)
    if invalid:
        raise ValueError("Judge output cited evidence that was not supplied.")
    data = result.model_dump(mode="json")
    if result.contradicts_deterministic_findings or result.unsupported_claims:
        data["overall_result"] = "FAIL"
    data["authoritative"] = False
    data["live_judge_invoked"] = False
    return data
