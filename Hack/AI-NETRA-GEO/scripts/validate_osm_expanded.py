"""
AI NETRA — Expanded OSM Dataset Validation
Workstream: GEO-001
Version: 0.4.2

Validates:
- Building count
- Unique identifiers
- Geometry validity
- Missing attributes
- Building classification
- Geographic coverage

Dependencies:
- Python 3.11
- Shapely

No Pandas or GeoPandas required.
"""

import json
from collections import Counter
from pathlib import Path

from shapely.geometry import shape


# ============================================================
# 1. CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = (
    PROJECT_ROOT
    / "data"
    / "moosarambagh_osm_buildings_expanded_v1.geojson"
)


# ============================================================
# 2. LOAD DATASET
# ============================================================

with open(DATA_FILE, "r", encoding="utf-8") as file:
    dataset = json.load(file)

features = dataset.get("features", [])
metadata = dataset.get("metadata", {})

print("\nAI NETRA — EXPANDED DATASET VALIDATION")
print("=" * 55)

print(f"Total building records: {len(features)}")
print(f"Dataset complete: {metadata.get('is_complete')}")
print(f"Bounding box: {metadata.get('bbox')}")


# ============================================================
# 3. VALIDATION COUNTERS
# ============================================================

valid_geometries = 0
invalid_geometries = 0
empty_geometries = 0

building_ids = set()
duplicate_ids = []

with_levels = 0
with_height = 0
with_construction_date = 0

building_types = Counter()

invalid_samples = []


# ============================================================
# 4. VALIDATE EACH BUILDING
# ============================================================

for feature in features:

    properties = feature.get("properties", {})

    building_id = properties.get("building_id")

    # Check duplicate IDs.
    if building_id in building_ids:
        duplicate_ids.append(building_id)

    building_ids.add(building_id)

    # Validate geometry.
    try:
        geometry = shape(feature["geometry"])

        if geometry.is_empty:
            empty_geometries += 1

        elif not geometry.is_valid:
            invalid_geometries += 1

            if len(invalid_samples) < 10:
                invalid_samples.append(building_id)

        else:
            valid_geometries += 1

    except Exception:
        invalid_geometries += 1

        if len(invalid_samples) < 10:
            invalid_samples.append(building_id)

    # Check available attributes.
    if properties.get("building_levels"):
        with_levels += 1

    if properties.get("height"):
        with_height += 1

    if properties.get("construction_date"):
        with_construction_date += 1

    building_types[
        properties.get("building_type") or "unknown"
    ] += 1


# ============================================================
# 5. REPORT
# ============================================================

total = len(features)


def percentage(value):
    return (
        round(value / total * 100, 2)
        if total
        else 0
    )


print("\nGEOMETRY VALIDATION")
print("-" * 55)

print(f"Valid geometries: {valid_geometries}")
print(f"Invalid geometries: {invalid_geometries}")
print(f"Empty geometries: {empty_geometries}")
print(f"Unique building IDs: {len(building_ids)}")
print(f"Duplicate IDs: {len(duplicate_ids)}")


print("\nATTRIBUTE AVAILABILITY")
print("-" * 55)

print(
    f"Buildings with floor counts: "
    f"{with_levels} ({percentage(with_levels)}%)"
)

print(
    f"Buildings with heights: "
    f"{with_height} ({percentage(with_height)}%)"
)

print(
    f"Buildings with construction dates: "
    f"{with_construction_date} "
    f"({percentage(with_construction_date)}%)"
)


print("\nTOP BUILDING TAGS")
print("-" * 55)

for building_type, count in building_types.most_common(10):
    print(f"{building_type}: {count}")


if invalid_samples:
    print("\nINVALID GEOMETRY SAMPLES")
    print("-" * 55)

    for building_id in invalid_samples:
        print(building_id)


print("\nVALIDATION COMPLETED")