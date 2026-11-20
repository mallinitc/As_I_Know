"""
AI NETRA — Building-to-Waterlogging Location Proximity
Step 8.58

Input:
    ai_netra_building_catalog_v1.geojson
    tgrac_waterlogging_points_v1.geojson

Output:
    ai_netra_waterlogging_distances_v1.csv
    waterlogging_distance_validation_v1.json

Distances are measured from building footprints to
government-mapped waterlogging points.

These are proximity measurements, NOT flood-risk scores.
"""

import csv
import json
import math
import statistics

from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

from shapely.geometry import shape
from shapely.affinity import scale


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BUILDINGS_FILE = DATA / "ai_netra_building_catalog_v1.geojson"
WATERLOGGING_FILE = DATA / "tgrac_waterlogging_points_v1.geojson"

OUTPUT_FILE = DATA / "ai_netra_waterlogging_distances_v1.csv"
REPORT_FILE = DATA / "waterlogging_distance_validation_v1.json"

EARTH_RADIUS_M = 6371008.8
REF_LAT = 17.37

METRES_PER_DEGREE_LAT = EARTH_RADIUS_M * math.pi / 180
METRES_PER_DEGREE_LON = (
    METRES_PER_DEGREE_LAT * math.cos(math.radians(REF_LAT))
)


def project_geometry(geometry):
    """Approximate local metric projection for the Hyderabad pilot."""

    return scale(
        geometry,
        xfact=METRES_PER_DEGREE_LON,
        yfact=METRES_PER_DEGREE_LAT,
        origin=(78.515, REF_LAT),
    )


def proximity_band(distance):
    if distance == 0:
        return "contains_mapped_point"
    if distance <= 100:
        return "within_100m"
    if distance <= 250:
        return "within_250m"
    if distance <= 500:
        return "within_500m"
    if distance <= 1000:
        return "within_1000m"
    return "beyond_1000m"


print("\nAI NETRA — WATERLOGGING PROXIMITY ANALYSIS")
print("=" * 60)


# ------------------------------------------------------------
# LOAD DATA
# ------------------------------------------------------------

with BUILDINGS_FILE.open(encoding="utf-8") as file:
    building_data = json.load(file)

with WATERLOGGING_FILE.open(encoding="utf-8") as file:
    waterlogging_data = json.load(file)

buildings = building_data.get("features", [])
locations = waterlogging_data.get("features", [])

print(f"Building records: {len(buildings)}")
print(f"Government waterlogging locations: {len(locations)}")


# ------------------------------------------------------------
# PREPARE WATERLOGGING POINTS
# ------------------------------------------------------------

waterlogging_points = []

for feature in locations:

    geometry = shape(feature["geometry"])

    if geometry.is_empty or geometry.geom_type != "Point":
        continue

    properties = feature.get("properties", {})

    waterlogging_points.append({
        "id": properties.get("waterlogging_id"),
        "name": properties.get("name"),
        "geometry": project_geometry(geometry),
    })

if not waterlogging_points:
    raise RuntimeError("No valid waterlogging points available.")


# ------------------------------------------------------------
# CALCULATE DISTANCES
# ------------------------------------------------------------

records = []
distances = []
bands = Counter()
failed = 0

for feature in buildings:

    properties = feature.get("properties", {})
    building_id = properties.get("building_id")

    try:
        geometry = shape(feature["geometry"])

        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("Invalid building geometry")

        projected_building = project_geometry(geometry)

        nearest = min(
            waterlogging_points,
            key=lambda point: projected_building.distance(
                point["geometry"]
            ),
        )

        distance = projected_building.distance(nearest["geometry"])

        if not math.isfinite(distance):
            raise ValueError("Non-finite distance")

        band = proximity_band(distance)

        records.append({
            "building_id": building_id,
            "nearest_waterlogging_location": nearest["name"],
            "nearest_waterlogging_id": nearest["id"],
            "distance_to_waterlogging_point_m": round(distance, 2),
            "proximity_band": band,
            "source": "Telangana Government TGRAC",
            "geometry_type": "mapped_waterlogging_point",
            "distance_method": "local_equirectangular_footprint_to_point",
            "verification_status": "geometry_derived_unverified",
            "historical_flood_confirmed": False,
            "building_flooding_confirmed": False,
            "flood_risk_assigned": False,
        })

        distances.append(distance)
        bands[band] += 1

    except Exception as error:
        failed += 1
        print(f"Failed {building_id}: {error}")


# ------------------------------------------------------------
# EXPORT CSV
# ------------------------------------------------------------

fields = [
    "building_id",
    "nearest_waterlogging_location",
    "nearest_waterlogging_id",
    "distance_to_waterlogging_point_m",
    "proximity_band",
    "source",
    "geometry_type",
    "distance_method",
    "verification_status",
    "historical_flood_confirmed",
    "building_flooding_confirmed",
    "flood_risk_assigned",
]

with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fields)
    writer.writeheader()
    writer.writerows(records)


# ------------------------------------------------------------
# VALIDATION REPORT
# ------------------------------------------------------------

report = {
    "project": "AI NETRA",
    "step": "8.58",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "total_buildings": len(buildings),
    "waterlogging_locations": len(waterlogging_points),
    "distances_calculated": len(records),
    "failed_records": failed,
    "proximity_distribution": dict(bands),
    "minimum_distance_m": min(distances) if distances else None,
    "maximum_distance_m": max(distances) if distances else None,
    "average_distance_m": statistics.mean(distances) if distances else None,
    "median_distance_m": statistics.median(distances) if distances else None,
    "source": "Telangana Government TGRAC",
    "method": "local_equirectangular_footprint_to_point",
    "limitations": [
        "Government points are not inundation boundaries.",
        "Observation dates are unavailable.",
        "The dataset may not contain every waterlogging location.",
        "Nearest point does not establish historical flooding.",
        "Distances use an approximate local metric projection.",
        "No flood-risk classification has been assigned.",
    ],
}

REPORT_FILE.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)


# ------------------------------------------------------------
# RESULTS
# ------------------------------------------------------------

print("\nCALCULATION RESULTS")
print("-" * 60)

print(f"Total buildings: {len(buildings)}")
print(f"Distances calculated: {len(records)}")
print(f"Failed records: {failed}")

print("\nPROXIMITY DISTRIBUTION")
print("-" * 60)

for band, count in sorted(bands.items()):
    print(f"{band}: {count}")

if distances:
    print("\nDISTANCE STATISTICS")
    print("-" * 60)

    print(f"Minimum: {min(distances):.2f} m")
    print(f"Maximum: {max(distances):.2f} m")
    print(f"Average: {statistics.mean(distances):.2f} m")
    print(f"Median: {statistics.median(distances):.2f} m")

print("\nSAMPLE BUILDINGS")
print("-" * 60)

for record in records[:5]:
    print(
        record["building_id"],
        "=>",
        record["nearest_waterlogging_location"],
        "|",
        record["distance_to_waterlogging_point_m"],
        "m",
    )

print("\nOUTPUT FILES")
print(OUTPUT_FILE)
print(REPORT_FILE)

print("\nWATERLOGGING DISTANCE CALCULATION COMPLETED")