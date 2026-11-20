"""
AI NETRA — Geospatial Building Catalog
Workstream: GEO-001
Version: 0.5.0

Creates an enriched GeoJSON catalog containing:
- 11,659 validated OSM building polygons
- Google Open Buildings 2.5D estimated heights
- Height-quality indicators
- Source provenance
- Missing-attribute tracking

No source datasets are modified.

Dependencies:
- Python 3.11 standard library
"""

import csv
import json
import math

from pathlib import Path
from datetime import datetime, timezone
from collections import Counter


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"

OSM_FILE = (
    DATA / "moosarambagh_osm_buildings_expanded_v1.geojson"
)

HEIGHT_FILE = (
    DATA / "ai_netra_merged_heights_2023_v1.csv"
)

OUTPUT_FILE = (
    DATA / "ai_netra_building_catalog_v1.geojson"
)

REPORT_FILE = (
    DATA / "building_catalog_validation_v1.json"
)

LOW_HEIGHT_THRESHOLD_M = 2.0


# ============================================================
# 2. LOAD HEIGHT DATA
# ============================================================

height_lookup = {}

with open(
    HEIGHT_FILE,
    newline="",
    encoding="utf-8-sig"
) as file:

    reader = csv.DictReader(file)

    for row in reader:

        building_id = row.get("building_id")

        if not building_id:
            continue

        raw_height = row.get("estimated_height_m")

        height = None

        if raw_height:

            try:

                parsed = float(raw_height)

                if math.isfinite(parsed) and parsed > 0:
                    height = parsed

            except (ValueError, TypeError):
                pass

        height_lookup[building_id] = {

            "estimated_height_m": height,

            "height_source": row.get(
                "height_source",
                "Google Open Buildings 2.5D"
            ),

            "height_dataset_year": 2023,

            "height_measurement_type": "model_estimate",

            "height_sampling_method": "representative_point",

            "height_verification": "not_field_verified",

            "height_quality_flag": (
                "unavailable"
                if height is None
                else "review_low_estimate"
                if height < LOW_HEIGHT_THRESHOLD_M
                else "unverified_estimate"
            )
        }


# ============================================================
# 3. LOAD EXPANDED OSM DATASET
# ============================================================

with open(
    OSM_FILE,
    encoding="utf-8"
) as file:

    osm_data = json.load(file)

features = osm_data.get("features", [])


# ============================================================
# 4. BUILD ENRICHED CATALOG
# ============================================================

catalog_features = []

quality_counts = Counter()

missing_height_ids = []

for feature in features:

    properties = feature.get("properties", {}).copy()

    building_id = properties.get("building_id")

    height_record = height_lookup.get(building_id)

    if height_record is None:

        height_record = {
            "estimated_height_m": None,
            "height_source": None,
            "height_dataset_year": None,
            "height_measurement_type": "unknown",
            "height_sampling_method": None,
            "height_verification": "unavailable",
            "height_quality_flag": "unavailable"
        }

    properties.update(height_record)

    quality_flag = properties["height_quality_flag"]

    quality_counts[quality_flag] += 1

    if properties["estimated_height_m"] is None:
        missing_height_ids.append(building_id)

    properties["attribute_availability"] = {

        "building_levels": (
            properties.get("building_levels") is not None
        ),

        "osm_height": (
            properties.get("height") is not None
        ),

        "construction_date": (
            properties.get("construction_date") is not None
        ),

        "google_estimated_height": (
            properties.get("estimated_height_m") is not None
        )
    }

    catalog_features.append({

        "type": "Feature",

        "properties": properties,

        "geometry": feature["geometry"]
    })


# ============================================================
# 5. CREATE VERSIONED CATALOG
# ============================================================

catalog = {

    "type": "FeatureCollection",

    "metadata": {

        "project": "AI NETRA",

        "workstream": "Hyderabad Building Intelligence",

        "catalog_version": "1.0",

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "building_count": len(catalog_features),

        "coordinate_system": "EPSG:4326",

        "bounding_box": osm_data.get(
            "metadata",
            {}
        ).get("bbox"),

        "building_source": "OpenStreetMap",

        "height_source": "Google Open Buildings 2.5D",

        "height_dataset_year": 2023,

        "height_sampling_method": "representative_point",

        "height_verification": "model_estimate_not_field_verified",

        "height_quality_counts": dict(quality_counts),

        "limitations": [
            "OSM building coverage may be incomplete",
            "Google heights are model-derived estimates",
            "Zero-height samples are classified as unavailable",
            "Low estimates require review",
            "Building age is not established by OSM edit timestamps",
            "Floor counts are not inferred from estimated height",
            "No ground-truth height validation has been performed"
        ]
    },

    "features": catalog_features
}


# ============================================================
# 6. SAVE CATALOG
# ============================================================

OUTPUT_FILE.write_text(
    json.dumps(catalog, separators=(",", ":")),
    encoding="utf-8"
)


# ============================================================
# 7. SAVE VALIDATION REPORT
# ============================================================

report = {

    "catalog_version": "1.0",

    "total_buildings": len(catalog_features),

    "height_quality_counts": dict(quality_counts),

    "buildings_without_usable_height": len(
        missing_height_ids
    ),

    "sample_missing_height_ids": missing_height_ids[:10],

    "catalog_file": OUTPUT_FILE.name,

    "source_files": [
        OSM_FILE.name,
        HEIGHT_FILE.name
    ]
}

REPORT_FILE.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)


# ============================================================
# 8. PRINT VALIDATION SUMMARY
# ============================================================

print("\nAI NETRA — GEOSPATIAL CATALOG")
print("=" * 55)

print(f"Total buildings: {len(catalog_features)}")

print("\nHEIGHT QUALITY DISTRIBUTION")
print("-" * 55)

for status, count in quality_counts.items():
    print(f"{status}: {count}")

print(
    "\nBuildings without usable height:",
    len(missing_height_ids)
)

print("\nOUTPUT FILES")
print("-" * 55)

print(f"Catalog: {OUTPUT_FILE}")

print(f"Report: {REPORT_FILE}")

print("\nOriginal datasets preserved.")
print("CATALOG GENERATION COMPLETED")