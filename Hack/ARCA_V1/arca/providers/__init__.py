"""Cloud-provider adapters for synthetic evidence."""

PROVIDER_CAPABILITIES = {
    "aws": frozenset({"stage1", "stage2", "stage3", "lifecycle", "undocumented", "investigation"}),
    "azure": frozenset({"stage1", "stage2", "stage3", "lifecycle", "undocumented", "investigation"}),
    "snowflake": frozenset({"stage1", "post_implementation", "undocumented", "investigation"}),
}


def provider_capabilities(name: str) -> frozenset[str]:
    normalized = name.lower()
    if normalized not in PROVIDER_CAPABILITIES:
        raise ValueError(f"Unsupported evidence provider: {name}")
    return PROVIDER_CAPABILITIES[normalized]


def get_provider(name: str):
    normalized = name.lower()
    if normalized == "aws":
        from . import aws
        return aws
    if normalized == "azure":
        from . import azure
        return azure
    if normalized == "snowflake":
        from . import snowflake
        return snowflake
    raise ValueError(f"Unsupported evidence provider: {name}")
