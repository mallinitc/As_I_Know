"""
AI NETRA — Building Height Dataset Merger
Workstream: GEO-001
Version: 0.4.4

Combines original and expanded Google Open Buildings 2.5D
height estimates while preserving provenance.

Dependencies: Python 3.11 standard library
"""

import csv
import json
import math
import statistics
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

INPUT_FILES = [
    DATA / "ai_netra_building_heights_2023_v1.csv",
    DATA / "ai_netra_expanded_heights_2023_v1.csv",
]

OSM_FILE = DATA / "moosarambagh_osm_buildings_expanded_v1.geojson"

OUTPUT_FILE = DATA / "ai_netra_merged_heights_2023_v1.csv"

REPORT_FILE = DATA / "height_merge_validation_v1.json"

# Screening threshold, not a verified minimum building height.
LOW_HEIGHT_THRESHOLD_M = 2.0

with open(OSM_FILE, encoding="utf-8") as f:
    osm = json.load(f)

expected_ids = {
    feature["properties"]["building_id"]
    for feature in osm["features"]
}

records = {}
duplicate_ids = []
invalid_values = []
unexpected_ids = []

for input_file in INPUT_FILES:

    with open(
        input_file,
        newline="",
        encoding="utf-8-sig"
    ) as f:

        reader = csv.DictReader(f)

        required = {"building_id", "estimated_height_m"}

        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                f"Missing required columns in {input_file.name}"
            )

        for row in reader:

            building_id = (row.get("building_id") or "").strip()
            raw_height = (row.get("estimated_height_m") or "").strip()

            if not building_id:
                invalid_values.append({
                    "building_id": None,
                    "reason": "missing_building_id"
                })
                continue

            if building_id not in expected_ids:
                unexpected_ids.append(building_id)
                continue

            if building_id in records:
                duplicate_ids.append(building_id)
                continue

            try:
                height = float(raw_height)

                if not math.isfinite(height) or height <= 0:
                    raise ValueError("Non-positive or non-finite height")

                valid_height = True

            except (ValueError, TypeError):
                height = None
                valid_height = False

                invalid_values.append({
                    "building_id": building_id,
                    "reason": "invalid_height",
                    "raw_value": raw_height
                })

            records[building_id] = {
                "building_id": building_id,
                "estimated_height_m": height,
                "height_source": "Google Open Buildings 2.5D",
                "dataset_year": 2023,
                "measurement_type": "model_estimate",
                "sampling_method": "representative_point",
                "verification_status": "not_field_verified",
                "height_quality_flag": (
                    "missing_or_invalid"
                    if not valid_height
                    else "review_low_estimate"
                    if height < LOW_HEIGHT_THRESHOLD_M
                    else "unverified_estimate"
                ),
            }

missing_ids = expected_ids - set(records)

heights = [
    row["estimated_height_m"]
    for row in records.values()
    if row["estimated_height_m"] is not None
]

low_height_count = sum(
    h < LOW_HEIGHT_THRESHOLD_M for h in heights
)

fieldnames = [
    "building_id",
    "estimated_height_m",
    "height_source",
    "dataset_year",
    "measurement_type",
    "sampling_method",
    "verification_status",
    "height_quality_flag",
]

with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as f:

    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()

    for building_id in sorted(records):
        writer.writerow(records[building_id])

report = {
    "project": "AI NETRA",
    "report_version": "1.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "expected_osm_buildings": len(expected_ids),
    "merged_records": len(records),
    "numeric_height_records": len(heights),
    "missing_building_ids": len(missing_ids),
    "duplicate_ids": len(duplicate_ids),
    "unexpected_ids": len(unexpected_ids),
    "invalid_height_values": len(invalid_values),
    "low_height_threshold_m": LOW_HEIGHT_THRESHOLD_M,
    "low_estimates_flagged": low_height_count,
    "minimum_height_m": min(heights) if heights else None,
    "maximum_height_m": max(heights) if heights else None,
    "mean_height_m": statistics.mean(heights) if heights else None,
    "median_height_m": statistics.median(heights) if heights else None,
    "dataset_year": 2023,
    "source": "Google Open Buildings 2.5D",
    "limitations": [
        "Heights are satellite-derived model estimates",
        "Representative-point sampling does not validate whole-building height",
        "Low estimates are flagged for review, not declared incorrect",
        "No independent ground-truth accuracy assessment performed"
    ]
}

REPORT_FILE.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print("\nAI NETRA — HEIGHT DATASET MERGE VALIDATION")
print("=" * 55)

print(f"Expected OSM buildings: {len(expected_ids)}")
print(f"Merged building records: {len(records)}")
print(f"Valid numeric heights: {len(heights)}")
print(f"Missing building IDs: {len(missing_ids)}")
print(f"Duplicate IDs: {len(duplicate_ids)}")
print(f"Unexpected IDs: {len(unexpected_ids)}")
print(f"Invalid heights: {len(invalid_values)}")
print(f"Low estimates (<2 m): {low_height_count}")

if heights:
    print(f"Minimum height: {min(heights):.2f} m")
    print(f"Maximum height: {max(heights):.2f} m")
    print(f"Mean height: {statistics.mean(heights):.2f} m")
    print(f"Median height: {statistics.median(heights):.2f} m")

print(f"\nMerged CSV: {OUTPUT_FILE}")
print(f"Validation report: {REPORT_FILE}")
print("\nOriginal datasets preserved.")