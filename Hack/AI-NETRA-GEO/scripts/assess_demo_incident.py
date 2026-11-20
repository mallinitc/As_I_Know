"""
AI NETRA — Synthetic Incident Triage
Version: 1.0.0
Step: 9.13.18

Purpose:
Identify potential emergency indicators in a synthetic
incident report and explain why human review is required.

This is NOT an operational rescue-priority model.
"""

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

SCENARIO_FILE = (
    ROOT / "data" / "ai_netra_demo_incident_001.json"
)

OUTPUT_FILE = (
    ROOT / "data" / "ai_netra_demo_triage_001.json"
)


def nonnegative_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def assess_demo_incident(scenario):

    if scenario.get("scenario_type") != "synthetic_training_scenario":
        raise ValueError("Only synthetic training scenarios are supported")

    incident = scenario.get("incident", {})

    people = incident.get("estimated_people_stranded")
    children = incident.get("children")
    seniors = incident.get("senior_citizens")
    depth = incident.get("observed_water_depth_m")
    velocity = incident.get("observed_flow_velocity_mps")

    numeric_fields = {
        "estimated_people_stranded": people,
        "children": children,
        "senior_citizens": seniors,
        "observed_water_depth_m": depth,
        "observed_flow_velocity_mps": velocity,
    }

    for field, value in numeric_fields.items():
        if value is not None and not nonnegative_number(value):
            raise ValueError(f"Invalid nonnegative value: {field}")

    for field in [
        "estimated_people_stranded",
        "children",
        "senior_citizens",
    ]:
        value = incident.get(field)

        if value is not None and not float(value).is_integer():
            raise ValueError(f"Expected whole-number count: {field}")

    if people is not None:
        if children is not None and children > people:
            raise ValueError("Children count exceeds reported people")

        if seniors is not None and seniors > people:
            raise ValueError("Senior count exceeds reported people")

    indicators = []

    if people is not None and people > 0:
        indicators.append({
            "indicator": "people_reportedly_stranded",
            "value": people,
            "explanation": (
                "The synthetic report indicates people may "
                "require emergency assistance."
            ),
        })

    if children is not None and children > 0:
        indicators.append({
            "indicator": "children_reportedly_present",
            "value": children,
            "explanation": (
                "Children are reportedly among those requiring "
                "assistance. Their needs require human assessment."
            ),
        })

    if seniors is not None and seniors > 0:
        indicators.append({
            "indicator": "senior_citizens_reportedly_present",
            "value": seniors,
            "explanation": (
                "Senior citizens are reportedly present. "
                "Mobility and support needs require assessment."
            ),
        })

    if depth is not None and depth > 0:
        indicators.append({
            "indicator": "reported_water_depth",
            "value": depth,
            "unit": "m",
            "explanation": (
                "The synthetic report includes a positive water "
                "depth. This is not a verified measurement."
            ),
        })

    if velocity is not None and velocity > 0:
        indicators.append({
            "indicator": "reported_flow_velocity",
            "value": velocity,
            "unit": "m/s",
            "explanation": (
                "The synthetic report includes water movement. "
                "The measurement has not been verified."
            ),
        })

    verification = incident.get(
        "verification_status", "unavailable"
    )

    attention_required = (
        people is not None and people > 0
    )

    return {
        "scenario_id": scenario.get("scenario_id"),
        "scenario_type": "synthetic_training_scenario",
        "building_id": scenario.get("building_id"),

        "reported_indicators": indicators,
        "indicator_count": len(indicators),

        "observation_source": incident.get(
            "observation_source"
        ),

        "verification_status": verification,

        "triage": {
            "status": (
                "reported_urgent_review"
                if attention_required
                else "requires_manual_assessment"
            ),
            "human_attention_flag": attention_required,
            "human_review_required": True,

            "rescue_priority": "not_assessed",
            "priority_score": None,

            "current_flooding_confirmed": False,
            "automated_dispatch_authorized": False,

            "explanation": (
                "Synthetic emergency information suggests "
                "potential assistance needs. The report is "
                "unverified and must be assessed by a human. "
                "No operational rescue priority is assigned."
            ),
        },

        "limitations": [
            "Synthetic demonstration only",
            "No verified current flood observations",
            "No validated rescue-priority thresholds",
            "No automated dispatch authorization",
        ],
    }


def main():

    with SCENARIO_FILE.open(
        "r", encoding="utf-8-sig"
    ) as file:
        scenario = json.load(file)

    result = assess_demo_incident(scenario)

    with OUTPUT_FILE.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(result, file, indent=2)

    triage = result["triage"]

    valid = (
        result["scenario_id"] == "AI_NETRA_DEMO_001"
        and result["indicator_count"] == 5
        and triage["status"] == "reported_urgent_review"
        and triage["human_review_required"] is True
        and triage["rescue_priority"] == "not_assessed"
        and triage["priority_score"] is None
        and triage["automated_dispatch_authorized"] is False
    )

    print("===== AI_NETRA_RESULTS_START =====")
    print("SCENARIO:", result["scenario_id"])
    print("INDICATORS_DETECTED:", result["indicator_count"])

    for item in result["reported_indicators"]:
        print("INDICATOR:", item["indicator"])

    print("TRIAGE_STATUS:", triage["status"])
    print("VERIFICATION:", result["verification_status"])
    print("HUMAN_REVIEW:", triage["human_review_required"])
    print("RESCUE_PRIORITY:", triage["rescue_priority"])
    print("AUTOMATED_DISPATCH:", triage["automated_dispatch_authorized"])
    print("OUTPUT_FILE:", OUTPUT_FILE.name)
    print("VALIDATION:", "PASS" if valid else "FAIL")
    print("===== AI_NETRA_RESULTS_END =====")

    if not valid:
        raise RuntimeError("Synthetic incident triage validation failed")


if __name__ == "__main__":
    main()
