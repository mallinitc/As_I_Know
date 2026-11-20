from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderDefinition:
    name: str
    display_name: str
    capabilities: tuple[str, ...]


PROVIDERS: dict[str, ProviderDefinition] = {
    "aws": ProviderDefinition("aws", "AWS", ("change_quality_validation", "access_validation", "execution_assurance")),
    "azure": ProviderDefinition("azure", "Azure", ("change_quality_validation", "access_validation", "execution_assurance")),
    "snowflake": ProviderDefinition(
        "snowflake", "Snowflake", ("change_access_validation", "execution_assurance"),
    ),
}


def provider_definition(name: str) -> ProviderDefinition:
    normalized = (name or "").strip().lower()
    try:
        return PROVIDERS[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported provider: {name}") from exc
