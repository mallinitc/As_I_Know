"""
AI NETRA — Expanded Earth Engine Point Preparation
Workstream: GEO-001
Version: 0.4.3

Purpose:
- Prepare 11,659 OSM building locations
- Preserve OSM building IDs
- Identify buildings already enriched with Google heights
- Generate an Earth Engine-ready CSV
- Preserve existing datasets

Dependencies:
- Python 3.11
- Shapely

No Pandas or GeoPandas required.
"""

import csv
import json
from pathlib import Path

from shapely.geometry import shape


# ============================================================
# 1. CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"

INPUT_FILE = (
    DATA_DIR
    / "moosarambagh_osm_buildings_expanded_v1.geojson"
)

EXISTING_HEIGHT_FILE = (
    DATA_DIR
    / "ai_netra_building_heights_2023_v1.csv"
)

OUTPUT_FILE = (
    DATA_DIR
    / "moosarambagh_expanded_building_points_v1.csv"
)

NEW_POINTS_FILE = (
    DATA_DIR
    / "moosarambagh_new_height_points_v1.csv"
)


# ============================================================
# 2. LOAD EXISTING GOOGLE HEIGHT RECORDS
# ============================================================

existing_height_ids = set()

if EXISTING_HEIGHT_FILE.exists():

    with open(
        EXISTING_HEIGHT_FILE,
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            building_id = row.get("building_id")

            raw_height = row.get("estimated_height_m")

            if building_id and raw_height:

                existing_height_ids.add(
                    building_id
                )

print(
    f"Existing height records: "
    f"{len(existing_height_ids)}"
)


# ============================================================
# 3. LOAD EXPANDED OSM DATASET
# ============================================================

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8"
) as file:

    dataset = json.load(file)

features = dataset.get("features", [])

print(f"Expanded OSM buildings: {len(features)}")


# ============================================================
# 4. GENERATE REPRESENTATIVE POINTS
# ============================================================

all_records = []

new_records = []

for feature in features:

    properties = feature.get("properties", {})

    building_id = properties.get("building_id")

    if not building_id:
        continue

    polygon = shape(feature["geometry"])

    if polygon.is_empty or not polygon.is_valid:
        continue

    point = polygon.representative_point()

    record = {
        "building_id": building_id,
        "longitude": point.x,
        "latitude": point.y
    }

    all_records.append(record)

    if building_id not in existing_height_ids:

        new_records.append(record)


# ============================================================
# 5. EXPORT CSV FILES
# ============================================================

fieldnames = [
    "building_id",
    "longitude",
    "latitude"
]


def write_csv(path, records):

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(records)


write_csv(
    OUTPUT_FILE,
    all_records
)

write_csv(
    NEW_POINTS_FILE,
    new_records
)


# ============================================================
# 6. VALIDATION SUMMARY
# ============================================================

print("\nAI NETRA — EXPANDED HEIGHT PREPARATION")
print("=" * 55)

print(
    f"Total expanded buildings: "
    f"{len(all_records)}"
)

print(
    f"Existing Google height IDs: "
    f"{len(existing_height_ids)}"
)

print(
    f"Buildings requiring height lookup: "
    f"{len(new_records)}"
)

print("\nFILES CREATED")
print("-" * 55)

print(f"All building points:\n{OUTPUT_FILE}")

print(f"\nNew height lookup points:\n{NEW_POINTS_FILE}")

print("\nOriginal datasets preserved.")

print("\nPREPARATION COMPLETED")