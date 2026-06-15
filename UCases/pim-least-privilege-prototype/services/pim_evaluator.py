import json
import re
from pathlib import Path
from typing import Dict, Any, List

from services.change_extractor import extract_change_details
from services.required_action_mapper import map_required_actions
from services.role_recommender import recommend_least_privilege_role
from services.decision_engine import evaluate_role_decision


DEFAULT_PROJECT_ROOT = Path(r"D:\Usecase\Projects\pim-least-privilege-prototype")


def load_role_cache(project_root: Path = DEFAULT_PROJECT_ROOT) -> Dict[str, Any]:
    """
    Load cached Azure role definitions.
    """
    cache_path = project_root / "cache" / "role_definitions_selected.json"
    return json.loads(cache_path.read_text(encoding="utf-8"))


def extract_resource_name_fallback(change_text: str) -> List[str]:
    """
    Extract simple Azure-like resource names from raw change text as a fallback.
    This is intentionally conservative for the prototype.
    """
    patterns = [
        r"storage account\s+([a-zA-Z0-9-]+)",
        r"network security group\s+([a-zA-Z0-9-]+)",
        r"nsg\s+([a-zA-Z0-9-]+)",
        r"vnet\s+([a-zA-Z0-9-]+)",
        r"subnet\s+([a-zA-Z0-9-]+)",
    ]

    found = []

    for pattern in patterns:
        matches = re.findall(pattern, change_text, flags=re.IGNORECASE)
        for match in matches:
            clean_match = match.strip().strip(".,;:")
            if clean_match and clean_match.lower() not in {"to", "for", "during", "the"}:
                found.append(clean_match)

    return list(dict.fromkeys(found))


def get_extraction_confidence(extraction_result: Dict[str, Any]) -> Any:
    """
    Support both possible confidence key names.
    """
    return (
        extraction_result.get("extraction_confidence")
        if extraction_result.get("extraction_confidence") is not None
        else extraction_result.get("confidence")
    )


def evaluate_pim_request(
    change_text: str,
    model: str = "qwen2.5:1.5b-instruct",
    timeout_seconds: int = 120,
    project_root: Path = DEFAULT_PROJECT_ROOT
) -> Dict[str, Any]:
    """
    Run full least-privilege PIM evaluation for a change request.
    """
    role_cache = load_role_cache(project_root)

    extraction_result = extract_change_details(
        change_text=change_text,
        model=model,
        timeout_seconds=timeout_seconds
    )

    extracted = extraction_result["extracted"]

    if not extracted.get("resource_names"):
        extracted["resource_names"] = extract_resource_name_fallback(change_text)

    extraction_confidence = get_extraction_confidence(extraction_result)

    action_mapping = map_required_actions(extracted)

    if action_mapping["mapping_status"] != "MATCH_FOUND":
        return {
            "final_decision": "MANUAL_REVIEW_REQUIRED",
            "reason": "Could not map change intent to required Azure actions.",
            "extracted": extracted,
            "extraction_confidence": extraction_confidence,
            "matched_pattern": action_mapping["matched_pattern"],
            "required_actions": [],
            "recommended_role": None,
            "matching_roles": [],
            "llm_model": extraction_result.get("model"),
            "llm_elapsed_seconds": extraction_result.get("elapsed_seconds"),
        }

    recommendation = recommend_least_privilege_role(
        role_definitions=role_cache["roles"],
        required_actions=action_mapping["required_actions"]
    )

    decision = evaluate_role_decision(
        requested_role=extracted.get("requested_role", ""),
        recommended_role=recommendation["recommended_role"]
    )

    return {
        "final_decision": decision["decision"],
        "reason": decision["reason"],
        "extracted": extracted,
        "extraction_confidence": extraction_confidence,
        "matched_pattern": action_mapping["matched_pattern"],
        "required_actions": action_mapping["required_actions"],
        "recommended_role": recommendation["recommended_role"],
        "recommendation_status": recommendation["recommendation_status"],
        "matching_roles": recommendation["matching_roles"],
        "llm_model": extraction_result.get("model"),
        "llm_elapsed_seconds": extraction_result.get("elapsed_seconds"),
    }
