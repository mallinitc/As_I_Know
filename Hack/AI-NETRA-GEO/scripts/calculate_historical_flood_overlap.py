import csv
import json
import math
from pathlib import Path

from shapely.geometry import shape, box
from shapely.ops import unary_union, transform

# ============================================================
# AI NETRA — STEP 8.92
# Historical Flood Polygon / Building Footprint Overlap
#
# Purpose:
# Calculate percentage of each building footprint overlapping
# the mapped historical flood-affected-area polygons.
#
# IMPORTANT:
# Spatial overlap is NOT verified building inundation.
# ============================================================

BUILDINGS_FILE = Path(
    "data/ai_netra_building_catalog_v1.geojson"
)

FLOOD_FILE = Path(
    "data/ai_netra_historical_flood_polygons_pilot_v1.geojson"
)

OUTPUT_FILE = Path(
    "data/ai_netra_historical_flood_building_overlap_v1.csv"
)

PILOT = box(78.50, 17.36, 78.53, 17.38)

# Local metric approximation centered on pilot.
LAT0 = 17.37
LON0 = 78.515
R = 6371008.8

COS_LAT = math.cos(math.radians(LAT0))


def to_meters(x, y, z=None):
    mx = math.radians(x - LON0) * R * COS_LAT
    my = math.radians(y - LAT0) * R
    return mx, my


def load_features(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)["features"]


buildings = load_features(BUILDINGS_FILE)
flood_features = load_features(FLOOD_FILE)

print("\n=== AI NETRA — STEP 8.92 ===")
print("Buildings loaded:", len(buildings))
print("Historical polygons loaded:", len(flood_features))

# ------------------------------------------------------------
# 1. Prepare historical flood-affected geometry
# ------------------------------------------------------------

flood_polygons = []

for feature in flood_features:

    geom = shape(feature["geometry"])

    if not geom.is_valid:
        raise ValueError("Invalid historical flood geometry.")

    clipped = geom.intersection(PILOT)

    if not clipped.is_empty:
        flood_polygons.append(clipped)

flood_union = unary_union(flood_polygons)

if flood_union.is_empty:
    raise RuntimeError("Historical flood geometry is empty.")

# ------------------------------------------------------------
# 2. Calculate overlap for every building
# ------------------------------------------------------------

rows = []

categories = {
    "No overlap": 0,
    "Greater than 0% to 1%": 0,
    "Greater than 1% to 10%": 0,
    "Greater than 10% to 50%": 0,
    "Greater than 50% to 90%": 0,
    "Greater than 90% to 100%": 0,
}

for index, feature in enumerate(buildings, start=1):

    geom = shape(feature["geometry"])

    if not geom.is_valid or geom.is_empty:
        continue

    if not geom.intersects(PILOT):
        continue

    building = geom.intersection(PILOT)

    if building.is_empty:
        continue

    building_metric = transform(to_meters, building)
    building_area = building_metric.area

    if building_area <= 0:
        continue

    intersection = building.intersection(flood_union)

    overlap_area = 0.0

    if not intersection.is_empty:
        overlap_metric = transform(
            to_meters,
            intersection
        )
        overlap_area = overlap_metric.area

    overlap_pct = min(
        100.0,
        max(0.0, (overlap_area / building_area) * 100)
    )

    if overlap_pct == 0:
        category = "No overlap"
    elif overlap_pct <= 1:
        category = "Greater than 0% to 1%"
    elif overlap_pct <= 10:
        category = "Greater than 1% to 10%"
    elif overlap_pct <= 50:
        category = "Greater than 10% to 50%"
    elif overlap_pct <= 90:
        category = "Greater than 50% to 90%"
    else:
        category = "Greater than 90% to 100%"

    categories[category] += 1

    props = feature.get("properties", {})

    building_id = (
        props.get("building_id")
        or feature.get("id")
        or f"building-{index}"
    )

    rows.append({
        "building_id": building_id,
        "building_area_in_pilot_m2": round(building_area, 4),
        "historical_polygon_overlap_m2": round(overlap_area, 4),
        "historical_polygon_overlap_pct": round(overlap_pct, 4),
        "overlap_category": category,
        "evidence_source": "Hyderabad Floods 2020 SpatialMap",
        "evidence_status": "geometric_overlap_only",
        "confirmed_building_flooding": "not_established"
    })

# ------------------------------------------------------------
# 3. Export CSV
# ------------------------------------------------------------

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

with OUTPUT_FILE.open(
    "w",
    newline="",
    encoding="utf-8"
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "building_id",
            "building_area_in_pilot_m2",
            "historical_polygon_overlap_m2",
            "historical_polygon_overlap_pct",
            "overlap_category",
            "evidence_source",
            "evidence_status",
            "confirmed_building_flooding"
        ]
    )

    writer.writeheader()
    writer.writerows(rows)

# ------------------------------------------------------------
# 4. Results
# ------------------------------------------------------------

print("\n=== BUILDING OVERLAP DISTRIBUTION ===")

for category, count in categories.items():
    print(f"{category}: {count}")

total_overlap = sum(
    count
    for category, count in categories.items()
    if category != "No overlap"
)

print("\n=== SUMMARY ===")

print("Buildings analyzed:", len(rows))
print("Buildings with any overlap:", total_overlap)
print("Buildings without overlap:", categories["No overlap"])

print("\nOutput file:", OUTPUT_FILE)

print("\nIMPORTANT:")
print("Overlap percentages are geometric measurements.")
print("They do not establish actual building flooding.")
print("Areas use a local metric approximation.")
print("Pilot-clipped building footprints are the denominator.")
print("Original source datasets remain unchanged.")
