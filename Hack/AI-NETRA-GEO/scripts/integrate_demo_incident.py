"""
AI NETRA — Integrated Incident Assessment
Version: 1.0.0
Step: 9.13.19

Combines existing building evidence with synthetic incident
triage while preserving provenance and safety boundaries.

No operational rescue priority or automated dispatch.
"""

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BUILDING_FILE = (
    ROOT / "data" / "ai_netra_unified_assessment_demo_v1.json"
)

SCENARIO_FILE = (
    ROOT / "data" / "ai_netra_demo_incident_001.json"
)

OUTPUT_FILE = (
    ROOT / "data" / "ai_netra_integrated_incident_001.json"
)

from scripts.assess_demo_incident import assess_demo_incident


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def main():

    building_assessment = load_json(BUILDING_FILE)
    scenario = load_json(SCENARIO_FILE)

    if scenario.get("scenario_type") != "synthetic_training_scenario":
        raise ValueError("Scenario must be explicitly synthetic")

    if (
        building_assessment.get("building_id")
        != scenario.get("building_id")
    ):
        raise ValueError("Building IDs do not match")

    triage_result = assess_demo_incident(scenario)

    integrated = deepcopy(building_assessment)

    integrated["assessment_type"] = (
        "synthetic_incident_evidence_assessment"
    )

    integrated["scenario"] = {
        "scenario_id": scenario["scenario_id"],
        "scenario_type": scenario["scenario_type"],
        "synthetic": True,
        "verification_status": scenario["incident"].get(
            "verification_status", "unavailable"
        ),
    }

    # Keep the original, actual incident-evidence section
    # unchanged. Synthetic values are stored separately.
    integrated["synthetic_incident"] = {
        "reported_values": scenario["incident"],
        "triage": triage_result["triage"],
        "reported_indicators": triage_result["reported_indicators"],
        "limitations": triage_result["limitations"],
    }

    integrated["assessment"] = {
        "current_flooding_status": "not_established",
        "incident_report_status": "synthetic_unverified",
        "human_attention_flag": triage_result["triage"][
            "human_attention_flag"
        ],
        "triage_status": triage_result["triage"]["status"],
        "rescue_priority": "not_assessed",
        "priority_score": None,
        "human_review_required": True,
        "automated_dispatch_authorized": False,
        "explanation": (
            "The synthetic scenario reports people requiring "
            "assistance and potential flood hazards. These "
            "values are fictional and unverified. The report "
            "demonstrates a human-review alert, not an "
            "operational rescue-priority decision."
        ),
    }

    integrated["disclaimer"] = (
        "SYNTHETIC DEMONSTRATION ONLY. No real emergency, "
        "confirmed flooding, verified measurements, or "
        "authorized rescue dispatch."
    )

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(integrated, file, indent=2)

    saved = load_json(OUTPUT_FILE)

    valid = (
        saved["building_id"] == "osm-way-357584220"
        and saved["scenario"]["synthetic"] is True
        and saved["assessment"]["human_attention_flag"] is True
        and saved["assessment"]["triage_status"]
        == "reported_urgent_review"
        and saved["assessment"]["rescue_priority"]
        == "not_assessed"
        and saved["assessment"]["priority_score"] is None
        and saved["assessment"][
            "automated_dispatch_authorized"
        ] is False
        and saved["incident_evidence"].get(
            "estimated_people_stranded"
        ) is None
        and len(
            saved["synthetic_incident"]["reported_indicators"]
        ) == 5
    )

    print("===== AI_NETRA_RESULTS_START =====")
    print("BUILDING_ID:", saved["building_id"])
    print("SCENARIO:", saved["scenario"]["scenario_id"])
    print("SYNTHETIC:", saved["scenario"]["synthetic"])
    print(
        "BUILDING_EVIDENCE:",
        saved["evidence_completeness"]["building"][
            "available_count"
        ]
    )
    print(
        "ENVIRONMENTAL_EVIDENCE:",
        saved["evidence_completeness"]["environmental"][
            "available_count"
        ]
    )
    print(
        "INCIDENT_INDICATORS:",
        len(saved["synthetic_incident"]["reported_indicators"])
    )
    print(
        "TRIAGE_STATUS:",
        saved["assessment"]["triage_status"]
    )
    print(
        "HUMAN_ATTENTION:",
        saved["assessment"]["human_attention_flag"]
    )
    print(
        "RESCUE_PRIORITY:",
        saved["assessment"]["rescue_priority"]
    )
    print(
        "AUTOMATED_DISPATCH:",
        saved["assessment"]["automated_dispatch_authorized"]
    )
    print("OUTPUT_FILE:", OUTPUT_FILE.name)
    print("VALIDATION:", "PASS" if valid else "FAIL")
    print("===== AI_NETRA_RESULTS_END =====")

    if not valid:
        raise RuntimeError("Integrated assessment validation failed")


if __name__ == "__main__":
    main()
