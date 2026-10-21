"""Provider-independent extraction adapters. Mock mode only extracts explicit text."""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

from .change_models import ExpectedOperation, ExtractedChange
from .llm_provider import get_llm_provider


FIELDS = {
    "purpose": "purpose", "change title": "title", "title": "title", "change number": "change_id",
    "business justification": "business_justification",
    "environment": "environment", "implementer": "implementer", "resource": "target_resources",
    "target resource": "target_resources", "scope": "scope_requirements",
    "subscription": "subscription", "resource group": "resource_group", "resource name": "resource_name",
    "implementation tasks": "implementation_tasks", "implementation plan": "implementation_tasks",
    "start": "start", "start time": "start", "end": "end", "end time": "end",
    "timezone": "timezone",
    "expected outcome": "expected_outcome", "post-change validation": "validation_steps",
    "validation steps": "validation_steps", "rollback plan": "rollback_plan",
    "risk and impact": "risk_impact", "risk/impact": "risk_impact",
    "role requirements": "role_requirements", "scope requirements": "scope_requirements",
    "expected operations": "expected_operations",
}
LIST_FIELDS = {"target_resources", "implementation_tasks", "validation_steps", "role_requirements", "scope_requirements"}


class ChangeExtractor(ABC):
    @abstractmethod
    def extract(self, text: str, provider: str, overrides: dict[str, Any] | None = None) -> ExtractedChange: ...


def _parts(value: str) -> list[str]:
    return [item.strip(" -\t") for item in re.split(r"[;|]", value) if item.strip(" -\t")]


class MockChangeExtractor(ChangeExtractor):
    """Deterministic label parser; it does not perform semantic inference."""
    def extract(self, text: str, provider: str, overrides: dict[str, Any] | None = None) -> ExtractedChange:
        values: dict[str, Any] = {"provider": provider, "source_mode": "pasted", "raw_text": text}
        seen: dict[str, list[str]] = {}
        for line in text.splitlines():
            match = re.match(r"^\s*([A-Za-z][A-Za-z /_-]+?)\s*:\s*(.+?)\s*$", line)
            if not match: continue
            key = FIELDS.get(match.group(1).strip().lower())
            if not key: continue
            value = match.group(2).strip()
            seen.setdefault(key, []).append(value)
            if key == "expected_operations":
                operations = []
                for part in _parts(value):
                    op, _, resource = part.partition(" @ ")
                    operations.append(ExpectedOperation(operation=op.strip(), resource_id=resource.strip()))
                values[key] = operations
            elif key in LIST_FIELDS:
                values[key] = _parts(value)
            else:
                values[key] = value
        conflicts = [f"Conflicting values supplied for {key}: {items}" for key, items in seen.items() if len(set(items)) > 1]
        for key, value in (overrides or {}).items():
            if value:
                values[key] = [value] if key == "target_resources" and isinstance(value, str) else value
        values["conflicts"] = conflicts
        return ExtractedChange.model_validate(values)


class BedrockChangeExtractor(ChangeExtractor):
    """Configurable structured extraction; network/model calls occur only when selected."""
    def extract(self, text: str, provider: str, overrides: dict[str, Any] | None = None) -> ExtractedChange:
        import boto3
        model_id = os.getenv("ARCA_BEDROCK_MODEL_ID")
        if not model_id:
            raise RuntimeError("ARCA_BEDROCK_MODEL_ID is not configured")
        client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        prompt = ("Extract only facts explicitly present and refine narrative wording for a professional change record. "
                  "Never add unsupported facts. Preserve identifiers, resource IDs, IP addresses, identities, permissions, "
                  "and timestamps character-for-character; leave unsupported values empty. Return JSON matching this schema:\n"
                  + json.dumps(ExtractedChange.model_json_schema()) + "\nTEXT:\n" + text)
        response = client.converse(modelId=model_id, messages=[{"role": "user", "content": [{"text": prompt}]}])
        payload = response["output"]["message"]["content"][0]["text"]
        values = json.loads(payload)
        values.update({"provider": provider, "source_mode": "pasted", "extraction_mode": "bedrock", "raw_text": text})
        values.update({k: v for k, v in (overrides or {}).items() if v})
        return ExtractedChange.model_validate(values)


class LLMChangeExtractor(ChangeExtractor):
    """Provider-neutral structured extraction with Pydantic validation."""
    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def extract(self, text: str, provider: str, overrides: dict[str, Any] | None = None) -> ExtractedChange:
        instructions = (
            "Extract and professionally structure only facts explicitly supported by the supplied change text. "
            "Identify ambiguities and contradictions. Never invent missing facts. Preserve technical identifiers, "
            "resource IDs, IP addresses, identities, permissions, and timestamps exactly. Leave unknown strings empty "
            "and unknown lists empty. Do not approve, submit, or execute the change."
        )
        result = get_llm_provider(self.provider_name).parse(instructions, text, ExtractedChange)
        values = result.model_dump()
        values.update({"provider": provider, "source_mode": "pasted", "extraction_mode": self.provider_name, "raw_text": text})
        values.update({k: v for k, v in (overrides or {}).items() if v})
        return ExtractedChange.model_validate(values)


def get_extractor(mode: str | None = None) -> ChangeExtractor:
    selected = (mode or os.getenv("ARCA_CHANGE_EXTRACTOR") or os.getenv("LLM_PROVIDER", "mock")).lower()
    if selected == "mock": return MockChangeExtractor()
    if selected in {"openai", "bedrock"}: return LLMChangeExtractor(selected)
    raise ValueError(f"Unsupported change extraction mode: {selected}")


def extract_existing_change(record: dict, provider: str) -> ExtractedChange:
    expected = record.get("expected", [])
    operations = [ExpectedOperation(operation=x.get("operation") or x.get("eventName", ""), resource_id=x.get("resource_id") or x.get("resource", "")) for x in expected]
    actor = record.get("implementer", {})
    implementer = (actor.get("principal_name") or actor.get("principal_id")) if isinstance(actor, dict) else (actor or record.get("actor", ""))
    description = record.get("description", "")
    rollback = description[description.lower().find("rollback"):].strip(" .") if "rollback" in description.lower() else ""
    return ExtractedChange(
        change_id=record.get("change_id"), provider=provider, source_mode="existing", purpose=description,
        business_justification=record.get("business_justification", ""), environment=record.get("environment", ""),
        target_resources=[x.resource_id for x in operations if x.resource_id], implementer=implementer or "",
        implementation_tasks=[x.operation for x in operations if x.operation], start=record.get("start", ""), end=record.get("end", ""),
        expected_outcome=record.get("expected_outcome", ""), validation_steps=record.get("validation_steps", []),
        rollback_plan=record.get("rollback_plan", rollback), risk_impact=record.get("risk_impact") or record.get("risk", ""),
        role_requirements=record.get("role_requirements", []), scope_requirements=record.get("scope_requirements", []),
        expected_operations=operations, raw_text=description,
    )
