"""Central, traversal-safe project paths for supported ARCA environments."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = frozenset({"aws", "azure", "snowflake"})


def validate_provider(provider: str) -> str:
    """Return a canonical provider name or reject unknown/path-like values."""
    normalized = (provider or "").strip().lower()
    if normalized not in PROVIDERS:
        raise ValueError(f"Unsupported environment provider: {provider}")
    return normalized


def _provider_dir(category: str, provider: str, *, create: bool = False) -> Path:
    path = PROJECT_ROOT / category / validate_provider(provider)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir(provider: str) -> Path:
    return _provider_dir("data", provider)


def config_dir(provider: str) -> Path:
    return _provider_dir("config", provider)


def log_root() -> Path:
    """Honor the existing test/deployment override; otherwise use project logs."""
    configured = os.getenv("ARCA_LOG_DIR")
    if not configured:
        return PROJECT_ROOT / "logs"
    candidate = Path(configured).expanduser()
    if candidate.is_absolute():
        return candidate
    resolved = (PROJECT_ROOT / candidate).resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError("Relative ARCA_LOG_DIR must remain within the project root")
    return resolved


def log_dir(provider: str | None = None, *, create: bool = False) -> Path:
    root = log_root()
    path = root / validate_provider(provider) if provider else root
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir(provider: str, *, create: bool = False) -> Path:
    path = _provider_dir("outputs", provider)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def cross_environment_output_dir(*, create: bool = False) -> Path:
    path = PROJECT_ROOT / "outputs" / "cross_environment"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
