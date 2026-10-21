from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _enabled(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LlmSettings:
    enabled: bool
    provider: str
    endpoint: str
    model: str
    api_key: str = field(repr=False)
    api_version: str = ""
    timeout_seconds: float = 20.0
    input_max_chars: int = 30000
    max_output_tokens: int = 1200
    reasoning_effort: str = "minimal"

    @property
    def configured(self) -> bool:
        if not self.enabled or self.provider not in {"openai", "azure_openai", "openai_compatible"}:
            return False
        if not self.endpoint or not self.model or not self.api_key:
            return False
        if self.provider == "azure_openai" and not self.api_version:
            return False
        parsed = urlparse(self.endpoint)
        return parsed.scheme == "https" and bool(parsed.netloc)

    @property
    def status(self) -> str:
        if not self.enabled:
            return "disabled"
        return "available" if self.configured else "configuration_error"


def llm_settings() -> LlmSettings:
    timeout_text = os.getenv("ARCA_LLM_TIMEOUT_SECONDS", "20").strip()
    try:
        timeout = float(timeout_text)
    except ValueError as exc:
        raise ValueError("ARCA_LLM_TIMEOUT_SECONDS must be numeric") from exc
    if not 1 <= timeout <= 120:
        raise ValueError("ARCA_LLM_TIMEOUT_SECONDS must be between 1 and 120")
    input_limit_text = os.getenv("ARCA_LLM_INPUT_MAX_CHARS", "30000").strip()
    try:
        input_limit = int(input_limit_text)
    except ValueError as exc:
        raise ValueError("ARCA_LLM_INPUT_MAX_CHARS must be an integer") from exc
    if not 2000 <= input_limit <= 100000:
        raise ValueError("ARCA_LLM_INPUT_MAX_CHARS must be between 2000 and 100000")
    max_output_text = os.getenv("ARCA_LLM_MAX_OUTPUT_TOKENS", "1200").strip()
    try:
        max_output_tokens = int(max_output_text)
    except ValueError as exc:
        raise ValueError("ARCA_LLM_MAX_OUTPUT_TOKENS must be an integer") from exc
    if not 100 <= max_output_tokens <= 10000:
        raise ValueError("ARCA_LLM_MAX_OUTPUT_TOKENS must be between 100 and 10000")
    reasoning_effort = os.getenv("ARCA_LLM_REASONING_EFFORT", "minimal").strip().casefold()
    if reasoning_effort not in {"minimal", "low", "medium", "high"}:
        raise ValueError("ARCA_LLM_REASONING_EFFORT must be minimal, low, medium, or high")
    provider = os.getenv("ARCA_LLM_PROVIDER", "").strip().casefold()
    configured_endpoint = os.getenv("ARCA_LLM_ENDPOINT", "").strip().rstrip("/")
    endpoint = configured_endpoint or ("https://api.openai.com" if provider == "openai" else "")
    return LlmSettings(
        enabled=_enabled(os.getenv("ARCA_LLM_ENABLED", "false")),
        provider=provider,
        endpoint=endpoint,
        model=os.getenv("ARCA_LLM_MODEL", "").strip(),
        api_key=os.getenv("ARCA_LLM_API_KEY", "").strip(),
        api_version=os.getenv("ARCA_LLM_API_VERSION", "").strip(),
        timeout_seconds=timeout,
        input_max_chars=input_limit,
        max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort,
    )


def data_path(provider: str) -> Path:
    if provider not in {"aws", "azure", "snowflake"}:
        raise ValueError(f"Unsupported provider: {provider}")
    return PROJECT_ROOT / "data" / provider


def log_path() -> Path:
    configured = os.getenv("ARCA_LOG_DIR")
    if not configured:
        return PROJECT_ROOT / "logs"
    candidate = Path(configured).expanduser()
    if candidate.is_absolute():
        return candidate
    resolved = (PROJECT_ROOT / candidate).resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError("Relative ARCA_LOG_DIR must remain within ARCA V2")
    return resolved


def cors_origins() -> list[str]:
    configured = os.getenv("ARCA_API_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    origins = [item.strip().rstrip("/") for item in configured.split(",") if item.strip()]
    if not origins or "*" in origins:
        raise ValueError("ARCA_API_CORS_ORIGINS must contain explicit origins and cannot use a wildcard")
    return list(dict.fromkeys(origins))
