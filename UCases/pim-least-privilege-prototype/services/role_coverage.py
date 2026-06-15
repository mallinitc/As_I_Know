import fnmatch
from typing import Dict, Any, List


def get_role_actions(role_definition: Dict[str, Any]) -> List[str]:
    """
    Return management-plane actions from an Azure role definition.
    """
    actions = []

    for permission in role_definition.get("permissions", []):
        actions.extend(permission.get("actions", []))

    return actions


def role_covers_action(role_actions: List[str], required_action: str) -> bool:
    """
    Check whether any role action pattern covers a required action.

    Supports wildcard patterns like:
    - *
    - Microsoft.Storage/storageAccounts/*
    - Microsoft.Authorization/*/read
    """
    for role_action in role_actions:
        if fnmatch.fnmatchcase(required_action.lower(), role_action.lower()):
            return True

    return False


def role_covers_required_actions(
    role_definition: Dict[str, Any],
    required_actions: List[str]
) -> Dict[str, Any]:
    """
    Check whether a role definition covers all required actions.
    """
    role_actions = get_role_actions(role_definition)

    covered = []
    missing = []

    for required_action in required_actions:
        if role_covers_action(role_actions, required_action):
            covered.append(required_action)
        else:
            missing.append(required_action)

    return {
        "covered": covered,
        "missing": missing,
        "covers_all": len(missing) == 0
    }
