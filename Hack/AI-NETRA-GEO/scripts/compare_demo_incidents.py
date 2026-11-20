"""
AI NETRA — Multi-Incident Comparison
Version: 1.0.0
Step: 9.13.27

Compares synthetic emergency reports using the
existing incident-triage module.

No operational rescue ranking, validated risk score,
or automated dispatch.
"""

import json
from copy import deepcopy
from pathlib import Path

from scripts.assess_demo_incident import assess_demo_incident


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

SOURCE_FILE = DATA_DIR / "ai_netra_demo_incident_001.json"

OUTPUT_FILE = (
    DATA_DIR / "ai_netra_multi_incident_comparison_v1.json"
)


def create_scenarios(base):

    scenarios = []

    configurations = [
        {
            "scenario_id": "AI_NETRA_DEMO_001",
            "estimated_people_stranded": 5,
            "children": 2,
            "senior_citizens": 1,
            "observed_water_depth_m": 1.5,
            "observed_flow_velocity_mps": 0.8,
        },
        {
            "scenario_id": "AI_NETRA_DEMO_002",
            "estimated_people_stranded": 12,
            "children": 4,
            "senior_citizens": 3,
            "observed_water_depth_m": 0.8,
            "observed_flow_velocity_mps": 0.3,
        },
        {
            "scenario_id": "AI_NETRA_DEMO_003",
            "estimated_people_stranded": 2,
            "children": 0,
            "senior_citizens": 1,
            "observed_water_depth_m": 2.2,
            "observed_flow_velocity_mps": 1.1,
        },
    ]

    for config in configurations:

        scenario = deepcopy(base)

        scenario["scenario_id"] = config["scenario_id"]
        scenario["scenario_type"] = "synthetic_training_scenario"

        # Do not claim these are actual reported incidents.
        scenario["incident"].update({
            key: value
            for key, value in config.items()
            if key != "scenario_id"
        })

        scenario["incident"]["observation_source"] = (
            "synthetic_emergency_report"
        )

        scenario["incident"]["verification_status"] = "unverified"

        scenarios.append(scenario)

    return scenarios


def compare_incidents(scenarios):

    results = []

    for scenario in scenarios:

        assessment = assess_demo_incident(scenario)

        incident = scenario["incident"]

        results.append({
            "scenario_id": scenario["scenario_id"],
            "building_id": scenario["building_id"],
            "synthetic": True,

            "reported_people": incident[
                "estimated_people_stranded"
            ],
            "reported_children": incident["children"],
            "reported_seniors": incident["senior_citizens"],

            "reported_water_depth_m": incident[
                "observed_water_depth_m"
            ],
            "reported_flow_velocity_mps": incident[
                "observed_flow_velocity_mps"
            ],

            "indicator_count": assessment["indicator_count"],

            "triage_status": assessment["triage"]["status"],

            "human_attention_flag": assessment[
                "triage"
            ]["human_attention_flag"],

            "verification_status": assessment[
                "verification_status"
            ],

            "rescue_priority": "not_assessed",
            "priority_score": None,
            "automated_dispatch_authorized": False,

            "explanation": assessment[
                "triage"
            ]["explanation"],
        })

    return {
        "project": "AI NETRA",
        "schema_version": "1.0.0",

        "assessment_type": (
            "synthetic_multi_incident_comparison"
        ),

        "scenario_count": len(results),

        "comparison_mode": "descriptive_only",

        "ranking_performed": False,

        "incidents": results,

        "human_review_required": True,

        "automated_dispatch_authorized": False,

        "limitations": [
            "All scenarios are fictional",
            "No independently verified incident measurements",
            "No operational rescue-priority ranking",
            "Reported values are not validated hazard estimates",
            "Human emergency decisions are outside this prototype",
        ],
    }


def main():

    with SOURCE_FILE.open(
        "r",
        encoding="utf-8-sig"
    ) as file:
        base = json.load(file)

    if base.get("scenario_type") != "synthetic_training_scenario":
        raise ValueError("Source scenario must be synthetic")

    scenarios = create_scenarios(base)

    result = compare_incidents(scenarios)

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(result, file, indent=2)

    with OUTPUT_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:
        saved = json.load(file)

    incidents = saved["incidents"]

    valid = (
        saved["scenario_count"] == 3
        and saved["comparison_mode"] == "descriptive_only"
        and saved["ranking_performed"] is False
        and all(
            item["synthetic"] is True
            and item["verification_status"] == "unverified"
            and item["rescue_priority"] == "not_assessed"
            and item["priority_score"] is None
            and item["automated_dispatch_authorized"] is False
            for item in incidents
        )
    )

    print("===== AI_NETRA_RESULTS_START =====")

    print("SCENARIOS:", saved["scenario_count"])

    for item in incidents:

        print(
            "INCIDENT:",
            item["scenario_id"],
            "| PEOPLE:", item["reported_people"],
            "| DEPTH:", item["reported_water_depth_m"],
            "| VELOCITY:", item["reported_flow_velocity_mps"],
            "| TRIAGE:", item["triage_status"]
        )

    print(
        "HUMAN_ATTENTION_CASES:",
        sum(
            1 for item in incidents
            if item["human_attention_flag"]
        )
    )

    print("RANKING_PERFORMED:", saved["ranking_performed"])

    print(
        "AUTOMATED_DISPATCH:",
        saved["automated_dispatch_authorized"]
    )

    print("OUTPUT_FILE:", OUTPUT_FILE.name)

    print("VALIDATION:", "PASS" if valid else "FAIL")

    print("===== AI_NETRA_RESULTS_END =====")

    if not valid:
        raise RuntimeError("Multi-incident validation failed")


if __name__ == "__main__":
    main()
