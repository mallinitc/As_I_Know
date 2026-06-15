from typing import Dict, Any


def calculate_extraction_confidence(extracted: Dict[str, Any]) -> float:
    """
    Calculate confidence based on whether required extracted fields are present.

    This is not LLM-generated confidence.
    It is deterministic Python scoring.
    """
    field_weights = {
        "change_number": 0.15,
        "environment": 0.10,
        "intent_summary": 0.20,
        "resource_names": 0.20,
        "requested_role": 0.15,
        "requested_scope": 0.10,
        "requested_duration": 0.10,
    }

    score = 0.0

    for field, weight in field_weights.items():
        value = extracted.get(field)

        if isinstance(value, list):
            if len(value) > 0:
                score += weight
        elif isinstance(value, str):
            if value.strip():
                score += weight
        elif value is not None:
            score += weight

    return round(score, 2)
