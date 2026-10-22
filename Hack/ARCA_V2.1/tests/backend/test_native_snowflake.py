from pathlib import Path

import pytest

from backend.config import PROJECT_ROOT, data_path
from backend.repositories.snowflake import SnowflakeRepository
from backend.services.snowflake import SnowflakeValidationService
from backend.services.snowflake_validation import (
    assess_change_quality,
    assess_change_window,
    assess_role,
    validate_change,
)
from backend.services.timestamps import parse_utc


@pytest.fixture(scope="module")
def evidence():
    repository = SnowflakeRepository()
    return repository, {item["change_id"]: item for item in repository.changes()}


def test_all_verified_scenarios_are_computed_from_evidence(evidence):
    repository, changes = evidence
    catalog = repository.validation_catalog()
    for scenario in repository.demo_scenarios():
        result = validate_change(
            changes[scenario["change_id"]],
            catalog,
            parse_utc(scenario["evaluation_timestamp"]),
        )
        expected = scenario["expected_check_outcomes"]
        assert result["change_quality"]["status"] == expected["change_quality"]
        assert result["window_assessment"]["status"] == expected["window"]
        assert result["role_assessment"]["status"] == expected["access"]
        assert result["overall_status"] == expected["overall"]


def test_overprivileged_role_uses_narrower_catalog_evidence(evidence):
    repository, changes = evidence
    result = assess_role(changes["CHG-SF-1008"], repository.validation_catalog())
    assert result["status"] == "OVERPRIVILEGED"
    assert result["recommended_role"] == "REPORTING_DDL_ADMIN"
    assert result["evidence"]


def test_insufficient_privileges_identify_uncovered_requirements(evidence):
    repository, changes = evidence
    result = assess_role(changes["CHG-SF-1001"], repository.validation_catalog())
    assert result["status"] == "INSUFFICIENT_PRIVILEGES"
    assert result["missing_privileges"]


def test_missing_change_information_is_reported(evidence):
    result = assess_change_quality(evidence[1]["CHG-SF-1015"])
    assert result["status"] == "NEEDS_INFO"
    assert {"description", "implementer", "start", "expected", "approved_state"} <= set(result["missing"])


def test_invalid_change_window_is_not_authorized(evidence):
    change = evidence[1]["CHG-SF-1003"]
    quality = assess_change_quality(change)
    window = assess_change_window(change, parse_utc("2026-11-03T10:30:00Z"))
    assert "valid_change_window" in quality["missing"]
    assert window["status"] == "NEED_MORE_INFO"


def test_service_uses_current_time_when_evaluation_time_is_omitted():
    result = SnowflakeValidationService().validate("CHG-SF-1007")
    assert result["evaluation_timestamp"]


def test_backend_has_no_legacy_arca_or_v1_imports():
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "backend").rglob("*.py")
    )
    assert "from arca" not in sources
    assert "import arca" not in sources
    assert "ARCA_V1" not in sources


def test_repository_paths_are_v2_local_and_provider_isolated():
    snowflake = data_path("snowflake").resolve()
    assert snowflake == (PROJECT_ROOT / "data" / "snowflake").resolve()
    assert snowflake != data_path("aws").resolve()
    assert snowflake != data_path("azure").resolve()
    assert "ARCA_V1" not in str(snowflake)
