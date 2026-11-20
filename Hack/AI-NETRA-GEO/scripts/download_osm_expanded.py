"""
AI NETRA — Expanded OSM Building Downloader
Workstream: GEO-001
Version: 0.4.1

Capabilities:
- Split expanded pilot area into smaller sections
- Download real OSM building polygons
- Handle temporary Overpass API failures
- Preserve partial download progress
- Deduplicate buildings
- Preserve source metadata
- Avoid overwriting existing working datasets

Dependencies:
- Python 3.11 standard library
"""

import json
import time
import urllib.parse
import urllib.request
import urllib.error

from pathlib import Path
from datetime import datetime, timezone


# ============================================================
# 1. PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"

DATA_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = (
    DATA_DIR
    / "moosarambagh_osm_buildings_expanded_v1.geojson"
)

PARTIAL_FILE = (
    DATA_DIR
    / "moosarambagh_osm_buildings_expanded_partial_v1.geojson"
)

# Existing original dataset must remain unchanged.
ORIGINAL_FILE = (
    DATA_DIR
    / "moosarambagh_osm_buildings.geojson"
)


# ============================================================
# 2. EXPANDED PILOT AREA
# ============================================================

SOUTH = 17.3600
WEST = 78.5000
NORTH = 17.3800
EAST = 78.5300

# Divide into 2 x 2 geographic sections.
ROWS = 2
COLS = 2


# ============================================================
# 3. OVERPASS SERVERS
# ============================================================

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

REQUEST_TIMEOUT = 120

# Pause between successful requests.
REQUEST_DELAY = 5


# ============================================================
# 4. GENERATE SMALLER BOUNDING BOXES
# ============================================================

def generate_sections():

    sections = []

    lat_step = (NORTH - SOUTH) / ROWS
    lon_step = (EAST - WEST) / COLS

    section_number = 1

    for row in range(ROWS):

        for col in range(COLS):

            south = SOUTH + row * lat_step
            north = SOUTH + (row + 1) * lat_step

            west = WEST + col * lon_step
            east = WEST + (col + 1) * lon_step

            sections.append({
                "id": section_number,
                "south": south,
                "west": west,
                "north": north,
                "east": east
            })

            section_number += 1

    return sections


# ============================================================
# 5. DOWNLOAD ONE SECTION
# ============================================================

def download_section(section):

    bbox = (
        f"{section['south']},"
        f"{section['west']},"
        f"{section['north']},"
        f"{section['east']}"
    )

    query = f"""
    [out:json][timeout:90];
    way["building"]({bbox});
    out meta geom;
    """

    request_data = urllib.parse.urlencode({
        "data": query
    }).encode("utf-8")

    for endpoint in OVERPASS_SERVERS:

        print(f"  Trying: {endpoint}")

        request = urllib.request.Request(
            endpoint,
            data=request_data,
            headers={
                "User-Agent": "AINETRA-Geospatial-Research/0.4.1"
            }
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT
            ) as response:

                result = json.load(response)

            print("  Download successful")

            return result

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            OSError
        ) as error:

            print(
                f"  Server unavailable: {error}"
            )

            # Respect rate limiting; do not immediately
            # switch servers after an HTTP 429 response.
            if (
                isinstance(error, urllib.error.HTTPError)
                and error.code == 429
            ):
                print(
                    "  Rate limited. Stopping this run."
                )
                raise

            time.sleep(5)

    print(
        f"  Section {section['id']} failed "
        "on all configured servers."
    )

    return None


# ============================================================
# 6. CONVERT OSM ELEMENT TO GEOJSON
# ============================================================

def convert_building(element):

    if element.get("type") != "way":
        return None

    geometry = element.get("geometry", [])

    coordinates = [
        [point["lon"], point["lat"]]
        for point in geometry
    ]

    if len(coordinates) < 4:
        return None

    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])

    tags = element.get("tags", {})

    return {
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


# ============================================================
# 7. SAVE GEOJSON
# ============================================================

def save_geojson(
    features,
    output_file,
    completed_sections,
    failed_sections
):

    collection = {
        "type": "FeatureCollection",

        "metadata": {
            "project": "AI NETRA",
            "workstream": "Hyderabad Building Intelligence",
            "dataset_version": "expanded_v1",
            "pilot": "Moosarambagh–Musi River Corridor",
            "source": "OpenStreetMap",
            "license": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
            "retrieved_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "bbox": [WEST, SOUTH, EAST, NORTH],
            "completed_sections": completed_sections,
            "failed_sections": failed_sections,
            "is_complete": len(failed_sections) == 0,
            "building_count": len(features),
            "limitations": [
                "OSM coverage may be incomplete",
                "Only building ways are included",
                "Building multipolygon relations are excluded",
                "OSM tags are not independently verified",
                "Source servers may have different update times"
            ]
        },

        "features": features
    }

    # Write to a temporary file before replacing the
    # destination, avoiding an incomplete JSON output.
    temporary_file = output_file.with_suffix(".tmp")

    temporary_file.write_text(
        json.dumps(collection, indent=2),
        encoding="utf-8"
    )

    temporary_file.replace(output_file)


# ============================================================
# 8. MAIN DOWNLOAD WORKFLOW
# ============================================================

def main():

    print("\nAI NETRA — EXPANDED BUILDING DOWNLOAD")
    print("=" * 55)

    print("Pilot: Moosarambagh–Musi River Corridor")

    sections = generate_sections()

    print(f"Total geographic sections: {len(sections)}")

    buildings_by_id = {}

    completed_sections = []
    failed_sections = []

    for section in sections:

        section_id = section["id"]

        print(
            f"\nDownloading section "
            f"{section_id}/{len(sections)}"
        )

        result = download_section(section)

        if result is None:

            failed_sections.append(section_id)

            continue

        elements = result.get("elements", [])

        section_count = 0

        for element in elements:

            feature = convert_building(element)

            if feature is None:
                continue

            building_id = feature[
                "properties"
            ]["building_id"]

            # Deduplicate OSM building IDs.
            buildings_by_id[building_id] = feature

            section_count += 1

        completed_sections.append(section_id)

        print(
            f"  Building records returned: {section_count}"
        )

        print(
            f"  Unique buildings collected: "
            f"{len(buildings_by_id)}"
        )

        # Preserve successful progress after each section.
        save_geojson(
            list(buildings_by_id.values()),
            PARTIAL_FILE,
            completed_sections,
            failed_sections
        )

        time.sleep(REQUEST_DELAY)

    # ========================================================
    # 9. FINAL OUTPUT
    # ========================================================

    print("\nDOWNLOAD SUMMARY")
    print("=" * 55)

    print(
        f"Unique buildings: {len(buildings_by_id)}"
    )

    print(
        f"Completed sections: {completed_sections}"
    )

    print(
        f"Failed sections: {failed_sections}"
    )

    if failed_sections:

        print(
            "\nSome sections could not be downloaded."
        )

        print(
            f"Partial results saved to: {PARTIAL_FILE}"
        )

        print(
            "The expanded dataset was not marked complete."
        )

    else:

        save_geojson(
            list(buildings_by_id.values()),
            OUTPUT_FILE,
            completed_sections,
            failed_sections
        )

        print("\nEXPANDED DATASET CREATED")

        print(f"Saved to: {OUTPUT_FILE}")

    print("\nOriginal dataset preserved:")

    print(ORIGINAL_FILE)


# ============================================================
# 10. EXECUTION
# ============================================================

if __name__ == "__main__":

    main()