"""
AI NETRA — Rescue Assessment Readiness
Version: 1.0.0
Step: 9.13.9

Identifies missing incident evidence and explains
why rescue priority cannot currently be assessed.

Does not calculate rescue priority or flood probability.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CONTRACT_FILE = (
    ROOT / "data" /
    "ai_netra_rescue_evidence_contract_v1.json"
)

REQUIRED_INCIDENT_FIELDS = {
    "incident_timestamp": "Current incident timestamp",
    "observation_source": "Current observation source",
    "verification_status": "Verified observation status",
    "estimated_people_stranded": "People requiring assistance",
    "observed_water_depth_m": "Observed floodwater depth",
    "observed_flow_velocity_mps": "Observed water-flow velocity"
}


def assess_readiness(contract):

    evidence = contract.get("evidence", {})
    incident = evidence.get("incident", {})

    missing = []
    available = []

    for field, description in REQUIRED_INCIDENT_FIELDS.items():

        value = incident.get(field)

        if field == "verification_status":
            usable = value == "verified"
        elif isinstance(value, str):
            usable = (
                bool(value.strip())
                and value.strip().lower()
                not in ("unknown", "unavailable")
            )
        elif isinstance(value, bool):
            usable = False
        elif isinstance(value, (int, float)):
            import math
            usable = math.isfinite(value) and value >= 0
        else:
            usable = False

        if usable:
            available.append(field)
        else:
            missing.append({
                "field": field,
                "description": description
            })

    return {
        "building_id": evidence.get(
            "building", {}
        ).get("building_id"),

        "incident_fields_available": available,

        "incident_fields_missing": missing,

        "current_flooding_status": "not_established",

        "rescue_priority": "not_assessed",

        "priority_score": None,

        "human_review_required": True,

        "automated_dispatch_authorized": False,

        "explanation": (
            "Current incident evidence is incomplete or "
            "unverified. Historical geographic and satellite "
            "observations cannot establish current rescue urgency."
        )
    }


def main():

    with CONTRACT_FILE.open(
        "r", encoding="utf-8-sig"
    ) as file:
        contract = json.load(file)

    result = assess_readiness(contract)

    print("===== AI_NETRA_RESULTS_START =====")

    print(
        "INCIDENT_FIELDS_AVAILABLE:",
        len(result["incident_fields_available"])
    )

    print(
        "INCIDENT_FIELDS_MISSING:",
        len(result["incident_fields_missing"])
    )

    print("MISSING_EVIDENCE:")

    for item in result["incident_fields_missing"]:
        print("-", item["field"])

    print(
        "CURRENT_FLOODING:",
        result["current_flooding_status"]
    )

    print(
        "RESCUE_PRIORITY:",
        result["rescue_priority"]
    )

    print(
        "HUMAN_REVIEW_REQUIRED:",
        result["human_review_required"]
    )

    print(
        "AUTOMATED_DISPATCH:",
        result["automated_dispatch_authorized"]
    )

    print("===== AI_NETRA_RESULTS_END =====")


if __name__ == "__main__":
    main()
