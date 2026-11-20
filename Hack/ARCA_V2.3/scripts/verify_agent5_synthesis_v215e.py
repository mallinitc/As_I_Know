from __future__ import annotations

import base64
import copy
import gzip
import json

from dotenv import load_dotenv

from backend.llm.gateway import LlmGateway
from backend.schemas.ask_arca import AskArcaResponse
from backend.services.ask_arca import AskArcaService


QUESTION = "Find unapproved Snowflake role grants in the last 30 days."
EVALUATION_TIMESTAMP = "2026-11-24T00:00:00Z"


def main() -> None:
    load_dotenv(".env")
    service = AskArcaService()
    result = service._ask_deterministic(
        QUESTION,
        EVALUATION_TIMESTAMP,
        None,
        execution_mode="llm_assisted",
    )
    authoritative_before = copy.deepcopy(
        {
            "findings": result["findings"],
            "overall_status": result["overall_status"],
            "confidence": result["confidence"],
        }
    )
    evidence_ids = service._evidence_ids(result)
    gateway = LlmGateway()
    synthesis, model, usage = gateway.synthesize(QUESTION, result, evidence_ids)

    if not evidence_ids or not synthesis.evidence_citations:
        raise RuntimeError("Synthesis omitted required evidence citations.")
    if not set(synthesis.evidence_citations).issubset(set(evidence_ids)):
        raise RuntimeError("Synthesis cited evidence outside the supplied set.")
    authoritative_after = {
        "findings": result["findings"],
        "overall_status": result["overall_status"],
        "confidence": result["confidence"],
    }
    if authoritative_before != authoritative_after:
        raise RuntimeError("Synthesis changed deterministic findings or status.")

    result.update(
        {
            "investigation_summary": synthesis.summary,
            "model_generated_explanation": synthesis.summary,
            "llm_evidence_citations": synthesis.evidence_citations,
            "llm_provider": gateway.capability().get("provider"),
            "llm_status": "completed",
            "model_identifier": model,
            "token_usage": usage.model_dump(),
            "llm_error": None,
        }
    )
    result["resolved_intent"]["parser"] = "reused_deterministic_context"
    validated = AskArcaResponse.model_validate(result).model_dump(mode="json")
    compressed = gzip.compress(
        json.dumps(validated, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    print(
        json.dumps(
            {
                "response_gzip_b64": base64.b64encode(compressed).decode("ascii"),
                "model": model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "citation_count": len(synthesis.evidence_citations),
                "evidence_count": len(evidence_ids),
                "findings_count": len(result["findings"]),
                "overall_status": result["overall_status"],
                "final_schema_valid": True,
                "findings_preserved": True,
            }
        )
    )


if __name__ == "__main__":
    main()
