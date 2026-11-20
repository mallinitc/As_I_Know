"""
AI NETRA — Explainable Incident Comparison
Version: 1.0.0
Step: 9.13.28

Compares synthetic incident reports factor by factor.

This module does not:
- Rank incidents by rescue urgency
- Calculate flood probability
- Assign operational rescue priorities
- Authorize automated dispatch
"""

import json
import math
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    ROOT / "data" /
    "ai_netra_multi_incident_comparison_v1.json"
)

OUTPUT_FILE = (
    ROOT / "data" /
    "ai_netra_explainable_comparison_v1.json"
)


FACTORS = {
    "reported_people": "People reportedly stranded",
    "reported_children": "Children reportedly present",
    "reported_seniors": "Senior citizens reportedly present",
    "reported_water_depth_m": "Reported water depth",
    "reported_flow_velocity_mps": "Reported flow velocity"
}


def compare_pair(first, second):

    comparisons = []

    for field, description in FACTORS.items():

        value_a = first.get(field)
        value_b = second.get(field)

        valid_a = (
            isinstance(value_a, (int, float))
            and not isinstance(value_a, bool)
            and math.isfinite(value_a)
            and value_a >= 0
        )

        valid_b = (
            isinstance(value_b, (int, float))
            and not isinstance(value_b, bool)
            and math.isfinite(value_b)
            and value_b >= 0
        )

        if not valid_a or not valid_b:
            higher = None
            relationship = "insufficient_data"

        elif value_a > value_b:
            higher = first["scenario_id"]
            relationship = "first_higher"

        elif value_b > value_a:
            higher = second["scenario_id"]
            relationship = "second_higher"

        else:
            higher = None
            relationship = "equal"

        comparisons.append({
            "factor": field,
            "description": description,
            "first_value": value_a,
            "second_value": value_b,
            "relationship": relationship,
            "higher_reported_value_scenario": higher,
            "interpretation": (
                "Descriptive comparison of fictional reports. "
                "A higher value does not independently establish "
                "greater rescue urgency."
            )
        })

    first_higher = sum(
        item["relationship"] == "first_higher"
        for item in comparisons
    )

    second_higher = sum(
        item["relationship"] == "second_higher"
        for item in comparisons
    )

    return {
        "first_scenario": first["scenario_id"],
        "second_scenario": second["scenario_id"],
        "same_building_id": (
            first.get("building_id") ==
            second.get("building_id")
        ),
        "factor_comparisons": comparisons,
        "first_higher_factor_count": first_higher,
        "second_higher_factor_count": second_higher,
        "tradeoffs_present": (
            first_higher > 0 and second_higher > 0
        ),
        "rescue_priority_comparison": "not_determined",
        "operational_ranking_performed": False
    }


def main():

    with INPUT_FILE.open(
        "r", encoding="utf-8-sig"
    ) as file:
        source = json.load(file)

    incidents = source.get("incidents", [])

    if (
        source.get("assessment_type")
        != "synthetic_multi_incident_comparison"
        or len(incidents) < 2
        or any(
            item.get("synthetic") is not True
            or item.get("verification_status") != "unverified"
            for item in incidents
        )
    ):
        raise ValueError(
            "Expected at least two unverified synthetic incidents"
        )

    identifiers = [
        item["scenario_id"]
        for item in incidents
    ]

    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate scenario IDs")

    comparisons = [
        compare_pair(first, second)
        for first, second in combinations(incidents, 2)
    ]

    result = {
        "project": "AI NETRA",
        "schema_version": "1.0.0",
        "assessment_type": "synthetic_explainable_comparison",
        "scenario_count": len(incidents),
        "pairwise_comparison_count": len(comparisons),
        "comparison_method": "descriptive_factor_by_factor",
        "comparisons": comparisons,
        "ranking_performed": False,
        "priority_scores_assigned": False,
        "human_review_required": True,
        "automated_dispatch_authorized": False,
        "limitations": [
            "All incident values are fictional and unverified",
            "Scenarios may reference the same building",
            "Higher measurements do not independently establish rescue urgency",
            "No validated operational weighting or thresholds",
            "No automated rescue decisions"
        ]
    }

    with OUTPUT_FILE.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(result, file, indent=2)

    with OUTPUT_FILE.open(
        "r", encoding="utf-8"
    ) as file:
        saved = json.load(file)

    valid = (
        saved["scenario_count"] == 3
        and saved["pairwise_comparison_count"] == 3
        and saved["ranking_performed"] is False
        and saved["priority_scores_assigned"] is False
        and saved["automated_dispatch_authorized"] is False
        and all(
            comparison["rescue_priority_comparison"]
            == "not_determined"
            for comparison in saved["comparisons"]
        )
    )

    print("===== AI_NETRA_RESULTS_START =====")
    print("SCENARIOS:", saved["scenario_count"])
    print(
        "PAIRWISE_COMPARISONS:",
        saved["pairwise_comparison_count"]
    )

    for item in saved["comparisons"]:
        print(
            "PAIR:",
            item["first_scenario"],
            "vs",
            item["second_scenario"],
            "| FIRST_HIGHER:",
            item["first_higher_factor_count"],
            "| SECOND_HIGHER:",
            item["second_higher_factor_count"],
            "| TRADEOFFS:",
            item["tradeoffs_present"]
        )

    print(
        "SAME_BUILDING_PAIRS:",
        sum(
            item["same_building_id"]
            for item in saved["comparisons"]
        )
    )

    print(
        "RANKING_PERFORMED:",
        saved["ranking_performed"]
    )

    print(
        "AUTOMATED_DISPATCH:",
        saved["automated_dispatch_authorized"]
    )

    print("OUTPUT_FILE:", OUTPUT_FILE.name)
    print("VALIDATION:", "PASS" if valid else "FAIL")
    print("===== AI_NETRA_RESULTS_END =====")

    if not valid:
        raise RuntimeError("Comparison validation failed")


if __name__ == "__main__":
    main()
