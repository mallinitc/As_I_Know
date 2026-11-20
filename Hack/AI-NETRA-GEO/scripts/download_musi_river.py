"""
AI NETRA — Musi River Geospatial Data
Workstream: GEO-001
Step: 8.38

Downloads OpenStreetMap river features covering
the expanded Moosarambagh pilot area.

Sources:
- OSM waterway=river
- OSM waterway=riverbank
- OSM natural=water + water=river

Preserves raw Overpass response for inspection.

Dependencies:
- Python standard library

Does not modify existing datasets.
"""

import json
import urllib.parse
import urllib.request

from pathlib import Path
from datetime import datetime, timezone
from collections import Counter


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"

OUTPUT_FILE = DATA / "musi_river_osm_raw_v1.json"

METADATA_FILE = DATA / "musi_river_metadata_v1.json"

SOUTH = 17.3600
WEST = 78.5000
NORTH = 17.3800
EAST = 78.5300

BBOX = f"{SOUTH},{WEST},{NORTH},{EAST}"

ENDPOINT = "https://overpass-api.de/api/interpreter"


# ============================================================
# 2. OVERPASS QUERY
# ============================================================

query = f"""
[out:json][timeout:120];
(
  way["waterway"="river"]({BBOX});
  way["waterway"="riverbank"]({BBOX});
  way["natural"="water"]["water"="river"]({BBOX});
  relation["natural"="water"]["water"="river"]({BBOX});
  relation["waterway"="riverbank"]({BBOX});
);
out meta geom;
"""


# ============================================================
# 3. DOWNLOAD DATA
# ============================================================

print("\nAI NETRA — MUSI RIVER DATA DOWNLOAD")
print("=" * 55)

print("Area: Moosarambagh–Musi River Corridor")

print("Downloading real OSM waterway features...")

request_data = urllib.parse.urlencode({
    "data": query
}).encode("utf-8")

request = urllib.request.Request(
    ENDPOINT,
    data=request_data,
    headers={
        "User-Agent": "AINETRA-Geospatial-Research/0.5"
    }
)

with urllib.request.urlopen(
    request,
    timeout=180
) as response:

    osm_data = json.load(response)


# ============================================================
# 4. SAVE ORIGINAL RESPONSE
# ============================================================

DATA.mkdir(exist_ok=True)

OUTPUT_FILE.write_text(
    json.dumps(osm_data, indent=2),
    encoding="utf-8"
)


# ============================================================
# 5. INSPECT RIVER FEATURES
# ============================================================

elements = osm_data.get("elements", [])

feature_types = Counter()

river_features = []

for element in elements:

    tags = element.get("tags", {})

    feature_type = element.get("type", "unknown")

    feature_types[feature_type] += 1

    river_features.append({
        "osm_id": element.get("id"),
        "element_type": feature_type,
        "name": tags.get("name"),
        "waterway": tags.get("waterway"),
        "natural": tags.get("natural"),
        "water": tags.get("water"),
        "source_timestamp": element.get("timestamp")
    })


# ============================================================
# 6. SAVE METADATA
# ============================================================

metadata = {
    "project": "AI NETRA",
    "workstream": "Building Intelligence",
    "dataset_version": "1.0",
    "source": "OpenStreetMap",
    "license": "ODbL-1.0",
    "attribution": "© OpenStreetMap contributors",
    "retrieved_at": datetime.now(
        timezone.utc
    ).isoformat(),
    "bbox": [WEST, SOUTH, EAST, NORTH],
    "feature_count": len(elements),
    "feature_types": dict(feature_types),
    "features": river_features,
    "limitations": [
        "OSM river geometry is crowdsourced",
        "River centreline and water boundaries are different",
        "Water polygons may be incomplete",
        "Multipolygon relations require topology reconstruction",
        "Mapped water extent is not a verified flood boundary",
        "River geometry must be inspected before distance calculations"
    ]
}

METADATA_FILE.write_text(
    json.dumps(metadata, indent=2),
    encoding="utf-8"
)


# ============================================================
# 7. DISPLAY RESULTS
# ============================================================

print("\nDOWNLOAD RESULTS")
print("-" * 55)

print(f"Total features: {len(elements)}")

print("\nFEATURE TYPES")

for feature_type, count in feature_types.items():
    print(f"{feature_type}: {count}")

print("\nSAMPLE FEATURES")
print("-" * 55)

for feature in river_features[:10]:

    print(
        f"OSM ID: {feature['osm_id']} | "
        f"Type: {feature['element_type']} | "
        f"Name: {feature['name']} | "
        f"Waterway: {feature['waterway']} | "
        f"Water: {feature['water']}"
    )

print("\nFILES CREATED")
print("-" * 55)

print(OUTPUT_FILE)
print(METADATA_FILE)

print("\nDOWNLOAD COMPLETED")