"""Provider-neutral evidence contracts used by ARCA adapters.

Adapters retain the original provider payload under ``raw`` so identifiers and
timestamps are never lost during normalization.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict


class ExpectedOperation(TypedDict):
    operation: str
    resource_id: str


class ChangeEvidence(TypedDict):
    provider: Literal["aws", "azure", "snowflake"]
    evidence_id: str
    change_id: str
    environment: str
    actor_id: str
    actor_name: str
    window_start: str
    window_end: str
    description: str
    expected: list[ExpectedOperation]
    raw: dict[str, Any]


class PrivilegeEvidence(TypedDict):
    provider: Literal["aws", "azure"]
    evidence_id: str
    change_id: str
    principal_id: str
    principal_name: str
    role_definition_id: str
    role_name: str
    actions: list[str]
    scopes: list[str]
    valid_from: str
    valid_to: str
    raw: dict[str, Any]


class ResourceEvidence(TypedDict):
    provider: Literal["aws", "azure"]
    resource_id: str
    resource_type: str
    environment: str
    raw: dict[str, Any]


class ActivityEvidence(TypedDict):
    provider: Literal["aws", "azure"]
    evidence_id: str
    correlation_id: str
    timestamp: str
    actor_id: str
    actor_name: str
    operation: str
    resource_ids: list[str]
    successful: bool
    read_only: bool
    raw: dict[str, Any]
