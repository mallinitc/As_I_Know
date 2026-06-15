from typing import Dict, Any, List, Optional

from services.role_coverage import role_covers_required_actions


DEFAULT_ROLE_PREFERENCE_ORDER = {
    "Reader": 10,
    "Storage Blob Data Reader": 20,
    "Storage Blob Data Contributor": 30,
    "Storage Account Contributor": 40,
    "Network Contributor": 50,
    "Virtual Machine Contributor": 60,
    "Contributor": 100,
}


def find_matching_roles(
    role_definitions: Dict[str, Any],
    required_actions: List[str],
    role_preference_order: Optional[Dict[str, int]] = None
) -> List[Dict[str, Any]]:
    """
    Find cached roles that cover all required actions.
    """
    if role_preference_order is None:
        role_preference_order = DEFAULT_ROLE_PREFERENCE_ORDER

    matching_roles = []

    for role_name, role_definition in role_definitions.items():
        coverage = role_covers_required_actions(role_definition, required_actions)

        if coverage["covers_all"]:
            matching_roles.append({
                "role_name": role_name,
                "preference_score": role_preference_order.get(role_name, 999),
                "covered": coverage["covered"],
                "missing": coverage["missing"]
            })

    return sorted(matching_roles, key=lambda item: item["preference_score"])


def recommend_least_privilege_role(
    role_definitions: Dict[str, Any],
    required_actions: List[str],
    role_preference_order: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """
    Recommend the least-broad role from cached roles that covers required actions.
    """
    matching_roles = find_matching_roles(
        role_definitions=role_definitions,
        required_actions=required_actions,
        role_preference_order=role_preference_order
    )

    if not matching_roles:
        return {
            "recommended_role": None,
            "matching_roles": [],
            "recommendation_status": "NO_MATCHING_ROLE"
        }

    return {
        "recommended_role": matching_roles[0]["role_name"],
        "matching_roles": matching_roles,
        "recommendation_status": "MATCH_FOUND"
    }
