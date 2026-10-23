"""Custom Snowflake role model: default roles for infrastructure only."""
from __future__ import annotations

import re

import pytest

from backend.repositories.snowflake import SnowflakeRepository
from backend.services.ask_arca import AskArcaService
from backend.services.snowflake_execution import SnowflakeExecutionService
from backend.services.snowflake_roles import DEFAULT_ROLES, is_data_operation
from backend.services.snowflake_validation import assess_role
from backend.services.timestamps import parse_utc


ROLE_NAME = re.compile(r"^(DB_[A-Z]+(_C)?_RL|[A-Z]+_[A-Z]+_(R|W|C)_RL|WH_[A-Z]+_(U|O)_RL|[A-Z_]+_FR)$")


@pytest.fixture(scope="module")
def repository():
    return SnowflakeRepository()


@pytest.fixture(scope="module")
def catalog(repository):
    return repository.validation_catalog()


@pytest.fixture(scope="module")
def changes(repository):
    return {item["change_id"]: item for item in repository.changes()}


def test_custom_roles_follow_the_naming_convention(catalog):
    for item in catalog["roles"]:
        name = item["role_name"]
        if name in DEFAULT_ROLES or name == "CATALOG_INCOMPLETE_ROLE":
            continue
        assert ROLE_NAME.match(name), name


def test_schema_roles_layer_read_write_create(catalog):
    edges = {(item["granted_role"], item["grantee_role"]) for item in catalog["role_grants"]}
    for prefix in ("FINANCE_REPORTING", "FINANCE_STAGING", "MARKETING_REPORTING", "DEV_STAGING"):
        assert (f"{prefix}_R_RL", f"{prefix}_W_RL") in edges
        assert (f"{prefix}_W_RL", f"{prefix}_C_RL") in edges
    functional = {item["role_name"] for item in catalog["roles"] if item["role_name"].endswith("_FR")}
    assert functional and all((name, "SYSADMIN") in edges for name in functional)


def test_object_privileges_are_held_only_by_custom_roles(catalog):
    for grant in catalog["object_grants"]:
        if grant["object_type"] in {"DATABASE", "SCHEMA", "TABLE"}:
            assert grant["grantee_role"] not in DEFAULT_ROLES, grant["grant_id"]


@pytest.mark.parametrize(("operation", "expected"), [
    ("CREATE DATABASE", True), ("ALTER TABLE", True), ("CREATE SCHEMA", True), ("GRANT SELECT", True), ("REVOKE INSERT", True),
    ("GRANT ROLE", False), ("CREATE USER", False), ("ALTER WAREHOUSE", False), ("UPDATE NETWORK CONTROLS", False),
])
def test_infrastructure_and_data_operations_are_separated(operation, expected):
    assert is_data_operation(operation) is expected


def test_default_role_for_schema_change_is_overprivileged(catalog, changes):
    result = assess_role(changes["CHG-SF-1024"], catalog)
    assert result["status"] == "OVERPRIVILEGED"
    assert result["recommended_role"] == "DB_FINANCE_C_RL"
    finding = next(item for item in result["findings"] if isinstance(item, dict))
    assert finding["category"] == "DEFAULT_ROLE_FOR_DATA_CHANGE" and finding["recommended_role"] == "DB_FINANCE_C_RL"


def test_custom_database_role_for_schema_change_is_appropriate(catalog, changes):
    assert assess_role(changes["CHG-SF-1025"], catalog)["status"] == "APPROPRIATE"


def test_default_roles_stay_appropriate_for_infrastructure(catalog, changes):
    for change_id in ("CHG-SF-1007", "CHG-SF-1010"):
        result = assess_role(changes[change_id], catalog)
        assert result["status"] == "APPROPRIATE", change_id
        assert not any(isinstance(item, dict) for item in result["findings"])


def test_insufficient_default_role_still_reports_the_policy_finding(catalog, changes):
    result = assess_role(changes["CHG-SF-1005"], catalog)
    assert result["status"] == "INSUFFICIENT_PRIVILEGES"
    assert any(isinstance(item, dict) and item["category"] == "DEFAULT_ROLE_FOR_DATA_CHANGE" for item in result["findings"])


def test_object_grant_is_covered_by_ownership(catalog, changes):
    result = assess_role(changes["CHG-SF-1013"], catalog)
    assert result["requested_role"] == "FINANCE_STAGING_C_RL" and result["status"] == "APPROPRIATE"


def test_execution_flags_default_role_queries_for_data_changes(repository):
    service = SnowflakeExecutionService(repository)
    table_change = service.assess_change("CHG-SF-1008", parse_utc("2026-11-24T00:00:00Z"))
    assert "DEFAULT_ROLE_FOR_DATA_CHANGE" in {item["category"] for item in table_change["findings"]}
    grant_change = service.assess_change("CHG-SF-1007", parse_utc("2026-11-24T00:00:00Z"), "SF-POST-01")
    assert "DEFAULT_ROLE_FOR_DATA_CHANGE" not in {item["category"] for item in grant_change["findings"]}
    rogue = service.assess_user("rogue.engineer@example.invalid", 30, parse_utc("2026-11-24T00:00:00Z"), "SF-POST-19")
    assert {"POSSIBLE_UNAPPROVED_ACTIVITY", "DEFAULT_ROLE_FOR_DATA_CHANGE"} <= {item["category"] for item in rogue["findings"]}


def test_ask_arca_recognizes_custom_role_names():
    intent = AskArcaService().parse("Investigate activities using FIN_DDL_FR in Snowflake in the last 30 days.")
    assert intent["role"] == "FIN_DDL_FR" and intent["investigation_type"] == "role_investigation"
