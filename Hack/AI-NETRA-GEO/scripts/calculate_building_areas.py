"""
AI NETRA — Building Footprint Area Calculation
Workstream: GEO-001
Step: 8.35

Calculates approximate building footprint areas
using real OpenStreetMap polygons.

Input:
    ai_netra_building_catalog_v1.geojson

Outputs:
    ai_netra_building_areas_v1.csv
    building_area_validation_v1.json

Dependencies:
    Python 3.11
    Shapely

Does not modify existing datasets.
"""

import csv
import json
import math
import statistics

from pathlib import Path
from datetime import datetime, timezone

from shapely.geometry import shape
from shapely.ops import transform


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"

INPUT_FILE = DATA / "ai_netra_building_catalog_v1.geojson"

OUTPUT_FILE = DATA / "ai_netra_building_areas_v1.csv"

REPORT_FILE = DATA / "building_area_validation_v1.json"

EARTH_RADIUS_M = 6371008.8


# ============================================================
# 2. LOCAL METRIC PROJECTION
# ============================================================

def calculate_area_m2(geometry):
    """
    Calculate approximate polygon area in square metres.

    Uses a local equirectangular projection centered
    on the polygon's representative point.

    Appropriate for preliminary small-building analysis
    in the Hyderabad pilot area.

    Not suitable for authoritative cadastral surveying.
    """

    reference = geometry.representative_point()

    ref_lon = math.radians(reference.x)
    ref_lat = math.radians(reference.y)

    def project(lon, lat, z=None):

        x = (
            EARTH_RADIUS_M
            * (math.radians(lon) - ref_lon)
            * math.cos(ref_lat)
        )

        y = (
            EARTH_RADIUS_M
            * (math.radians(lat) - ref_lat)
        )

        if z is not None:
            return x, y, z

        return x, y

    projected_geometry = transform(
        project,
        geometry
    )

    return projected_geometry.area


# ============================================================
# 3. LOAD BUILDINGS
# ============================================================

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8"
) as file:

    catalog = json.load(file)

features = catalog.get("features", [])

print("\nAI NETRA — BUILDING FOOTPRINT AREA")
print("=" * 55)

print(f"Total building records: {len(features)}")


# ============================================================
# 4. CALCULATE AREAS
# ============================================================

records = []

areas = []

invalid_count = 0

for feature in features:

    properties = feature.get("properties", {})

    building_id = properties.get("building_id")

    try:

        geometry = shape(feature["geometry"])

        if geometry.is_empty or not geometry.is_valid:
            invalid_count += 1
            continue

        area_m2 = calculate_area_m2(geometry)

        if not math.isfinite(area_m2) or area_m2 <= 0:
            invalid_count += 1
            continue

        records.append({
            "building_id": building_id,
            "footprint_area_m2": round(area_m2, 2),
            "area_source": "OpenStreetMap",
            "area_method": "local_equirectangular_projection",
            "verification_status": "geometry_derived_unverified"
        })

        areas.append(area_m2)

    except Exception as error:

        invalid_count += 1

        print(
            f"Error processing {building_id}: {error}"
        )


# ============================================================
# 5. SAVE RESULTS
# ============================================================

fieldnames = [
    "building_id",
    "footprint_area_m2",
    "area_source",
    "area_method",
    "verification_status"
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
# 6. STATISTICAL VALIDATION
# ============================================================

report = {
    "project": "AI NETRA",
    "step": "8.35",
    "generated_at": datetime.now(
        timezone.utc
    ).isoformat(),
    "total_buildings": len(features),
    "areas_calculated": len(areas),
    "invalid_records": invalid_count,
    "minimum_area_m2": min(areas) if areas else None,
    "maximum_area_m2": max(areas) if areas else None,
    "mean_area_m2": statistics.mean(areas) if areas else None,
    "median_area_m2": statistics.median(areas) if areas else None,
    "method": "local_equirectangular_projection",
    "source": "OpenStreetMap",
    "limitations": [
        "Areas are derived from crowdsourced OSM polygons",
        "Calculations use an approximate local metric projection",
        "OSM footprints may not match physical building boundaries",
        "Areas are not cadastral or survey-verified",
        "Footprint area does not represent total floor area"
    ]
}

REPORT_FILE.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)


# ============================================================
# 7. DISPLAY RESULTS
# ============================================================

print("\nCALCULATION RESULTS")
print("-" * 55)

print(f"Total buildings: {len(features)}")
print(f"Areas calculated: {len(areas)}")
print(f"Invalid records: {invalid_count}")

if areas:

    print(f"Minimum area: {min(areas):.2f} m²")
    print(f"Maximum area: {max(areas):.2f} m²")
    print(f"Average area: {statistics.mean(areas):.2f} m²")
    print(f"Median area: {statistics.median(areas):.2f} m²")

print("\nSAMPLE BUILDINGS")
print("-" * 55)

for record in records[:5]:

    print(
        record["building_id"],
        "=>",
        record["footprint_area_m2"],
        "m²"
    )

print("\nOUTPUT FILES")
print("-" * 55)

print(OUTPUT_FILE)
print(REPORT_FILE)

print("\nAREA CALCULATION COMPLETED")