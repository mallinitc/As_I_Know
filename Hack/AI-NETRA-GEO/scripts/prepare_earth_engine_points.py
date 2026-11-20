import csv
import json
from pathlib import Path

from shapely.geometry import shape

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "moosarambagh_osm_buildings.geojson"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "moosarambagh_building_points.csv"
)

with open(INPUT_FILE, "r", encoding="utf-8") as file:
    buildings = json.load(file)

records = []

for feature in buildings["features"]:

    polygon = shape(feature["geometry"])
    point = polygon.representative_point()

    records.append({
        "building_id": feature["properties"]["building_id"],
        "longitude": point.x,
        "latitude": point.y
    })

with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as file:

    writer = csv.DictWriter(
        file,
        fieldnames=[
            "building_id",
            "longitude",
            "latitude"
        ]
    )

    writer.writeheader()
    writer.writerows(records)

print(f"Prepared {len(records)} building points")
print(f"Output: {OUTPUT_FILE}")