import json
from typing import Dict, Any


def parse_llm_json_response(raw_response: str) -> Dict[str, Any]:
    """
    Clean and parse JSON returned by an LLM.

    Supports:
    - plain JSON
    - JSON wrapped in ```json fences
    - JSON wrapped in generic ``` fences
    """
    cleaned = raw_response.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()

    if cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    return json.loads(cleaned)
