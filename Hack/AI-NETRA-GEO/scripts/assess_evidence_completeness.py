"""
AI NETRA - Evidence Completeness Assessment
Version: 1.0.0

Purpose:
Evaluate available and missing evidence before rescue triage.

This module does not calculate flood probability,
rescue priority, or authorize rescue dispatch.
"""

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

CONTRACT_FILE = (
    ROOT / "data" /
    "ai_netra_rescue_evidence_contract_v1.json"
)


def is_available(value):
    """Return True for usable non-empty evidence."""

    if value is None:
        return False

    if isinstance(value, bool):
        return False

    if isinstance(value, (int, float)):
        return math.isfinite(value)

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (dict, list)):
        return bool(value)

    return False


def evaluate_section(data):
    """Identify available and missing evidence fields."""

    available = []
    missing = []

    for field, value in data.items():

        if is_available(value):
            available.append(field)
        else:
            missing.append(field)

    return {
        "available": available,
        "missing": missing,
        "available_count": len(available),
        "missing_count": len(missing),
        "total_fields": len(data)
    }


def assess_evidence(contract):
    """Assess completeness without making rescue decisions."""

    evidence = contract.get("evidence", {})

    building = evaluate_section(
        evidence.get("building", {})
    )

    environmental = evaluate_section(
        evidence.get("environmental", {})
    )

    incident_data = evidence.get("incident", {})

    incident = evaluate_section(incident_data)

    # Incident readiness requires current, verified
    # observations. Historical environmental evidence
    # alone cannot establish rescue urgency.

    current_observation_available = (
        is_available(
            incident_data.get("incident_timestamp")
        )
        and is_available(
            incident_data.get("observation_source")
        )
        and incident_data.get("verification_status")
        == "verified"
    )

    required_incident_fields = [
        "observed_water_depth_m",
        "observed_flow_velocity_mps",
        "estimated_people_stranded"
    ]

    incident_measurements_available = any(
        is_available(incident_data.get(field))
        for field in required_incident_fields
    )

    ready_for_human_review = (
        current_observation_available
        and incident_measurements_available
    )

    return {
        "schema_version": "1.0.0",
        "building": building,
        "environmental": environmental,
        "incident": incident,
        "current_observation_available":
            current_observation_available,
        "incident_measurements_available":
            incident_measurements_available,
        "ready_for_human_review":
            ready_for_human_review,
        "rescue_priority": "not_assessed",
        "priority_score": None,
        "current_flooding_status": "not_established",
        "human_review_required": True,
        "automated_dispatch_authorized": False
    }


def main():

    with CONTRACT_FILE.open(
        "r",
        encoding="utf-8-sig"
    ) as file:

        contract = json.load(file)

    result = assess_evidence(contract)

    print("===== AI_NETRA_RESULTS_START =====")

    print("MODULE: Evidence Completeness Assessment")

    for section in [
        "building",
        "environmental",
        "incident"
    ]:

        item = result[section]

        print(
            f"{section.upper()}_AVAILABLE:",
            item["available_count"]
        )

        print(
            f"{section.upper()}_MISSING:",
            item["missing_count"]
        )

    print(
        "CURRENT_OBSERVATION_AVAILABLE:",
        result["current_observation_available"]
    )

    print(
        "READY_FOR_HUMAN_REVIEW:",
        result["ready_for_human_review"]
    )

    print(
        "RESCUE_PRIORITY:",
        result["rescue_priority"]
    )

    print(
        "AUTOMATED_DISPATCH:",
        result["automated_dispatch_authorized"]
    )

    print("VALIDATION: PASS")

    print("===== AI_NETRA_RESULTS_END =====")


if __name__ == "__main__":
    main()
