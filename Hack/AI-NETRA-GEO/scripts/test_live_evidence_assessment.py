"""
AI NETRA — Step 9.13.6
Real Building Evidence Completeness Test

Reads actual FastAPI building evidence.
Does not assign flood probability or rescue priority.
Does not modify the existing evidence contract.
"""

import json
import urllib.request
from pathlib import Path

from scripts.assess_evidence_completeness import assess_evidence


ROOT = Path(__file__).resolve().parent.parent

CONTRACT = (
    ROOT / "data" /
    "ai_netra_rescue_evidence_contract_v1.json"
)

BUILDING_ID = "osm-way-357584220"

LATITUDE = 17.37990065
LONGITUDE = 78.51797466199042

URL = (
    "http://127.0.0.1:8000/building/query"
    f"?lat={LATITUDE}&lon={LONGITUDE}"
)


def main():

    with CONTRACT.open(
        "r",
        encoding="utf-8-sig"
    ) as file:
        contract = json.load(file)

    with urllib.request.urlopen(
        URL,
        timeout=20
    ) as response:
        building = json.load(response)

    if (
        building.get("match_type") != "exact"
        or building.get("building_id") != BUILDING_ID
    ):
        raise RuntimeError(
            "Expected exact building match was not returned."
        )

    attributes = building.get("attribute_evidence") or {}

    radar = attributes.get(
        "sentinel1_historical_radar"
    )

    if not isinstance(radar, dict):
        radar = building.get("sentinel1_historical_radar")

    if not isinstance(radar, dict):
        radar = {}

    if radar.get("availability") != "available":
        radar = None

    evidence = contract["evidence"]

    # Building information.
    evidence["building"].update({
        "building_id": building.get("building_id"),
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "footprint_area_m2": building.get(
            "footprint_area_m2"
        ),
        "estimated_height_m": building.get(
            "estimated_height_m"
        )
    })

    # Environmental information.
    evidence["environmental"].update({
        "distance_to_musi_water_m": building.get(
            "distance_to_musi_water_m"
        ),
        "distance_to_waterlogging_point_m": building.get(
            "distance_to_waterlogging_point_m"
        ),
        "historical_evidence_category": building.get(
            "historical_evidence_category"
        ),
        "sentinel1_historical_radar": radar
    })

    # Incident evidence remains unchanged and unavailable.
    # Historical observations cannot establish a current incident.

    result = assess_evidence(contract)

    print("===== AI_NETRA_RESULTS_START =====")

    print("BUILDING_ID:", BUILDING_ID)

    print(
        "BUILDING_AVAILABLE:",
        result["building"]["available_count"]
    )

    print(
        "BUILDING_MISSING:",
        result["building"]["missing_count"]
    )

    print(
        "ENVIRONMENTAL_AVAILABLE:",
        result["environmental"]["available_count"]
    )

    print(
        "ENVIRONMENTAL_MISSING:",
        result["environmental"]["missing_count"]
    )

    print(
        "SENTINEL1_AVAILABLE:",
        radar is not None
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

    print("===== AI_NETRA_RESULTS_END =====")


if __name__ == "__main__":
    main()
