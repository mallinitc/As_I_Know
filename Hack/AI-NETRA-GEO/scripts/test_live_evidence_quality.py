"""
AI NETRA - Live Evidence Quality Validation
Step: 9.13.8

Loads real building evidence from FastAPI and
classifies its provenance and verification status.

Does not assign flood probability or rescue priority.
"""

import json
import urllib.request
from collections import Counter
from pathlib import Path

from scripts.classify_evidence_quality import classify_evidence


ROOT = Path(__file__).resolve().parent.parent

CONTRACT_FILE = (
    ROOT / "data" /
    "ai_netra_rescue_evidence_contract_v1.json"
)

BUILDING_ID = "osm-way-357584220"

LAT = 17.37990065
LON = 78.51797466199042

URL = (
    "http://127.0.0.1:8000/building/query"
    f"?lat={LAT}&lon={LON}"
)


def main():

    with CONTRACT_FILE.open(
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
        raise RuntimeError("Building identification mismatch")

    attributes = building.get("attribute_evidence") or {}

    radar = attributes.get("sentinel1_historical_radar")

    if radar is None:
        radar = building.get("sentinel1_historical_radar")

    if not isinstance(radar, dict):
        radar = None

    elif radar.get("availability") != "available":
        radar = None

    # Populate building evidence.
    contract["evidence"]["building"].update({
        "building_id": BUILDING_ID,
        "latitude": LAT,
        "longitude": LON,
        "footprint_area_m2": building.get(
            "footprint_area_m2"
        ),
        "estimated_height_m": building.get(
            "estimated_height_m"
        )
    })

    # Populate environmental evidence.
    contract["evidence"]["environmental"].update({
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

    # Current incident evidence remains unavailable.
    result = classify_evidence(contract)

    records = result["records"]

    counts = Counter(
        record["classification"]
        for record in records
    )

    print("===== AI_NETRA_RESULTS_START =====")

    print("BUILDING_ID:", BUILDING_ID)
    print("TOTAL_EVIDENCE_FIELDS:", len(records))

    for category in [
        "geometry_derived",
        "model_estimated",
        "mapped_historical",
        "observed_historical",
        "verified_current",
        "unavailable"
    ]:
        print(
            category.upper() + ":",
            counts.get(category, 0)
        )

    print(
        "INDEPENDENTLY_VERIFIED_FIELDS:",
        sum(
            1 for record in records
            if record["independently_verified"]
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

    print("===== AI_NETRA_RESULTS_END =====")


if __name__ == "__main__":
    main()
