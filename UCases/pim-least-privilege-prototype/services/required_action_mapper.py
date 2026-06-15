from typing import Dict, Any


def map_required_actions(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map extracted change intent to required Azure RBAC actions for prototype scenarios.

    Supported prototype patterns:
    - storage_networking_change
    - nsg_rule_change
    """
    intent_text = " ".join([
        str(extracted.get("intent_summary", "")),
        " ".join(extracted.get("resource_names", [])),
    ]).lower()

    if (
        "storage" in intent_text
        and (
            "firewall" in intent_text
            or "virtual network" in intent_text
            or "vnet" in intent_text
            or "network rule" in intent_text
        )
    ):
        return {
            "mapping_status": "MATCH_FOUND",
            "matched_pattern": "storage_networking_change",
            "required_actions": [
                "Microsoft.Storage/storageAccounts/read",
                "Microsoft.Storage/storageAccounts/write",
            ]
        }

    if (
        "network security group" in intent_text
        or "nsg" in intent_text
        or "security rule" in intent_text
        or "inbound rule" in intent_text
        or "outbound rule" in intent_text
    ):
        return {
            "mapping_status": "MATCH_FOUND",
            "matched_pattern": "nsg_rule_change",
            "required_actions": [
                "Microsoft.Network/networkSecurityGroups/read",
                "Microsoft.Network/networkSecurityGroups/write",
            ]
        }

    return {
        "mapping_status": "NO_MATCH",
        "matched_pattern": None,
        "required_actions": []
    }
