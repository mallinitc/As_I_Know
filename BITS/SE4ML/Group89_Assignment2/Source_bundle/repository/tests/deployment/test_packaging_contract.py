from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

SOLUTION_ROOT = Path("/home/jovyan/chest-xray-ai-assistant").resolve()

API_DOCKERFILE = SOLUTION_ROOT / "Dockerfile.api"

UI_DOCKERFILE = SOLUTION_ROOT / "Dockerfile.ui"

COMPOSE_FILE = SOLUTION_ROOT / "docker-compose.yaml"

REQUIREMENT_FILES = [
    SOLUTION_ROOT / "requirements.txt",
    SOLUTION_ROOT / "requirements.api.txt",
    SOLUTION_ROOT / "requirements.ui.txt",
]

PINNED_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9_.-]+" r"(?:\[[A-Za-z0-9_,.-]+\])?" r"==[^\s;]+" r"(?:\s*;.*)?$"
)


def significant_lines(
    path: Path,
) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def docker_instructions(
    path: Path,
) -> set[str]:
    return {line.split(maxsplit=1)[0].upper() for line in significant_lines(path)}


def docker_transfer_instructions(
    path: Path,
) -> list[str]:
    logical_lines: list[str] = []
    current_line = ""

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped_line = raw_line.strip()

        if not stripped_line or stripped_line.startswith("#"):
            continue

        current_line = (
            f"{current_line} {stripped_line}" if current_line else stripped_line
        )

        if current_line.endswith("\\"):
            current_line = current_line[:-1].strip()
            continue

        logical_lines.append(current_line)
        current_line = ""

    if current_line:
        logical_lines.append(current_line)

    return [
        line
        for line in logical_lines
        if line.upper().startswith(
            (
                "COPY ",
                "ADD ",
            )
        )
    ]


def compose_configuration() -> dict[str, Any]:
    configuration = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))

    assert isinstance(configuration, dict)

    return configuration


def dependency_names(
    depends_on: object,
) -> set[str]:
    if isinstance(depends_on, dict):
        return set(depends_on)

    if isinstance(depends_on, list):
        return {str(dependency) for dependency in depends_on}

    return set()


def published_ports(
    service: dict[str, Any],
) -> set[str]:
    ports = service.get("ports", [])

    return {str(port) for port in ports}


@pytest.mark.parametrize(
    "path",
    [
        API_DOCKERFILE,
        UI_DOCKERFILE,
        COMPOSE_FILE,
        *REQUIREMENT_FILES,
    ],
)
def test_required_packaging_file_exists(
    path: Path,
) -> None:
    assert path.is_file()
    assert path.stat().st_size > 0


@pytest.mark.parametrize(
    ("dockerfile", "entrypoint_token"),
    [
        (API_DOCKERFILE, "uvicorn"),
        (UI_DOCKERFILE, "streamlit"),
    ],
)
def test_container_build_and_entrypoint_contract(
    dockerfile: Path,
    entrypoint_token: str,
) -> None:
    instructions = docker_instructions(dockerfile)

    assert "FROM" in instructions
    assert "WORKDIR" in instructions
    assert "COPY" in instructions
    assert "RUN" in instructions
    assert {
        "CMD",
        "ENTRYPOINT",
    } & instructions

    content = dockerfile.read_text(encoding="utf-8").lower()

    assert entrypoint_token in content


def test_compose_service_topology() -> None:
    configuration = compose_configuration()
    services = configuration.get(
        "services",
        {},
    )

    assert isinstance(services, dict)
    assert {"api", "ui"} <= set(services)

    api_service = services["api"]
    ui_service = services["ui"]

    assert isinstance(api_service, dict)
    assert isinstance(ui_service, dict)

    assert "healthcheck" in api_service
    assert "healthcheck" in ui_service

    assert any(
        port == "8000" or port.endswith(":8000")
        for port in published_ports(api_service)
    )

    assert any(
        port == "8501" or port.endswith(":8501") for port in published_ports(ui_service)
    )

    assert "api" in dependency_names(ui_service.get("depends_on"))


def test_all_direct_dependencies_are_pinned() -> None:
    direct_requirements: list[str] = []

    for path in REQUIREMENT_FILES:
        for line in significant_lines(path):
            if line.startswith(
                (
                    "-r ",
                    "--requirement ",
                    "--extra-index-url ",
                    "--index-url ",
                    "--find-links ",
                )
            ):
                continue

            direct_requirements.append(line)

    assert direct_requirements

    unpinned_requirements = [
        requirement
        for requirement in direct_requirements
        if PINNED_REQUIREMENT.fullmatch(requirement) is None
    ]

    assert unpinned_requirements == []


def test_large_runtime_artifacts_are_not_copied() -> None:
    transfer_content = "\n".join(
        instruction
        for dockerfile in [
            API_DOCKERFILE,
            UI_DOCKERFILE,
        ]
        for instruction in docker_transfer_instructions(dockerfile)
    ).lower()

    forbidden_copy_sources = [
        "chestmnist_224.npz",
        "train_images.npy",
        "val_images.npy",
        "test_images.npy",
        "model_state_dict.pt",
        "model.safetensors",
        "/home/jovyan/apicdsa2-datavol-1",
    ]

    explicitly_copied_artifacts = [
        reference
        for reference in forbidden_copy_sources
        if reference in transfer_content
    ]

    assert explicitly_copied_artifacts == []
