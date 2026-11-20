"""
AI NETRA — TGRAC Inundation Data Validation
Step: 8.53

Validates the original Telangana Government
ArcGIS inundation-location dataset.

Does not modify the original source file.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

INPUT = DATA / "tgrac_inundation_points_raw_v1.json"
REPORT = DATA / "tgrac_inundation_validation_v1.json"

# Expanded AI NETRA pilot bounding box
SOUTH = 17.36
NORTH = 17.38
WEST = 78.50
EAST = 78.53

print("\nAI NETRA — TGRAC INUNDATION VALIDATION")
print("=" * 60)

if not INPUT.exists():
    raise SystemExit(f"Source file not found: {INPUT}")

try:
    with INPUT.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
except json.JSONDecodeError as exc:
    raise SystemExit(
        f"Invalid JSON: {exc}\n"
        "Verify that the browser saved the actual JSON response, "
        "not an HTML webpage."
    )

if "error" in data:
    raise SystemExit(
        "ArcGIS returned an error:\n"
        + json.dumps(data["error"], indent=2)
    )

features = data.get("features")

if not isinstance(features, list):
    raise SystemExit(
        "No ArcGIS features array found. "
        "Check the downloaded JSON response."
    )

print(f"Total records: {len(features)}")

inside = []
outside = []
invalid = []

attribute_fields = set()

for index, feature in enumerate(features):

    attributes = feature.get("attributes") or {}
    geometry = feature.get("geometry") or {}

    attribute_fields.update(attributes.keys())

    name = (
        attributes.get("Name")
        or attributes.get("NAME")
        or attributes.get("name")
        or attributes.get("LOCATION")
        or attributes.get("Location")
        or "Unknown"
    )

    lon = geometry.get("x")
    lat = geometry.get("y")

    record = {
        "record_number": index + 1,
        "name": str(name),
        "latitude": lat,
        "longitude": lon,
        "attributes": attributes,
    }

    if (
        not isinstance(lat, (int, float))
        or not isinstance(lon, (int, float))
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
    ):
        invalid.append(record)
        continue

    if (
        SOUTH <= lat <= NORTH
        and WEST <= lon <= EAST
    ):
        inside.append(record)
    else:
        outside.append(record)

print(f"Valid coordinates: {len(inside) + len(outside)}")
print(f"Invalid coordinates: {len(invalid)}")
print(f"Inside pilot area: {len(inside)}")
print(f"Outside pilot area: {len(outside)}")

print("\nAVAILABLE SOURCE ATTRIBUTES")
print("-" * 60)

for field in sorted(attribute_fields):
    print(field)

print("\nLOCATIONS INSIDE PILOT AREA")
print("-" * 60)

if inside:
    for record in inside:
        print(
            f"{record['name']} | "
            f"Lat: {record['latitude']} | "
            f"Lon: {record['longitude']}"
        )
else:
    print("No records inside the pilot bounding box.")

report = {
    "project": "AI NETRA",
    "step": "8.53",
    "source": "Telangana Government TGRAC ArcGIS",
    "source_layer": "Inundation Areas",
    "source_layer_id": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "total_records": len(features),
    "valid_coordinates": len(inside) + len(outside),
    "invalid_coordinates": len(invalid),
    "inside_pilot": len(inside),
    "outside_pilot": len(outside),
    "pilot_bbox": [WEST, SOUTH, EAST, NORTH],
    "source_attribute_fields": sorted(attribute_fields),
    "inside_records": inside,
    "invalid_records": invalid,
    "interpretation": (
        "Government-mapped inundation-related point locations. "
        "Not verified historical inundation polygons."
    ),
    "historical_event_date": None,
    "building_level_flood_exposure_confirmed": False,
}

with REPORT.open("w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print("\nVALIDATION REPORT")
print(REPORT)

print("\nTGRAC VALIDATION COMPLETED")