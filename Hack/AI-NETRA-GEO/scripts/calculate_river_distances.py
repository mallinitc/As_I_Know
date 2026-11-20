"""
AI NETRA — Building-to-Musi River Distance Calculation
Workstream: GEO-001
Step: 8.41
Version: 1.0

Purpose:
- Calculate shortest distances from 11,659 building polygons
  to reconstructed OSM Musi River water-area polygons.
- Preserve source evidence and calculation metadata.
- Identify buildings intersecting mapped river water areas.
- Create a versioned distance dataset and validation report.

Dependencies:
- Python 3.11
- Shapely 2.x

No Pandas, GeoPandas, or PyProj required.

Important:
These distances are geographic proximity indicators,
NOT flood-risk scores or historical flood evidence.
"""

import csv
import json
import math
import statistics

from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

from shapely.geometry import shape
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BUILDINGS_FILE = DATA / "ai_netra_building_catalog_v1.geojson"

RIVER_FILE = DATA / "musi_river_water_polygons_v1.geojson"

OUTPUT_FILE = DATA / "ai_netra_musi_distances_v1.csv"

REPORT_FILE = DATA / "musi_distance_validation_v1.json"

EARTH_RADIUS_M = 6371008.8

# Local projection reference near Moosarambagh.
REF_LAT = 17.37
REF_LON = 78.515


# ============================================================
# 2. LOCAL METRIC PROJECTION
# ============================================================

def project_to_metres(geometry):
    """
    Approximate WGS84 geometry in local metre coordinates.

    Uses a fixed-reference equirectangular projection
    suitable for preliminary analysis over this small
    Hyderabad pilot area.

    Not an authoritative geodetic survey.
    """

    ref_lat_rad = math.radians(REF_LAT)
    ref_lon_rad = math.radians(REF_LON)

    def converter(lon, lat, z=None):

        x = (
            EARTH_RADIUS_M
            * (math.radians(lon) - ref_lon_rad)
            * math.cos(ref_lat_rad)
        )

        y = (
            EARTH_RADIUS_M
            * (math.radians(lat) - ref_lat_rad)
        )

        if z is not None:
            return x, y, z

        return x, y

    return transform(converter, geometry)


# ============================================================
# 3. LOAD BUILDINGS
# ============================================================

with open(
    BUILDINGS_FILE,
    "r",
    encoding="utf-8"
) as file:
    building_data = json.load(file)

building_features = building_data.get("features", [])

print("\nAI NETRA — MUSI RIVER DISTANCE CALCULATION")
print("=" * 60)

print(f"Building records: {len(building_features)}")


# ============================================================
# 4. LOAD RIVER WATER POLYGONS
# ============================================================

with open(
    RIVER_FILE,
    "r",
    encoding="utf-8"
) as file:
    river_data = json.load(file)

river_features = river_data.get("features", [])

river_geometries = []
river_ids = []

for feature in river_features:

    geometry = shape(feature["geometry"])

    if geometry.is_empty or not geometry.is_valid:
        continue

    river_geometries.append(
        project_to_metres(geometry)
    )

    river_ids.append(
        feature["properties"].get("waterbody_id")
    )

if not river_geometries:
    raise RuntimeError(
        "No valid Musi River water polygons available."
    )

print(f"Valid river polygons: {len(river_geometries)}")

river_union = unary_union(river_geometries)

print(f"Combined river geometry: {river_union.geom_type}")


# ============================================================
# 5. BUILDING DISTANCE CALCULATION
# ============================================================

records = []
distances = []

intersecting_count = 0
failed_count = 0

distance_categories = Counter()

for index, feature in enumerate(building_features, start=1):

    properties = feature.get("properties", {})

    building_id = properties.get("building_id")

    try:

        geometry = shape(feature["geometry"])

        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("Invalid building polygon")

        projected_building = project_to_metres(geometry)

        # Distance from building footprint to mapped water.
        distance_m = projected_building.distance(
            river_union
        )

        intersects_water = projected_building.intersects(
            river_union
        )

        if intersects_water:
            intersecting_count += 1

        # Descriptive proximity bands, not flood risk.
        if distance_m == 0:
            category = "intersects_mapped_water"
        elif distance_m <= 50:
            category = "within_50m"
        elif distance_m <= 100:
            category = "within_100m"
        elif distance_m <= 250:
            category = "within_250m"
        elif distance_m <= 500:
            category = "within_500m"
        else:
            category = "beyond_500m"

        distance_categories[category] += 1

        records.append({
            "building_id": building_id,
            "distance_to_musi_water_m": round(
                distance_m,
                2
            ),
            "intersects_mapped_water": intersects_water,
            "proximity_band": category,
            "river_source": "OpenStreetMap",
            "river_geometry_type": "mapped_water_polygon",
            "river_geometry_ids": ";".join(river_ids),
            "distance_method": (
                "local_equirectangular_polygon_distance"
            ),
            "verification_status": (
                "geometry_derived_unverified"
            ),
            "flood_risk_assigned": False
        })

        distances.append(distance_m)

    except Exception as error:

        failed_count += 1

        print(
            f"Failed building {building_id}: {error}"
        )

    if index % 2000 == 0:
        print(
            f"Processed {index}/{len(building_features)} buildings"
        )


# ============================================================
# 6. EXPORT DISTANCE DATASET
# ============================================================

fieldnames = [
    "building_id",
    "distance_to_musi_water_m",
    "intersects_mapped_water",
    "proximity_band",
    "river_source",
    "river_geometry_type",
    "river_geometry_ids",
    "distance_method",
    "verification_status",
    "flood_risk_assigned"
]

with open(
    OUTPUT_FILE,
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


# ============================================================
# 7. VALIDATION REPORT
# ============================================================

report = {
    "project": "AI NETRA",
    "workstream": "Hyderabad Building Intelligence",
    "step": "8.41",
    "generated_at": datetime.now(
        timezone.utc
    ).isoformat(),
    "total_buildings": len(building_features),
    "distances_calculated": len(records),
    "failed_records": failed_count,
    "river_water_polygons": len(river_geometries),
    "buildings_intersecting_mapped_water": intersecting_count,
    "proximity_categories": dict(distance_categories),
    "minimum_distance_m": min(distances) if distances else None,
    "maximum_distance_m": max(distances) if distances else None,
    "mean_distance_m": statistics.mean(distances) if distances else None,
    "median_distance_m": statistics.median(distances) if distances else None,
    "distance_method": "local_equirectangular_polygon_distance",
    "source": "OpenStreetMap",
    "limitations": [
        "Mapped water polygons are not verified flood boundaries",
        "Water polygons may not reflect current river extent",
        "Distance is measured to mapped polygon, not historical flood extent",
        "Calculations use an approximate local metric projection",
        "Near-river proximity does not establish flood risk",
        "River geometry may be incomplete outside mapped segments"
    ]
}

REPORT_FILE.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)


# ============================================================
# 8. PRINT RESULTS
# ============================================================

print("\nDISTANCE CALCULATION RESULTS")
print("-" * 60)

print(f"Total buildings: {len(building_features)}")
print(f"Distances calculated: {len(records)}")
print(f"Failed records: {failed_count}")
print(f"Buildings intersecting mapped water: {intersecting_count}")

print("\nPROXIMITY DISTRIBUTION")
print("-" * 60)

for category, count in distance_categories.items():
    print(f"{category}: {count}")

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
        record["distance_to_musi_water_m"],
        "m |",
        record["proximity_band"]
    )

print("\nOUTPUT FILES")
print("-" * 60)

print(OUTPUT_FILE)
print(REPORT_FILE)

print("\nMUSI DISTANCE CALCULATION COMPLETED")