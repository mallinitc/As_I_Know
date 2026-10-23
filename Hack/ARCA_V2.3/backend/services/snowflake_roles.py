from __future__ import annotations

from typing import Any


# Snowflake's built-in roles. Company policy allows them only for Snowflake
# infrastructure work; database, schema, and object changes must use the custom
# DB_<DB>_RL / <DB>_<SCHEMA>_R_RL, _W_RL, _C_RL access roles (directly or
# through a functional _FR role).
DEFAULT_ROLES = frozenset({"ACCOUNTADMIN", "SYSADMIN", "SECURITYADMIN", "USERADMIN", "ORGADMIN", "PUBLIC"})

# Infrastructure: users and roles, warehouses, and account-level settings.
INFRA_OPERATIONS = frozenset({
    "CREATE USER", "ALTER USER", "DROP USER",
    "CREATE ROLE", "ALTER ROLE", "DROP ROLE", "GRANT ROLE", "REVOKE ROLE",
    "CREATE WAREHOUSE", "ALTER WAREHOUSE", "DROP WAREHOUSE",
    "CREATE RESOURCE MONITOR", "ALTER RESOURCE MONITOR", "DROP RESOURCE MONITOR",
    "ALTER ACCOUNT", "CREATE NETWORK POLICY", "ALTER NETWORK POLICY", "DROP NETWORK POLICY",
    "UPDATE NETWORK CONTROLS", "CREATE INTEGRATION", "ALTER INTEGRATION", "DROP INTEGRATION",
    "CREATE SHARE", "ALTER SHARE", "DROP SHARE",
})
DATA_OBJECT_KEYWORDS = ("DATABASE", "SCHEMA", "TABLE", "VIEW", "STAGE", "PIPE", "STREAM", "TASK", "SEQUENCE", "FUNCTION", "PROCEDURE")
DML_OPERATIONS = frozenset({"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE TABLE", "COPY"})


def normalize_operation(operation: Any) -> str:
    return " ".join(str(operation or "").strip().upper().split())


def is_default_role(role: Any) -> bool:
    return str(role or "").strip().upper() in DEFAULT_ROLES


def is_data_operation(operation: Any) -> bool:
    """True for database, schema, object, and object-privilege changes."""
    normalized = normalize_operation(operation)
    if not normalized or normalized in INFRA_OPERATIONS:
        return False
    if normalized.startswith(("GRANT ", "REVOKE ")):
        return True
    return normalized in DML_OPERATIONS or any(keyword in normalized.split() for keyword in DATA_OBJECT_KEYWORDS)
