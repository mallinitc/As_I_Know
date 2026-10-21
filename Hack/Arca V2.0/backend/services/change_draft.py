from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from backend.llm.gateway import LlmGateway, LlmGatewayError
from backend.repositories.aws import AwsRepository
from backend.repositories.azure import AzureRepository
from backend.repositories.snowflake import SnowflakeRepository


PROSE_FIELDS = (
    "change_title", "business_justification", "implementation_steps", "validation_plan",
    "rollback_plan", "expected_outcome", "risk_and_impact",
)
REQUIRED_FIELDS = (
    "change_title", "business_justification", "environment", "resource_name_or_id", "implementer",
    "change_start", "change_end", "implementation_steps", "validation_plan", "rollback_plan",
    "expected_outcome", "risk_and_impact",
)


class ChangeDraftNotFound(LookupError):
    pass


def _resource_parts(resource: str) -> tuple[str, str]:
    subscription = re.search(r"/subscriptions/([^/]+)", resource, re.I)
    group = re.search(r"/resourceGroups/([^/]+)", resource, re.I)
    return (subscription.group(1) if subscription else "", group.group(1) if group else "")


class ChangeDraftService:
    def __init__(self, gateway: LlmGateway | None = None) -> None:
        self.gateway = gateway

    @staticmethod
    def _change(provider: str, change_id: str) -> dict[str, Any]:
        repositories = {"aws": AwsRepository, "azure": AzureRepository, "snowflake": SnowflakeRepository}
        change = next((item for item in repositories[provider]().changes() if item.get("change_id") == change_id), None)
        if change is None:
            raise ChangeDraftNotFound(change_id)
        return change

    @staticmethod
    def _baseline(provider: str, change: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        expected = change.get("expected") or []
        resources = [str(item.get("resource_id") or item.get("resource") or "") for item in expected]
        operations = [str(item.get("operation") or item.get("eventName") or "") for item in expected]
        resource = "; ".join(item for item in resources if item)
        subscription, resource_group = _resource_parts(resource)
        implementer = change.get("implementer")
        if isinstance(implementer, dict):
            implementer = implementer.get("principal_name") or implementer.get("principal_id") or ""
        implementer = str(implementer or change.get("actor") or "")
        context = change.get("snowflake_context") or {}
        title = str(change.get("short_description") or change.get("description") or "")
        description = str(change.get("description") or "")
        draft = {
            "change_title": title,
            "change_number": str(change.get("change_id") or ""),
            "business_justification": str(change.get("business_justification") or ""),
            "environment": str(change.get("environment") or ""),
            "subscription": subscription,
            "resource_group": resource_group,
            "resource_name_or_id": resource,
            "implementer": implementer,
            "change_start": str(change.get("start") or ""),
            "change_end": str(change.get("end") or ""),
            "timezone": "UTC" if str(change.get("start") or "").endswith("Z") and str(change.get("end") or "").endswith("Z") else "",
            "required_role": str(context.get("requested_role") or ""),
            "required_access_scope": resource,
            "implementation_steps": [f"Perform {operation} on {target}" for operation, target in zip(operations, resources) if operation and target],
            "validation_plan": list(change.get("validation_steps") or []),
            "rollback_plan": str(change.get("rollback_plan") or ""),
            "expected_outcome": str(change.get("expected_outcome") or ""),
            "risk_and_impact": str(change.get("risk") or ""),
        }
        evidence_ids = [str(change.get("sys_id") or change.get("change_id"))]
        # A description may explicitly contain rollback prose, but it is not parsed into an invented procedure.
        if provider == "aws" and "rollback" in description.casefold() and not draft["rollback_plan"]:
            draft["rollback_plan"] = description
        return draft, evidence_ids

    def improve(self, provider: str, change_id: str, execution_mode: str) -> dict[str, Any]:
        change = self._change(provider, change_id)
        draft, evidence_ids = self._baseline(provider, change)
        result = {
            "provider": provider, "change_id": change_id, "draft": deepcopy(draft),
            "missing_fields": [field for field in REQUIRED_FIELDS if not draft.get(field)],
            "source_evidence_ids": evidence_ids, "llm_invoked": False, "llm_status": "not_invoked",
            "model_identifier": None, "token_usage": None,
            "disclosure": "Template assembled from authoritative change evidence; no AI refinement was requested.",
        }
        if execution_mode != "llm_assisted":
            return result
        gateway = self.gateway or LlmGateway()
        capability = gateway.capability()
        result["model_identifier"] = capability.get("model_identifier")
        if not capability.get("available"):
            result["llm_status"] = str(capability.get("status") or "unavailable")
            result["disclosure"] = "AI refinement was unavailable; the editable template contains source evidence only."
            return result
        try:
            refined, model, usage = gateway.improve_draft(draft)
        except LlmGatewayError as exc:
            result["llm_status"] = exc.status
            result["disclosure"] = "AI refinement failed; the editable template contains source evidence only."
            return result
        values = refined.model_dump()
        for field in PROSE_FIELDS:
            original = draft[field]
            candidate = values[field]
            # Empty source fields must stay empty and populated fields may only be refined.
            result["draft"][field] = candidate if original not in ("", []) and candidate not in ("", []) else original
        result.update({
            "llm_invoked": True, "llm_status": "completed", "model_identifier": model,
            "token_usage": usage.model_dump(),
            "disclosure": "Advisory AI refinement used only source-supported prose; technical facts remain unchanged.",
        })
        return result
