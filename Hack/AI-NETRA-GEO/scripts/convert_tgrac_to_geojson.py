"""
AI NETRA — TGRAC Waterlogging GeoJSON Conversion
Step 8.55

Converts Telangana Government ArcGIS point records
into GeoJSON.

Preserves original source attributes.
Does not modify the original JSON.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

INPUT = DATA / "tgrac_inundation_points_raw_v1.json"

OUTPUT = DATA / "tgrac_waterlogging_points_v1.geojson"

with INPUT.open("r", encoding="utf-8-sig") as file:
    source = json.load(file)

if "error" in source:
    raise RuntimeError(
        f"ArcGIS returned an error: {source['error']}"
    )

features = []
skipped = 0

for record in source.get("features", []):

    attributes = record.get("attributes") or {}
    geometry = record.get("geometry") or {}

    lon = geometry.get("x")
    lat = geometry.get("y")

    if not isinstance(lon, (int, float)):
        skipped += 1
        continue

    if not isinstance(lat, (int, float)):
        skipped += 1
        continue

    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        skipped += 1
        continue

    feature = {
        "type": "Feature",
        "properties": {
            "waterlogging_id": attributes.get("OID"),
            "name": attributes.get("Name"),
            "classification": "mapped_waterlogging_location",
            "source": "Telangana Government TGRAC",
            "source_layer": "Inundation Areas",
            "original_folder": attributes.get("FolderPath"),
            "observation_date": None,
            "water_depth_m": None,
            "duration_hours": None,
            "verification_status": (
                "government_mapped_point_not_field_verified"
            ),
            "building_flooding_confirmed": False,
            "original_attributes": attributes,
        },
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat],
        },
    }

    features.append(feature)

collection = {
    "type": "FeatureCollection",
    "metadata": {
        "project": "AI NETRA",
        "dataset_version": "1.0",
        "source": "Telangana Government TGRAC",
        "original_dataset": "MAJOR WATER LOGGING PLACES.kmz",
        "source_layer": "Inundation Areas",
        "geometry_type": "Point",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "feature_count": len(features),
        "limitations": [
            "Points do not represent inundation boundaries",
            "Observation dates are unavailable",
            "Water depth and duration are unavailable",
            "Nearby buildings are not confirmed flooded",
        ],
    },
    "features": features,
}

OUTPUT.write_text(
    json.dumps(collection, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\nAI NETRA — TGRAC WATERLOGGING CONVERSION")
print("=" * 55)
print(f"Source records: {len(source.get('features', []))}")
print(f"Converted points: {len(features)}")
print(f"Skipped records: {skipped}")
print(f"Output: {OUTPUT}")
print("\nCONVERSION COMPLETED")