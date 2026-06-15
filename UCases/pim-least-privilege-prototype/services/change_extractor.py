from typing import Dict, Any

from services.llm_adapter import call_ollama
from services.json_utils import parse_llm_json_response
from services.extraction_confidence import calculate_extraction_confidence


def build_extraction_prompt(change_text: str) -> str:
    return f"""
You are an Azure change request parser.

Return only valid JSON.
Do not use markdown fences.
Do not include explanation.

The JSON must contain exactly these keys:
{{
  "change_number": "",
  "environment": "",
  "intent_summary": "",
  "resource_names": [],
  "requested_role": "",
  "requested_scope": "",
  "requested_duration": ""
}}

Rules:
- Extract resource names from the description if present.
- resource_names must be a list of strings.
- If a field is not found, use an empty string or empty list.
- Do not remove any key.

Change request:
{change_text}
"""


def extract_change_details(
    change_text: str,
    model: str = "qwen2.5:1.5b-instruct",
    timeout_seconds: int = 120
) -> Dict[str, Any]:
    prompt = build_extraction_prompt(change_text)

    llm_result = call_ollama(
        prompt=prompt,
        model=model,
        timeout_seconds=timeout_seconds
    )

    extracted = parse_llm_json_response(llm_result["response"])

    extraction_confidence = calculate_extraction_confidence(extracted)

    return {
        "extracted": extracted,
        "extraction_confidence": extraction_confidence,
        "model": llm_result["model"],
        "elapsed_seconds": llm_result["elapsed_seconds"],
        "raw_response": llm_result["response"]
    }
