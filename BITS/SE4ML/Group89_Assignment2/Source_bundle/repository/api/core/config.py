"""Environment-aware immutable API service settings."""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_SOLUTION_ROOT = Path("/home/jovyan/chest-xray-ai-assistant")
DEFAULT_DATA_ROOT = Path("/home/jovyan/apicdsa2-datavol-1/chest-xray-ai-assistant-data")


class ServiceSettings(BaseModel):
    """Validated paths, versions, and upload limits for the API."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
    )

    api_title: str = "API-Driven Chest X-Ray Analysis and Explanation Assistant"
    api_version: Literal["v1"] = "v1"
    api_prefix: Literal["/api/v1"] = "/api/v1"

    computer_vision_model_version: str = "resnet18-chestmnist-v1"
    language_model_version: str = "flan-t5-small-chestmnist-v1"
    prompt_registry_version: str = "grounded-language-prompts-v1"

    solution_root: Path
    data_root: Path
    api_output_dir: Path

    computer_vision_metadata_path: Path
    computer_vision_weights_path: Path
    language_model_dir: Path
    language_model_metadata_path: Path
    prompt_registry_path: Path
    explainability_metadata_path: Path
    language_guardrail_summary_path: Path
    language_evaluation_metrics_path: Path

    mlflow_tracking_uri: str

    maximum_upload_bytes: int = Field(gt=0)
    supported_image_media_types: tuple[
        Literal["image/png", "image/jpeg"],
        ...,
    ]

    educational_use_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_artifacts(
        self,
    ) -> "ServiceSettings":
        if not self.solution_root.is_dir():
            raise ValueError("The configured solution root is unavailable.")

        if not self.data_root.is_dir():
            raise ValueError("The configured data root is unavailable.")

        required_files = [
            self.computer_vision_metadata_path,
            self.computer_vision_weights_path,
            self.language_model_metadata_path,
            self.language_model_dir / "config.json",
            self.language_model_dir / "model.safetensors",
            self.prompt_registry_path,
            self.explainability_metadata_path,
            self.language_guardrail_summary_path,
            self.language_evaluation_metrics_path,
        ]

        missing_files = [
            str(file_path) for file_path in required_files if not file_path.is_file()
        ]

        if missing_files:
            raise ValueError(
                "Required frozen artifacts are missing: " + ", ".join(missing_files)
            )

        return self

    def sanitized_lineage(
        self,
    ) -> dict[str, Any]:
        """Return client-safe lineage without internal paths."""

        return {
            "api_version": self.api_version,
            "computer_vision_model_version": (self.computer_vision_model_version),
            "language_model_version": (self.language_model_version),
            "prompt_registry_version": (self.prompt_registry_version),
            "educational_use_only": (self.educational_use_only),
        }


def load_yaml_file(
    file_path: Path,
) -> dict[str, Any]:
    """Load one required YAML mapping."""

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        loaded_value = yaml.safe_load(file)

    if not isinstance(loaded_value, dict):
        raise ValueError(f"Expected a YAML mapping: {file_path.name}")

    return loaded_value


def load_json_file(
    file_path: Path,
) -> dict[str, Any]:
    """Load one required JSON object."""

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        loaded_value = json.load(file)

    if not isinstance(loaded_value, dict):
        raise ValueError(f"Expected a JSON object: {file_path.name}")

    return loaded_value


@lru_cache(maxsize=1)
def get_settings() -> ServiceSettings:
    """Create and cache the validated service settings."""

    solution_root = Path(
        os.getenv(
            "CHEST_XRAY_SOLUTION_ROOT",
            str(DEFAULT_SOLUTION_ROOT),
        )
    )
    data_root = Path(
        os.getenv(
            "CHEST_XRAY_DATA_ROOT",
            str(DEFAULT_DATA_ROOT),
        )
    )

    computer_vision_model_version = "resnet18-chestmnist-v1"
    language_model_version = "flan-t5-small-chestmnist-v1"

    return ServiceSettings(
        solution_root=solution_root,
        data_root=data_root,
        api_output_dir=(data_root / "outputs" / "api"),
        computer_vision_metadata_path=(
            data_root / "models" / computer_vision_model_version / "model_metadata.yaml"
        ),
        computer_vision_weights_path=(
            data_root / "models" / computer_vision_model_version / "model_state_dict.pt"
        ),
        language_model_dir=(data_root / "models" / language_model_version),
        language_model_metadata_path=(
            data_root / "models" / language_model_version / "model_metadata.yaml"
        ),
        prompt_registry_path=(solution_root / "configs" / "prompt_registry.yaml"),
        explainability_metadata_path=(
            data_root / "explainability" / "explainability_metadata.yaml"
        ),
        language_guardrail_summary_path=(
            data_root / "outputs" / "language" / "language_guardrail_summary.json"
        ),
        language_evaluation_metrics_path=(
            data_root / "outputs" / "language" / "language_evaluation_metrics.json"
        ),
        mlflow_tracking_uri=("file://" + str(data_root / "mlflow")),
        maximum_upload_bytes=(10 * 1024 * 1024),
        supported_image_media_types=(
            "image/png",
            "image/jpeg",
        ),
    )
