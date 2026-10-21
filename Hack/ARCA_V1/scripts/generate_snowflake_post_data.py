"""Generate deterministic, fully synthetic Snowflake audit fixtures. Never executes SQL."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "snowflake"
UTC = timezone.utc


def stamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def write(name: str, value) -> None:
    (DATA / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


users = [
    {"user_id": f"SF-USER-{index:03d}", "user_name": name, "email": email,
     "account_name": "ARCA_DEMO_ACCOUNT", "active": True}
    for index, (name, email) in enumerate([
        ("SFSECURITY01", "sfsecurity01@example.invalid"),
        ("SFENGINEER01", "sfengineer01@example.invalid"),
        ("SFENGINEER02", "sfengineer02@example.invalid"),
        ("SFENGINEER03", "sfengineer03@example.invalid"),
        ("SFENGINEER05", "sfengineer05@example.invalid"),
        ("SFENGINEER08", "sfengineer08@example.invalid"),
        ("SFSECURITY02", "sfsecurity02@example.invalid"),
        ("SFENGINEER12", "sfengineer12@example.invalid"),
        ("SFSECURITY05", "sfsecurity05@example.invalid"),
        ("SFENGINEER14", "sfengineer14@example.invalid"),
        ("SFENGINEER16", "sfengineer16@example.invalid"),
        ("SFENGINEER19", "sfengineer19@example.invalid"),
        ("SFENGINEER22", "sfengineer22@example.invalid"),
        ("SFROGUE01", "rogue.engineer@example.invalid"),
        ("SFROGUE02", "shared.operations@example.invalid"),
    ], start=1)
]
# A second exact-email identity intentionally supports ambiguity testing.
users.append({"user_id": "SF-USER-016", "user_name": "SFROGUE03",
              "email": "shared.operations@example.invalid", "account_name": "ARCA_DEMO_ACCOUNT", "active": True})

grants_to_users = [
    {"grant_id": f"SF-GTU-{index:03d}", "user_name": user["user_name"],
     "role_name": "SECURITYADMIN" if "SECURITY" in user["user_name"] else "SYSADMIN",
     "granted_on": "2026-10-01T00:00:00Z", "revoked_on": None}
    for index, user in enumerate(users, start=1)
]
grants_to_roles = json.loads((DATA / "role_grants.json").read_text(encoding="utf-8"))


def query(query_id: str, when: str, user: str, role: str, operation: str, target: str,
          change_id: str | None = None, status: str = "SUCCESS", sql: str | None = None) -> dict:
    start = datetime.fromisoformat(when.replace("Z", "+00:00"))
    database = target.split(".")[0] if "." in target and not target.startswith(("ROLE:", "USER:")) else None
    schema = target.split(".")[1] if target.count(".") >= 1 and not target.startswith(("ROLE:", "USER:")) else None
    return {
        "query_id": query_id, "query_text": sql or f"{operation} {target}", "query_type": operation,
        "user_name": user, "role_name": role, "database_name": database, "schema_name": schema,
        "warehouse_name": None if operation in {"GRANT ROLE", "REVOKE ROLE", "ALTER USER", "CREATE USER"} else "REPORTING_WH",
        "start_time": stamp(start), "end_time": stamp(start + timedelta(seconds=4)),
        "execution_status": status, "error_code": "002003" if status == "FAILED" else None,
        "error_message": "Synthetic object validation failure" if status == "FAILED" else None,
        "query_tag": f"ARCA_CHANGE={change_id}" if change_id else None,
        "session_id": f"SF-SESSION-{query_id[-3:]}", "target_object": target,
    }


special = [
    query("SF-QRY-001", "2026-11-07T10:10:00Z", "SFSECURITY01", "SECURITYADMIN", "GRANT ROLE", "ROLE:FINANCE_ANALYST->ROLE:REPORTING_USERS", "CHG-SF-1007", sql="GRANT ROLE FINANCE_ANALYST TO ROLE REPORTING_USERS"),
    query("SF-QRY-002", "2026-11-07T11:10:00Z", "SFSECURITY01", "SECURITYADMIN", "GRANT ROLE", "ROLE:FINANCE_ANALYST->ROLE:REPORTING_USERS", "CHG-SF-1007", sql="GRANT ROLE FINANCE_ANALYST TO ROLE REPORTING_USERS"),
    query("SF-QRY-003", "2026-11-07T10:12:00Z", "SFROGUE01", "SECURITYADMIN", "GRANT ROLE", "ROLE:FINANCE_ANALYST->ROLE:REPORTING_USERS", "CHG-SF-1007"),
    query("SF-QRY-004", "2026-11-07T10:14:00Z", "SFSECURITY01", "ACCOUNTADMIN", "GRANT ROLE", "ROLE:FINANCE_ANALYST->ROLE:REPORTING_USERS", "CHG-SF-1007"),
    query("SF-QRY-005", "2026-11-07T10:16:00Z", "SFSECURITY01", "SECURITYADMIN", "GRANT ROLE", "ROLE:ACCOUNTADMIN->USER:SFROGUE01", "CHG-SF-1007"),
    query("SF-QRY-006", "2026-11-08T10:20:00Z", "SFENGINEER08", "ACCOUNTADMIN", "ALTER TABLE", "FINANCE_DB.REPORTING.OTHER_TABLE", "CHG-SF-1008"),
    query("SF-QRY-007", "2026-11-22T10:20:00Z", "SFENGINEER22", "SYSADMIN", "CREATE DATABASE", "UNAPPROVED_DB", "CHG-SF-1022"),
    query("SF-QRY-008", "2026-11-08T10:25:00Z", "SFENGINEER08", "ACCOUNTADMIN", "ALTER TABLE", "FINANCE_DB.REPORTING.TRANSACTIONS", "CHG-SF-1008", status="FAILED"),
    query("SF-QRY-009", "2026-11-20T12:05:00Z", "SFROGUE01", "SECURITYADMIN", "REVOKE ROLE", "ROLE:FINANCE_ANALYST->ROLE:REPORTING_USERS"),
    query("SF-QRY-010", "2026-11-12T10:20:00Z", "SFENGINEER12", "SYSADMIN", "CREATE SCHEMA", "MARKETING_DB.REPORTING", "CHG-SF-1012"),
    query("SF-QRY-011", "2026-11-09T10:10:00Z", "SFSECURITY02", "USERADMIN", "ALTER USER", "USER:SVC_REPORTING", "CHG-SF-1009"),
    query("SF-QRY-012", "2026-11-09T10:15:00Z", "SFSECURITY02", "USERADMIN", "CREATE USER", "USER:UNAPPROVED_SUPPORT", "CHG-SF-1009"),
    query("SF-QRY-013", "2026-11-13T10:20:00Z", "SFSECURITY05", "SECURITYADMIN", "REVOKE INSERT", "FINANCE_DB.STAGING.TRANSACTIONS_RAW", "CHG-SF-1013"),
    query("SF-QRY-014", "2026-11-13T10:25:00Z", "SFSECURITY05", "SECURITYADMIN", "GRANT ROLE", "ROLE:ACCOUNTADMIN->USER:SFROGUE01", "CHG-SF-1013"),
    query("SF-QRY-015", "2026-11-07T12:00:00Z", "SFSECURITY01", "SECURITYADMIN", "REVOKE ROLE", "ROLE:FINANCE_ANALYST->ROLE:REPORTING_USERS", "CHG-SF-1007"),
    query("SF-QRY-016", "2026-11-14T12:00:00Z", "SFENGINEER14", "WAREHOUSE_OPERATOR", "ALTER WAREHOUSE", "REPORTING_WH", "CHG-SF-1014"),
    query("SF-QRY-017", "2026-11-03T10:30:00Z", "SFENGINEER03", "SYSADMIN", "ALTER DATABASE", "SALES_DB", "CHG-SF-1003"),
    query("SF-QRY-018", "2026-11-20T12:00:00Z", "SFROGUE01", "USERADMIN", "CREATE USER", "USER:UNAPPROVED_ADMIN"),
    query("SF-QRY-019", "2026-11-20T12:10:00Z", "SFROGUE01", "SECURITYADMIN", "GRANT ROLE", "ROLE:ACCOUNTADMIN->USER:SFROGUE01"),
    query("SF-QRY-020", "2026-11-20T12:20:00Z", "SFROGUE01", "ACCOUNTADMIN", "DROP TABLE", "FINANCE_DB.REPORTING.TRANSACTIONS"),
    query("SF-QRY-021", "2026-11-07T10:18:00Z", "SFSECURITY01", "SECURITYADMIN", "GRANT ROLE", "ROLE:FINANCE_ANALYST->ROLE:REPORTING_USERS", "CHG-SF-1007"),
    query("SF-QRY-022", "2026-11-09T10:18:00Z", "SFSECURITY01", "USERADMIN", "ALTER USER", "USER:SVC_REPORTING", "CHG-SF-1009"),
]

routine = []
base = datetime(2026, 10, 25, 8, tzinfo=UTC)
for index in range(24, 102):
    when = base + timedelta(hours=index * 4)
    user = users[index % len(users)]["user_name"]
    routine.append(query(f"SF-QRY-{index:03d}", stamp(when), user, "REPORTING_READONLY", "SELECT",
                         "FINANCE_DB.REPORTING.TRANSACTIONS", sql="SELECT COUNT(*) FROM FINANCE_DB.REPORTING.TRANSACTIONS"))
query_history = special + routine

access_history = []
for item in query_history[:50]:
    target = item["target_object"]
    modified = item["query_type"] != "SELECT" and item["execution_status"] == "SUCCESS"
    access_history.append({
        "query_id": item["query_id"], "query_start_time": item["start_time"], "user_name": item["user_name"],
        "direct_objects_accessed": [{"objectName": target, "objectDomain": "TABLE"}] if item["query_type"] == "SELECT" else [],
        "base_objects_accessed": [{"objectName": target, "objectDomain": "TABLE"}] if item["query_type"] == "SELECT" else [],
        "objects_modified": [{"objectName": target, "objectDomain": item["query_type"].split()[-1]}] if modified else [],
        "object_modified_by_ddl": modified and item["query_type"] not in {"INSERT", "UPDATE", "DELETE"},
    })
# Deliberately remove audit support for SF-QRY-017 to demonstrate incomplete evidence.
access_history = [item for item in access_history if item["query_id"] != "SF-QRY-017"]
access_history.append({"query_id": "SF-QRY-099", "query_start_time": query_history[98]["start_time"],
                       "user_name": query_history[98]["user_name"], "direct_objects_accessed": [],
                       "base_objects_accessed": [], "objects_modified": [], "object_modified_by_ddl": False})

login_history = [{
    "event_id": f"SF-LOGIN-{index:03d}", "event_timestamp": stamp(datetime(2026, 11, 1, 7, tzinfo=UTC) + timedelta(days=index)),
    "user_name": users[index % len(users)]["user_name"], "client_ip": f"192.0.2.{index + 10}",
    "reported_client_type": "SNOWSQL", "is_success": index not in {7, 13},
    "error_code": None if index not in {7, 13} else "390100",
} for index in range(20)]

scenario_specs = [
    ("01", "Change Executed Successfully", "change", "CHG-SF-1007", None, ["SF-QRY-001"], ["COMPLIANT_EXECUTION"]),
    ("02", "Change Executed Outside Approved Window", "change", "CHG-SF-1007", None, ["SF-QRY-002"], ["EXECUTED_OUTSIDE_WINDOW"]),
    ("03", "Unauthorized Implementer", "change", "CHG-SF-1007", None, ["SF-QRY-003"], ["UNAUTHORIZED_IMPLEMENTER"]),
    ("04", "Incorrect Snowflake Role", "change", "CHG-SF-1007", None, ["SF-QRY-004"], ["ROLE_MISMATCH"]),
    ("05", "Unexpected GRANT ROLE", "change", "CHG-SF-1007", None, ["SF-QRY-005"], ["WRONG_TARGET_OBJECT", "EXPECTED_OPERATION_MISSING"]),
    ("06", "Wrong Table Modified", "change", "CHG-SF-1008", None, ["SF-QRY-006"], ["WRONG_TARGET_OBJECT", "EXPECTED_OPERATION_MISSING"]),
    ("07", "Wrong Database Modified", "change", "CHG-SF-1022", None, ["SF-QRY-007"], ["WRONG_TARGET_OBJECT", "EXPECTED_OPERATION_MISSING"]),
    ("08", "Approved Operation Failed", "change", "CHG-SF-1008", None, ["SF-QRY-008"], ["FAILED_EXECUTION", "EXPECTED_OPERATION_MISSING"]),
    ("09", "Expected Operation Never Observed", "change", "CHG-SF-1017", None, [], ["NO_EXECUTION_EVIDENCE", "EXPECTED_OPERATION_MISSING"]),
    ("10", "Multiple Operations / Partial Implementation", "change", "CHG-SF-1012", None, ["SF-QRY-010"], ["COMPLIANT_EXECUTION", "EXPECTED_OPERATION_MISSING"]),
    ("11", "Extra Unauthorized Operation", "change", "CHG-SF-1009", None, ["SF-QRY-011", "SF-QRY-012"], ["COMPLIANT_EXECUTION", "UNAPPROVED_OPERATION", "UNEXPECTED_ADDITIONAL_OPERATION"]),
    ("12", "Compliant Role Modification", "change", "CHG-SF-1013", None, ["SF-QRY-013"], ["COMPLIANT_EXECUTION"]),
    ("13", "Privilege Escalation During Change", "change", "CHG-SF-1013", None, ["SF-QRY-014"], ["UNAPPROVED_OPERATION", "UNEXPECTED_ADDITIONAL_OPERATION", "EXPECTED_OPERATION_MISSING"]),
    ("14", "Role Revocation Outside Change Window", "change", "CHG-SF-1007", None, ["SF-QRY-015"], ["EXECUTED_OUTSIDE_WINDOW", "UNAPPROVED_OPERATION", "UNEXPECTED_ADDITIONAL_OPERATION", "EXPECTED_OPERATION_MISSING"]),
    ("15", "Warehouse Modified Outside Approved Window", "change", "CHG-SF-1014", None, ["SF-QRY-016"], ["EXECUTED_OUTSIDE_WINDOW"]),
    ("16", "Database Configuration Changed Incorrectly", "change", "CHG-SF-1003", None, ["SF-QRY-017"], ["WRONG_TARGET_OBJECT", "INSUFFICIENT_AUDIT_EVIDENCE", "EXPECTED_OPERATION_MISSING"]),
    ("17", "Unapproved User Creation", "user", None, "rogue.engineer@example.invalid", ["SF-QRY-018"], ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("18", "Unapproved Role Grant", "user", None, "rogue.engineer@example.invalid", ["SF-QRY-019"], ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("19", "Activity Without Matching Change", "user", None, "rogue.engineer@example.invalid", ["SF-QRY-020"], ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("20", "Multiple Changes by Same Implementer", "user", None, "sfsecurity01@example.invalid", ["SF-QRY-021", "SF-QRY-022"], ["COMPLIANT_EXECUTION", "UNAUTHORIZED_IMPLEMENTER"]),
]
scenarios = [{
    "scenario_id": f"SF-POST-{number}", "scenario_name": f"{number} — {name}",
    "change_id": change_id, "user_identity": identity, "evaluation_timestamp": "2026-11-24T00:00:00Z",
    "investigation_mode": mode, "evidence_query_ids": query_ids, "window_days": 20 if number == "20" else 10,
    "expected_findings": findings,
} for number, name, mode, change_id, identity, query_ids, findings in scenario_specs]

investigation_specs = [
    ("01", "Investigate Approved Change", "Investigate change CHG-SF-1007.", "snowflake_change", "CHG-SF-1007", None, ["COMPLIANT_EXECUTION", "EXECUTED_OUTSIDE_WINDOW", "UNAUTHORIZED_IMPLEMENTER", "ROLE_MISMATCH", "WRONG_TARGET_OBJECT", "UNAPPROVED_OPERATION", "UNEXPECTED_ADDITIONAL_OPERATION"]),
    ("02", "Investigate Out-of-Window Change", "Was CHG-SF-1014 implemented correctly?", "snowflake_change", "CHG-SF-1014", None, ["EXECUTED_OUTSIDE_WINDOW"]),
    ("03", "Investigate Unauthorized Role Grant", "Find unexpected role grants in the last 10 days.", "snowflake_unapproved", None, None, ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("04", "Investigate User Activity / Last 10 Days", "Investigate rogue.engineer@example.invalid for the last 10 days.", "snowflake_user", None, "rogue.engineer@example.invalid", ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("05", "Investigate User Activity / Last 15 Days", "Show changes performed by rogue.engineer@example.invalid during the last 15 days.", "snowflake_user", None, "rogue.engineer@example.invalid", ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("06", "Find Unexpected Administrative Actions", "Show database modifications performed without approved changes.", "snowflake_unapproved", None, None, ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("07", "Investigate Privilege Escalation", "Find privilege escalation activity in Snowflake during the last 10 days.", "snowflake_unapproved", None, None, ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("08", "Investigate Failed Snowflake Changes", "Investigate change CHG-SF-1008.", "snowflake_change", "CHG-SF-1008", None, ["WRONG_TARGET_OBJECT", "FAILED_EXECUTION", "EXPECTED_OPERATION_MISSING"]),
    ("09", "Identify Wrong Target Modifications", "Investigate change CHG-SF-1022.", "snowflake_change", "CHG-SF-1022", None, ["WRONG_TARGET_OBJECT", "EXPECTED_OPERATION_MISSING"]),
    ("10", "Investigate ACCOUNTADMIN Usage", "Which Snowflake changes were performed using ACCOUNTADMIN in the last 30 days?", "snowflake_unapproved", None, None, ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("11", "Investigate Missing Change Execution", "Investigate change CHG-SF-1017.", "snowflake_change", "CHG-SF-1017", None, ["NO_EXECUTION_EVIDENCE", "EXPECTED_OPERATION_MISSING"]),
    ("12", "Investigate Multiple Changes by One User", "Investigate sfsecurity01@example.invalid for the last 20 days.", "snowflake_user", None, "sfsecurity01@example.invalid", ["COMPLIANT_EXECUTION", "EXECUTED_OUTSIDE_WINDOW", "ROLE_MISMATCH", "WRONG_TARGET_OBJECT", "UNAPPROVED_OPERATION", "UNEXPECTED_ADDITIONAL_OPERATION", "UNAUTHORIZED_IMPLEMENTER"]),
    ("13", "Investigate Unapproved Object Creation", "Find unapproved user creation in Snowflake during the last 10 days.", "snowflake_unapproved", None, None, ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("14", "Investigate Role Revocation", "Find role revocation activity in Snowflake during the last 30 days.", "snowflake_unapproved", None, None, ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
    ("15", "Investigate Activity Without Approved Change", "Find Snowflake activity without approved changes during the last 10 days.", "snowflake_unapproved", None, None, ["POSSIBLE_UNAPPROVED_ACTIVITY"]),
]
investigation_scenarios = [{
    "scenario_id": f"SF-INV-{number}", "scenario_name": f"{number} — {name}", "investigation_prompt": prompt,
    "expected_intent": intent, "change_id": change_id, "user_identity": identity,
    "evaluation_timestamp": "2026-11-24T00:00:00Z", "expected_finding_categories": findings,
} for number, name, prompt, intent, change_id, identity, findings in investigation_specs]

write("users.json", users)
write("grants_to_users.json", grants_to_users)
write("grants_to_roles.json", grants_to_roles)
write("query_history.json", query_history)
write("access_history.json", access_history)
write("login_history.json", login_history)
write("post_implementation_scenarios.json", scenarios)
write("investigation_scenarios.json", investigation_scenarios)
print({"query_history": len(query_history), "access_history": len(access_history), "login_history": len(login_history),
       "users": len(users), "scenarios": len(scenarios)})
