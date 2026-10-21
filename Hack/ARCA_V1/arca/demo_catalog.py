"""Read-only access to evaluator-backed hackathon demo scenarios."""
from __future__ import annotations

import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "demo_catalog.json"


def load_demo_catalog() -> list[dict]:
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        scenarios = json.load(handle)
    required = {"scenario_id", "name", "feature", "associated_change_number",
                "pim_request_ids", "user_identity", "resource_identifiers",
                "expected_outcome", "explanation", "relevant_evidence_ids", "inputs"}
    for scenario in scenarios:
        missing = required - scenario.keys()
        if missing:
            raise ValueError(f"Demo scenario {scenario.get('scenario_id', '<unknown>')} is missing {sorted(missing)}")
    return scenarios


def demo_scenarios(feature: str, provider: str | None = None) -> list[dict]:
    return [item for item in load_demo_catalog()
            if item["feature"] == feature and (provider is None or item.get("provider", "azure") == provider)]


def demo_scenario(scenario_id: str) -> dict:
    return next(item for item in load_demo_catalog() if item["scenario_id"] == scenario_id)


def pim_records_json(scenario: dict, bundle: dict) -> str:
    """Return exact source records for a paste demo without changing evidence."""
    wanted = set(scenario.get("pim_request_ids", []))
    records = [item for item in bundle.get("access_requests", []) if item.get("pim_request_id") in wanted]
    return json.dumps(records, indent=2)


def stage1_demo_text(variant: str) -> str:
    """Build deterministic pasted input variants used by the catalog and UI."""
    resource = "/subscriptions/00000000-1111-2222-3333-444444444444/resourceGroups/rg-arca-prod/providers/Microsoft.Storage/storageAccounts/starchprod01"
    lines = [
        "Purpose: Rotate the application storage configuration",
        "Business Justification: Maintain the approved security baseline",
        "Environment: production", "Implementer: engineer01@example.invalid",
        f"Target Resource: {resource}",
        "Implementation Tasks: Update the resource configuration; verify the deployment completes",
        "Start: 2026-10-22T10:00:00Z", "End: 2026-10-22T11:00:00Z",
        "Expected Outcome: The approved configuration is active",
        "Post-change Validation: Confirm service health; test application access",
        "Rollback Plan: Restore the previous configuration from the captured baseline",
        "Risk and Impact: Moderate risk with a five minute application interruption",
        "Role Requirements: Contributor", "Scope Requirements: Resource scope only",
        f"Expected Operations: Microsoft.Storage/storageAccounts/write @ {resource}",
    ]
    if variant == "missing_implementer": lines = [x for x in lines if not x.startswith("Implementer:")]
    if variant == "missing_resource": lines = [x for x in lines if not x.startswith(("Target Resource:", "Expected Operations:"))]
    if variant == "reversed_window": lines = ["End: 2026-10-22T09:00:00Z" if x.startswith("End:") else x for x in lines]
    if variant == "ambiguous_task": lines = ["Implementation Tasks: Update as needed" if x.startswith("Implementation Tasks:") else x for x in lines]
    return "\n".join(lines)
