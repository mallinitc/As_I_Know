import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Initial pilot area near Moosarambagh Metro, Hyderabad.
# Bounding box: south, west, north, east.
# This is a small test area, not the full Musi corridor.

SOUTH = 17.3698
WEST = 78.5105
NORTH = 17.3723
EAST = 78.5138

bbox = f"{SOUTH},{WEST},{NORTH},{EAST}"

query = f"""
[out:json][timeout:60];
way["building"]({bbox});
out meta geom;
"""

endpoint = "https://overpass-api.de/api/interpreter"

data = urllib.parse.urlencode({
    "data": query
}).encode("utf-8")

request = urllib.request.Request(
    endpoint,
    data=data,
    headers={
        "User-Agent": "AINETRA-Hackathon-Research/0.1"
    }
)

print("Downloading real OSM building polygons...")

with urllib.request.urlopen(
    request,
    timeout=90
) as response:
    osm_data = json.load(response)

features = []

for element in osm_data.get("elements", []):

    if element["type"] != "way":
        continue

    geometry = element.get("geometry", [])

    coordinates = [
        [point["lon"], point["lat"]]
        for point in geometry
    ]

    if len(coordinates) < 4:
        continue

    # GeoJSON Polygon rings must be closed.
    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])

    tags = element.get("tags", {})

    feature = {
        "type": "Feature",
        "properties": {
            "building_id": f"osm-way-{element['id']}",
            "source": "OpenStreetMap",
            "source_id": element["id"],
            "source_timestamp": element.get("timestamp"),
            "building_type": tags.get("building"),
            "building_levels": tags.get("building:levels"),
            "height": tags.get("height"),
            "construction_date": tags.get("start_date"),
            "source_classification": "crowdsourced",
            "tags": tags
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [coordinates]
        }
    }

    features.append(feature)

collection = {
    "type": "FeatureCollection",
    "metadata": {
        "project": "AI NETRA",
        "workstream": "Building Intelligence",
        "pilot": "Moosarambagh",
        "source": "OpenStreetMap",
        "license": "ODbL-1.0",
        "attribution": "© OpenStreetMap contributors",
        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "bbox": [WEST, SOUTH, EAST, NORTH],
        "limitations": [
            "OSM building coverage may be incomplete",
            "Only building ways are included",
            "Building multipolygon relations are not yet included",
            "Building tags are not independently verified"
        ]
    },
    "features": features
}

output = Path("data/moosarambagh_osm_buildings.geojson")

output.write_text(
    json.dumps(collection, indent=2),
    encoding="utf-8"
)

print(f"\nBuildings downloaded: {len(features)}")
print(f"Saved to: {output.resolve()}")

print("\nSample building attributes:")

for feature in features[:5]:
    print(json.dumps(
        feature["properties"],
        indent=2
    ))

if not features:
    print(
        "\nNo building ways returned. "
        "Check API access or pilot coverage."
    )