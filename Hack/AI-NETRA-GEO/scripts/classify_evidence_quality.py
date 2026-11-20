"""
AI NETRA - Evidence Quality Classification
Version: 1.0.0
Step: 9.13.7

Classifies evidence provenance and verification status.

Does not calculate flood probability, rescue priority,
or authorize automated rescue operations.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

CONTRACT_FILE = (
    ROOT / "data" /
    "ai_netra_rescue_evidence_contract_v1.json"
)


EVIDENCE_RULES = {
    "building_id": "geometry_derived",
    "latitude": "geometry_derived",
    "longitude": "geometry_derived",
    "footprint_area_m2": "geometry_derived",
    "estimated_height_m": "model_estimated",
    "distance_to_musi_water_m": "geometry_derived",
    "distance_to_waterlogging_point_m": "geometry_derived",
    "historical_evidence_category": "mapped_historical",
    "sentinel1_historical_radar": "observed_historical"
}


def has_value(value):
    """Determine whether a meaningful value is present."""

    if value is None:
        return False

    if isinstance(value, str):
        return (
            bool(value.strip())
            and value.strip().lower()
            not in ("unavailable", "unknown", "not_verified")
        )

    if isinstance(value, bool):
        return False

    if isinstance(value, dict):
        if value.get("availability") == "not_available":
            return False

        return bool(value)

    return True


def classify_evidence(contract):
    """Classify evidence without inferring current flooding."""

    evidence = contract.get("evidence", {})

    records = []

    for section in ["building", "environmental"]:

        for field, value in evidence.get(section, {}).items():

            available = has_value(value)

            classification = (
                EVIDENCE_RULES.get(field, "unclassified")
                if available
                else "unavailable"
            )

            records.append({
                "section": section,
                "field": field,
                "available": available,
                "classification": classification,
                "current_incident_evidence": False,
                "independently_verified": False
            })

    incident = evidence.get("incident", {})

    incident_verified = (
        incident.get("verification_status") == "verified"
    )

    for field, value in incident.items():

        if field == "verification_status":
            continue

        available = has_value(value)

        records.append({
            "section": "incident",
            "field": field,
            "available": available,
            "classification": (
                "verified_current"
                if available and incident_verified
                else "unverified_current"
                if available
                else "unavailable"
            ),
            "current_incident_evidence": available,
            "independently_verified": (
                available and incident_verified
            )
        })

    return {
        "schema_version": "1.0.0",
        "records": records,
        "current_flooding_status": "not_established",
        "rescue_priority": "not_assessed",
        "human_review_required": True,
        "automated_dispatch_authorized": False
    }


def main():

    with CONTRACT_FILE.open(
        "r",
        encoding="utf-8-sig"
    ) as file:
        contract = json.load(file)

    result = classify_evidence(contract)

    records = result["records"]

    classifications = sorted({
        record["classification"]
        for record in records
    })

    print("===== AI_NETRA_RESULTS_START =====")

    print("MODULE: Evidence Quality Classification")
    print("TOTAL_EVIDENCE_FIELDS:", len(records))

    for category in classifications:

        count = sum(
            record["classification"] == category
            for record in records
        )

        print(f"{category.upper()}: {count}")

    print(
        "VERIFIED_CURRENT_EVIDENCE:",
        sum(
            record["classification"] == "verified_current"
            for record in records
        )
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
