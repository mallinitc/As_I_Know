"""
AI NETRA — Multi-Location Synthetic Incidents
Version: 1.0.0
Step: 9.13.29

Assign three synthetic incidents to distinct mapped buildings.

Uses actual OSM building geometries for locations.
Incident observations remain fictional and unverified.
"""

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import shape


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

BUILDINGS_FILE = DATA_DIR / "ai_netra_building_catalog_v1.geojson"

SOURCE_FILE = (
    DATA_DIR / "ai_netra_multi_incident_comparison_v1.json"
)

OUTPUT_FILE = (
    DATA_DIR / "ai_netra_multi_location_incidents_v1.json"
)

BASE_LAT = 17.37990065
BASE_LON = 78.51797466199042

BASE_BUILDING_ID = "osm-way-357584220"

API_URL = "http://127.0.0.1:8000/building/query"


def distance_m(lat1, lon1, lat2, lon2):
    """Approximate local distance using a spherical Earth."""

    radius = 6371000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )

    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def query_building(lat, lon):

    params = urllib.parse.urlencode({
        "lat": lat,
        "lon": lon
    })

    with urllib.request.urlopen(
        f"{API_URL}?{params}",
        timeout=15
    ) as response:
        return json.load(response)


def load_candidates():

    with BUILDINGS_FILE.open(
        "r",
        encoding="utf-8-sig"
    ) as file:
        catalog = json.load(file)

    candidates = []

    for feature in catalog.get("features", []):

        geometry = feature.get("geometry")

        if not geometry:
            continue

        try:
            polygon = shape(geometry)

            if polygon.is_empty or not polygon.is_valid:
                continue

            point = polygon.representative_point()

            lon = point.x
            lat = point.y

            distance = distance_m(
                BASE_LAT,
                BASE_LON,
                lat,
                lon
            )

            if 300 <= distance <= 3000:
                candidates.append({
                    "latitude": lat,
                    "longitude": lon,
                    "distance_from_base_m": round(distance, 2)
                })

        except (ValueError, TypeError):
            continue

    return candidates


def select_locations(candidates):

    selected = [{
        "building_id": BASE_BUILDING_ID,
        "latitude": BASE_LAT,
        "longitude": BASE_LON,
        "distance_from_base_m": 0.0
    }]

    # Try a nearer building and a more distant building.
    targets = [700, 1800]

    for target in targets:

        ordered = sorted(
            candidates,
            key=lambda item: abs(
                item["distance_from_base_m"] - target
            )
        )

        found = False

        for candidate in ordered[:300]:

            # Ensure geographical separation.
            if any(
                distance_m(
                    candidate["latitude"],
                    candidate["longitude"],
                    previous["latitude"],
                    previous["longitude"]
                ) < 400
                for previous in selected
            ):
                continue

            result = query_building(
                candidate["latitude"],
                candidate["longitude"]
            )

            if result.get("match_type") != "exact":
                continue

            building_id = result.get("building_id")

            if (
                not building_id
                or building_id in {
                    item["building_id"] for item in selected
                }
            ):
                continue

            selected.append({
                **candidate,
                "building_id": building_id
            })

            found = True
            break

        if not found:
            raise RuntimeError(
                f"No valid distinct building found near {target} m"
            )

    return selected


def main():

    with SOURCE_FILE.open(
        "r",
        encoding="utf-8-sig"
    ) as file:
        source = json.load(file)

    incidents = source.get("incidents", [])

    if len(incidents) != 3:
        raise ValueError("Expected exactly three demo incidents")

    if any(
        item.get("synthetic") is not True
        or item.get("verification_status") != "unverified"
        for item in incidents
    ):
        raise ValueError("Only unverified synthetic incidents are supported")

    candidates = load_candidates()

    locations = select_locations(candidates)

    for incident, location in zip(incidents, locations):

        incident["building_id"] = location["building_id"]

        incident["location"] = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "distance_from_demo_building_m": (
                location["distance_from_base_m"]
            ),
            "location_source": "OSM_building_catalog",
            "location_verified_by": "FastAPI_exact_polygon_query"
        }

        incident["synthetic"] = True
        incident["verification_status"] = "unverified"

    source["assessment_type"] = (
        "synthetic_multi_location_incident_comparison"
    )

    source["locations_distinct"] = True
    source["ranking_performed"] = False
    source["automated_dispatch_authorized"] = False

    source["disclaimer"] = (
        "SYNTHETIC DEMONSTRATION ONLY. Building locations "
        "are real mapped geometries, but the reported incidents "
        "and measurements are entirely fictional."
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(source, file, indent=2)

    ids = [
        incident["building_id"]
        for incident in incidents
    ]

    valid = (
        len(set(ids)) == 3
        and all(
            incident["synthetic"] is True
            and incident["verification_status"] == "unverified"
            and incident["rescue_priority"] == "not_assessed"
            for incident in incidents
        )
        and source["automated_dispatch_authorized"] is False
    )

    print("===== AI_NETRA_RESULTS_START =====")

    print("SCENARIOS:", len(incidents))
    print("DISTINCT_BUILDINGS:", len(set(ids)))

    for incident in incidents:

        location = incident["location"]

        print(
            "INCIDENT:",
            incident["scenario_id"],
            "| BUILDING:",
            incident["building_id"],
            "| LAT:",
            round(location["latitude"], 7),
            "| LON:",
            round(location["longitude"], 7)
        )

    print("ALL_SYNTHETIC: True")
    print("RANKING_PERFORMED:", source["ranking_performed"])

    print(
        "AUTOMATED_DISPATCH:",
        source["automated_dispatch_authorized"]
    )

    print("OUTPUT_FILE:", OUTPUT_FILE.name)
    print("VALIDATION:", "PASS" if valid else "FAIL")

    print("===== AI_NETRA_RESULTS_END =====")

    if not valid:
        raise RuntimeError("Multi-location validation failed")


if __name__ == "__main__":
    main()
