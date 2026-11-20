"""
AI NETRA — Hyderabad Building Intelligence
Workstream: GEO-001
Version: 0.6.0

Capabilities:
- 11,659 OSM building polygons
- STRtree spatial indexing
- Exact point-in-polygon identification
- Nearby building search within 100 metres
- Google Open Buildings 2.5D height estimates
- Height quality classification
- OSM-derived building footprint areas
- Source provenance and verification metadata

Dependencies:
- Python 3.11
- Shapely 2.x

No Pandas, GeoPandas or PyProj required.
"""

import csv
import json
import math

from pathlib import Path

from shapely.geometry import Point, shape, mapping, box
from shapely.ops import transform
from shapely.strtree import STRtree


# ============================================================
# 1. CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"

CATALOG_FILE = (
    DATA_DIR / "ai_netra_building_catalog_v1.geojson"
)

AREA_FILE = (
    DATA_DIR / "ai_netra_building_areas_v1.csv"
)

NEARBY_SEARCH_RADIUS_M = 100

MAX_NEARBY_CANDIDATES = 5

EARTH_RADIUS_M = 6371008.8


# ============================================================
# 2. LOAD BUILDING CATALOG
# ============================================================

with open(
    CATALOG_FILE,
    "r",
    encoding="utf-8"
) as file:

    catalog = json.load(file)


buildings = []
geometries = []


for feature in catalog.get("features", []):

    geometry = shape(feature["geometry"])

    if geometry.is_empty or not geometry.is_valid:
        continue

    buildings.append({
        "properties": feature["properties"],
        "geometry": geometry
    })

    geometries.append(geometry)


spatial_index = STRtree(geometries)

print(f"Loaded {len(buildings)} building polygons")

print("Spatial index initialized successfully")


# ============================================================
# 3. LOAD BUILDING FOOTPRINT AREAS
# ============================================================

area_lookup = {}


if AREA_FILE.exists():

    with open(
        AREA_FILE,
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            building_id = row.get("building_id")

            raw_area = row.get("footprint_area_m2")

            if not building_id or not raw_area:
                continue

            try:

                area = float(raw_area)

                if not math.isfinite(area) or area <= 0:
                    continue

                area_lookup[building_id] = {
                    "footprint_area_m2": area,
                    "area_source": row.get(
                        "area_source",
                        "OpenStreetMap"
                    ),
                    "area_method": row.get(
                        "area_method",
                        "local_equirectangular_projection"
                    ),
                    "area_verification": row.get(
                        "verification_status",
                        "geometry_derived_unverified"
                    )
                }

            except (ValueError, TypeError):
                continue

    print(
        f"Loaded {len(area_lookup)} "
        "building footprint areas"
    )

else:

    print(
        "Warning: Building area CSV not found."
    )


# ============================================================
# 4. LOCAL COORDINATE TRANSFORMATION
# ============================================================

def project_to_local_metres(
    geometry,
    reference_latitude,
    reference_longitude
):
    """
    Approximate WGS84 geographic coordinates in metres.

    Suitable for short-distance nearby-building searches.

    Not intended for authoritative surveying.
    """

    reference_lat_rad = math.radians(
        reference_latitude
    )

    reference_lon_rad = math.radians(
        reference_longitude
    )

    def converter(lon, lat, z=None):

        x = (
            EARTH_RADIUS_M
            * (math.radians(lon) - reference_lon_rad)
            * math.cos(reference_lat_rad)
        )

        y = (
            EARTH_RADIUS_M
            * (math.radians(lat) - reference_lat_rad)
        )

        if z is not None:
            return x, y, z

        return x, y

    return transform(converter, geometry)


# ============================================================
# 5. BUILD EXACT-MATCH RESPONSE
# ============================================================

def build_exact_response(
    building,
    latitude,
    longitude
):

    properties = building["properties"]

    geometry = building["geometry"]

    building_id = properties.get("building_id")

    estimated_height = properties.get(
        "estimated_height_m"
    )

    height_quality = properties.get(
        "height_quality_flag",
        "unavailable"
    )

    area_record = area_lookup.get(
        building_id,
        {}
    )

    footprint_area = area_record.get(
        "footprint_area_m2"
    )

    # --------------------------------------------------------
    # HEIGHT EVIDENCE
    # --------------------------------------------------------

    height_evidence = {

        "value": estimated_height,

        "unit": "metres",

        "source": properties.get(
            "height_source"
        ),

        "dataset_year": properties.get(
            "height_dataset_year"
        ),

        "measurement_type": properties.get(
            "height_measurement_type"
        ),

        "verification_status": properties.get(
            "height_verification"
        ),

        "sampling_method": properties.get(
            "height_sampling_method"
        ),

        "quality_flag": height_quality,

        "confidence": None
    }

    # --------------------------------------------------------
    # FOOTPRINT AREA EVIDENCE
    # --------------------------------------------------------

    area_evidence = {

        "value": footprint_area,

        "unit": "square_metres",

        "source": area_record.get(
            "area_source"
        ),

        "measurement_type": (
            "geometry_derived"
            if footprint_area is not None
            else "unknown"
        ),

        "verification_status": area_record.get(
            "area_verification",
            "unavailable"
        ),

        "calculation_method": area_record.get(
            "area_method"
        ),

        "confidence": None
    }

    # --------------------------------------------------------
    # COMPLETE BUILDING RESPONSE
    # --------------------------------------------------------

    return {

        "match_type": "exact",

        # Building identity
        "building_id": building_id,

        "latitude": latitude,

        "longitude": longitude,

        # OpenStreetMap attributes
        "building_type": properties.get(
            "building_type"
        ),

        "building_levels": properties.get(
            "building_levels"
        ),

        "height": properties.get(
            "height"
        ),

        "construction_date": properties.get(
            "construction_date"
        ),

        # Original OSM provenance
        "source": properties.get(
            "source",
            "OpenStreetMap"
        ),

        "source_timestamp": properties.get(
            "source_timestamp"
        ),

        # Google height
        "estimated_height_m": estimated_height,

        "height_estimate_source": (
            properties.get("height_source")
            if estimated_height is not None
            else None
        ),

        "height_estimate_year": (
            properties.get("height_dataset_year")
            if estimated_height is not None
            else None
        ),

        "height_verification": (
            "Model-estimated; not field-verified"
            if estimated_height is not None
            else "Unavailable"
        ),

        "height_sampling_method": (
            "Representative point"
            if estimated_height is not None
            else None
        ),

        "height_quality_flag": height_quality,

        # Building footprint area
        "footprint_area_m2": footprint_area,

        "area_source": area_record.get(
            "area_source"
        ),

        "area_method": area_record.get(
            "area_method"
        ),

        "area_verification": area_record.get(
            "area_verification"
        ),

        # Attribute evidence
        "attribute_evidence": {

            "estimated_height": height_evidence,

            "footprint_area": area_evidence
        },

        # Geometry
        "geometry": mapping(geometry),

        # Nearby candidates
        "nearby_candidates": []
    }


# ============================================================
# 6. NEARBY BUILDING SEARCH
# ============================================================

def find_nearby_buildings(
    latitude,
    longitude
):

    clicked_point = Point(
        longitude,
        latitude
    )

    latitude_delta = math.degrees(
        NEARBY_SEARCH_RADIUS_M / EARTH_RADIUS_M
    )

    longitude_delta = latitude_delta / max(
        math.cos(math.radians(latitude)),
        0.01
    )

    search_envelope = box(
        longitude - longitude_delta,
        latitude - latitude_delta,
        longitude + longitude_delta,
        latitude + latitude_delta
    )

    candidate_indices = spatial_index.query(
        search_envelope
    )

    projected_point = project_to_local_metres(
        clicked_point,
        latitude,
        longitude
    )

    candidates = []

    for index in candidate_indices:

        building = buildings[int(index)]

        properties = building["properties"]

        geometry = building["geometry"]

        projected_geometry = project_to_local_metres(
            geometry,
            latitude,
            longitude
        )

        distance_m = projected_point.distance(
            projected_geometry
        )

        if distance_m > NEARBY_SEARCH_RADIUS_M:
            continue

        building_id = properties.get(
            "building_id"
        )

        area_record = area_lookup.get(
            building_id,
            {}
        )

        candidates.append({

            "building_id": building_id,

            "distance_m": round(
                distance_m,
                2
            ),

            "building_type": properties.get(
                "building_type"
            ),

            "estimated_height_m": properties.get(
                "estimated_height_m"
            ),

            "height_quality_flag": properties.get(
                "height_quality_flag"
            ),

            "footprint_area_m2": area_record.get(
                "footprint_area_m2"
            ),

            "area_source": area_record.get(
                "area_source"
            ),

            "area_verification": area_record.get(
                "area_verification"
            ),

            "source": properties.get(
                "source",
                "OpenStreetMap"
            ),

            "geometry": mapping(geometry)
        })

    candidates.sort(
        key=lambda item: (
            item["distance_m"],
            item["building_id"] or ""
        )
    )

    return candidates[:MAX_NEARBY_CANDIDATES]


# ============================================================
# 7. MAIN BUILDING IDENTIFICATION
# ============================================================

def identify_building(
    latitude,
    longitude
):

    if not (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):

        raise ValueError(
            "Invalid latitude or longitude"
        )

    clicked_point = Point(
        longitude,
        latitude
    )

    candidate_indices = spatial_index.query(
        clicked_point
    )

    matches = []

    for index in candidate_indices:

        building = buildings[int(index)]

        if building["geometry"].covers(
            clicked_point
        ):

            matches.append(building)

    # --------------------------------------------------------
    # EXACT MATCH
    # --------------------------------------------------------

    if matches:

        matches.sort(
            key=lambda building: (
                building["geometry"].area,
                building["properties"].get(
                    "building_id"
                ) or ""
            )
        )

        return build_exact_response(
            matches[0],
            latitude,
            longitude
        )

    # --------------------------------------------------------
    # NO EXACT MATCH
    # --------------------------------------------------------

    nearby = find_nearby_buildings(
        latitude,
        longitude
    )

    return {

        "match_type": "none",

        "message": (
            "No exact building polygon contains this "
            "location. Nearby mapped buildings are listed."
        ),

        "latitude": latitude,

        "longitude": longitude,

        "search_radius_m": NEARBY_SEARCH_RADIUS_M,

        "nearby_count": len(nearby),

        "nearby_candidates": nearby,

        "distance_method": (
            "Approximate local metric projection"
        )
    }


# ============================================================
# 8. LOCAL VALIDATION
# ============================================================

if __name__ == "__main__":

    print("\nAI NETRA — BUILDING QUERY ENGINE")
    print("=" * 55)

    print(
        f"Buildings loaded: {len(buildings)}"
    )

    print(
        f"Footprint areas loaded: {len(area_lookup)}"
    )

    if not buildings:

        raise SystemExit(
            "No buildings available for testing"
        )

    # Use a known building polygon.
    sample_building = buildings[0]

    sample_point = (
        sample_building["geometry"]
        .representative_point()
    )

    result = identify_building(
        sample_point.y,
        sample_point.x
    )

    print("\nEXACT BUILDING MATCH")
    print("-" * 55)

    print(
        "Match type:",
        result.get("match_type")
    )

    print(
        "Building ID:",
        result.get("building_id")
    )

    print(
        "Estimated height:",
        result.get("estimated_height_m"),
        "m"
    )

    print(
        "Height quality:",
        result.get("height_quality_flag")
    )

    print(
        "Footprint area:",
        result.get("footprint_area_m2"),
        "m²"
    )

    print(
        "Area source:",
        result.get("area_source")
    )

    print(
        "Area verification:",
        result.get("area_verification")
    )

    print("\nVALIDATION COMPLETED")