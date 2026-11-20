"""
AI NETRA — Unified Rescue Assessment
Version: 1.0.0
Step: 9.13.10

Combines:
1. Building Intelligence
2. Evidence Completeness
3. Evidence Quality
4. Rescue Readiness

No flood probability or automated rescue priority is assigned.
"""

import json
import urllib.request
from collections import Counter
from copy import deepcopy
from pathlib import Path

from scripts.assess_evidence_completeness import assess_evidence
from scripts.classify_evidence_quality import classify_evidence
from scripts.assess_rescue_readiness import assess_readiness


ROOT = Path(__file__).resolve().parent.parent

CONTRACT_FILE = (
    ROOT / "data" /
    "ai_netra_rescue_evidence_contract_v1.json"
)

OUTPUT_FILE = (
    ROOT / "data" /
    "ai_netra_unified_assessment_demo_v1.json"
)

BUILDING_ID = "osm-way-357584220"

LAT = 17.37990065
LON = 78.51797466199042

API_URL = (
    "http://127.0.0.1:8000/building/query"
    f"?lat={LAT}&lon={LON}"
)


def main():

    # Load original contract without modifying it.
    with CONTRACT_FILE.open(
        "r", encoding="utf-8-sig"
    ) as file:
        template = json.load(file)

    contract = deepcopy(template)

    # Retrieve actual building intelligence.
    with urllib.request.urlopen(
        API_URL, timeout=20
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

    if (
        not isinstance(radar, dict)
        or radar.get("availability") != "available"
    ):
        radar = None

    # Populate actual building evidence.
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

    # Populate actual environmental evidence.
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

    # Run all three assessment modules.
    completeness = assess_evidence(contract)

    quality = classify_evidence(contract)

    readiness = assess_readiness(contract)

    quality_counts = dict(
        Counter(
            record["classification"]
            for record in quality["records"]
        )
    )

    # Construct unified response.
    unified = {
        "project": "AI NETRA",
        "schema_version": "1.0.0",
        "assessment_type": "experimental_evidence_assessment",

        "building_id": BUILDING_ID,

        "building_evidence": contract["evidence"]["building"],

        "environmental_evidence": contract["evidence"]["environmental"],

        "incident_evidence": contract["evidence"]["incident"],

        "evidence_completeness": completeness,

        "evidence_quality": {
            "classifications": quality_counts,
            "records": quality["records"]
        },

        "rescue_readiness": readiness,

        "assessment": {
            "current_flooding_status": "not_established",
            "rescue_priority": "not_assessed",
            "priority_score": None,
            "human_review_required": True,
            "automated_dispatch_authorized": False,

            "explanation": (
                "Historical geographic and satellite evidence "
                "is available, but verified current incident "
                "observations are missing. Rescue urgency "
                "cannot be established from these data alone."
            )
        }
    }

    # Save assessment for future frontend integration.
    with OUTPUT_FILE.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(unified, file, indent=2)

    # Validate saved output.
    with OUTPUT_FILE.open(
        "r", encoding="utf-8"
    ) as file:
        saved = json.load(file)

    valid = (
        saved["building_id"] == BUILDING_ID
        and saved["assessment"]["rescue_priority"] == "not_assessed"
        and saved["assessment"]["automated_dispatch_authorized"] is False
        and saved["assessment"]["human_review_required"] is True
    )

    print("===== AI_NETRA_RESULTS_START =====")

    print("BUILDING_ID:", BUILDING_ID)

    print(
        "BUILDING_EVIDENCE_AVAILABLE:",
        completeness["building"]["available_count"]
    )

    print(
        "ENVIRONMENTAL_EVIDENCE_AVAILABLE:",
        completeness["environmental"]["available_count"]
    )

    print(
        "SATELLITE_EVIDENCE_AVAILABLE:",
        radar is not None
    )

    print(
        "VERIFIED_CURRENT_EVIDENCE:",
        quality_counts.get("verified_current", 0)
    )

    print(
        "MISSING_INCIDENT_FIELDS:",
        len(readiness["incident_fields_missing"])
    )

    print(
        "RESCUE_PRIORITY:",
        saved["assessment"]["rescue_priority"]
    )

    print(
        "HUMAN_REVIEW_REQUIRED:",
        saved["assessment"]["human_review_required"]
    )

    print(
        "OUTPUT_FILE:",
        OUTPUT_FILE.name
    )

    print("VALIDATION:", "PASS" if valid else "FAIL")

    print("===== AI_NETRA_RESULTS_END =====")

    if not valid:
        raise RuntimeError("Unified assessment validation failed")


if __name__ == "__main__":
    main()
