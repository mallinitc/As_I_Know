from pathlib import Path

import pytest

from arca.paths import (
    PROJECT_ROOT, config_dir, cross_environment_output_dir, data_dir,
    log_dir, log_root, output_dir, validate_provider,
)


@pytest.mark.parametrize("provider", ["aws", "azure", "snowflake"])
def test_provider_paths_are_isolated_and_project_relative(provider):
    assert data_dir(provider) == PROJECT_ROOT / "data" / provider
    assert config_dir(provider) == PROJECT_ROOT / "config" / provider
    assert output_dir(provider) == PROJECT_ROOT / "outputs" / provider
    assert log_dir(provider) == log_root() / provider


@pytest.mark.parametrize("provider", ["../azure", "AWS/../../x", "", "gcp"])
def test_provider_validation_rejects_unknown_or_traversal(provider):
    with pytest.raises(ValueError):
        validate_provider(provider)


def test_runtime_directories_are_created_only_when_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCA_LOG_DIR", str(tmp_path / "telemetry"))
    target = log_dir("snowflake", create=True)
    assert target == tmp_path / "telemetry" / "snowflake"
    assert target.is_dir()
    assert cross_environment_output_dir().name == "cross_environment"


def test_relative_log_override_is_project_relative_and_cannot_escape(monkeypatch):
    monkeypatch.setenv("ARCA_LOG_DIR", "runtime/logs")
    assert log_root() == PROJECT_ROOT / "runtime" / "logs"
    monkeypatch.setenv("ARCA_LOG_DIR", "../outside")
    with pytest.raises(ValueError):
        log_root()


def test_aws_and_azure_data_locations_exist():
    assert (data_dir("aws") / "changes.json").is_file()
    assert (data_dir("azure") / "servicenow_changes.json").is_file()
