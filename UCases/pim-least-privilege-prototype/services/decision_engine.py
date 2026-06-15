from typing import Dict, Any


BROAD_ROLES = {
    "owner",
    "contributor",
    "user access administrator",
}


def evaluate_role_decision(
    requested_role: str,
    recommended_role: str
) -> Dict[str, Any]:
    """
    Compare the requested role with the recommended least-privilege role.
    """
    if not recommended_role:
        return {
            "decision": "MANUAL_REVIEW_REQUIRED",
            "reason": "No matching recommended role was found."
        }

    requested_normalized = requested_role.strip().lower()
    recommended_normalized = recommended_role.strip().lower()

    if requested_normalized == recommended_normalized:
        return {
            "decision": "APPROVE_RECOMMENDED",
            "reason": "Requested role matches the recommended least-privilege role."
        }

    if requested_normalized in BROAD_ROLES:
        return {
            "decision": "REJECT_OVERPRIVILEGED",
            "reason": (
                f"Requested role '{requested_role}' is broader than "
                f"recommended role '{recommended_role}'."
            )
        }

    return {
        "decision": "MANUAL_REVIEW_REQUIRED",
        "reason": (
            f"Requested role '{requested_role}' does not match recommended "
            f"role '{recommended_role}'. Manual review required."
        )
    }
