"""Optional provider-neutral workflow narrative (legacy module name retained)."""
from __future__ import annotations

import json
from pydantic import BaseModel

from .llm_provider import configured_provider, get_llm_provider, safe_provider_error


class WorkflowNarrative(BaseModel):
    narrative: str


def explain(summary: dict) -> str:
    provider = configured_provider()
    if provider == "mock":
        return "MOCK NARRATIVE: Findings are preliminary; validate them against approved changes and original provider evidence. Matching activity does not by itself prove the intended resource state."
    instructions = (
        "Summarize these change-control findings briefly using only supplied evidence. Cite evidence IDs when present. "
        "Never invent evidence, distinguish unmatched from unauthorized, and do not approve access or execute changes."
    )
    try:
        return get_llm_provider(provider).parse(instructions, json.dumps(summary, default=str), WorkflowNarrative).narrative
    except Exception as exc:
        return safe_provider_error(provider.title(), exc)
