"""
AI NETRA — Musi River Geometry Reconstruction
Workstream: GEO-001
Step: 8.40
Version: 1.0

Purpose:
- Reconstruct OSM river multipolygon relations
- Preserve outer boundaries and inner holes
- Validate polygon topology
- Preserve original OSM source identifiers
- Export valid water-area polygons as GeoJSON

Dependencies:
- Python 3.11
- Shapely 2.x

Important:
- No original datasets are modified.
- Invalid or ambiguous relations are rejected.
- Water polygons are not historical flood boundaries.
"""

import json

from pathlib import Path
from datetime import datetime, timezone

from shapely.geometry import (
    Polygon,
    mapping,
)

from shapely.ops import unary_union
from shapely.validation import explain_validity


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"

INPUT_FILE = (
    DATA_DIR / "musi_river_osm_raw_v1.json"
)

OUTPUT_FILE = (
    DATA_DIR / "musi_river_water_polygons_v1.geojson"
)

REPORT_FILE = (
    DATA_DIR / "musi_river_geometry_validation_v1.json"
)


# ============================================================
# 2. LOAD SOURCE DATA
# ============================================================

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8"
) as file:

    osm_data = json.load(file)

elements = osm_data.get("elements", [])

print("\nAI NETRA — MUSI RIVER POLYGON RECONSTRUCTION")
print("=" * 60)

print(f"Total source features: {len(elements)}")


# ============================================================
# 3. GEOMETRY HELPERS
# ============================================================

def get_coordinates(member):
    """
    Convert Overpass member geometry into
    longitude/latitude coordinate pairs.
    """

    geometry = member.get("geometry", [])

    return [
        (
            point["lon"],
            point["lat"]
        )
        for point in geometry
    ]


def build_ring(member):
    """
    Validate a closed polygon ring.

    Returns a Shapely Polygon or raises ValueError.
    """

    coordinates = get_coordinates(member)

    if len(coordinates) < 4:
        raise ValueError(
            "Insufficient coordinates for polygon ring"
        )

    if coordinates[0] != coordinates[-1]:
        raise ValueError(
            "Polygon ring is not closed"
        )

    polygon = Polygon(coordinates)

    if polygon.is_empty:
        raise ValueError(
            "Polygon ring is empty"
        )

    if not polygon.is_valid:
        raise ValueError(
            explain_validity(polygon)
        )

    if polygon.area <= 0:
        raise ValueError(
            "Polygon ring has zero area"
        )

    return polygon


# ============================================================
# 4. RECONSTRUCT RELATION
# ============================================================

def reconstruct_relation(relation):
    """
    Reconstruct an OSM water multipolygon.

    Supports individually closed outer and inner rings.

    Rejects:
    - Open member geometries
    - Unsupported member roles
    - Inner rings outside outer polygons
    - Invalid resulting geometry

    Does not attempt automatic geometry repair.
    """

    relation_id = relation["id"]

    members = relation.get("members", [])

    outer_polygons = []
    inner_polygons = []

    for member in members:

        role = member.get("role")

        if member.get("type") != "way":
            raise ValueError(
                f"Unsupported member type: "
                f"{member.get('type')}"
            )

        if role not in ("outer", "inner"):
            raise ValueError(
                f"Unsupported member role: {role}"
            )

        polygon = build_ring(member)

        if role == "outer":
            outer_polygons.append(polygon)

        else:
            inner_polygons.append(polygon)

    if not outer_polygons:
        raise ValueError(
            "Relation has no outer boundary"
        )

    # --------------------------------------------------------
    # Assign inner rings to their containing outer polygon.
    # --------------------------------------------------------

    reconstructed = []

    assigned_inner_indices = set()

    for outer in outer_polygons:

        holes = []

        for index, inner in enumerate(inner_polygons):

            # Require the inner ring to lie strictly
            # within the outer polygon.
            if outer.contains(inner):

                holes.append(
                    list(inner.exterior.coords)
                )

                assigned_inner_indices.add(index)

        polygon = Polygon(
            outer.exterior.coords,
            holes=holes
        )

        if not polygon.is_valid:
            raise ValueError(
                "Reconstructed polygon invalid: "
                + explain_validity(polygon)
            )

        reconstructed.append(polygon)

    # Every inner ring must have been assigned.
    if len(assigned_inner_indices) != len(inner_polygons):

        raise ValueError(
            "One or more inner rings could not "
            "be assigned to an outer polygon"
        )

    # Combine multiple outer polygons if required.
    if len(reconstructed) == 1:

        result = reconstructed[0]

    else:

        result = unary_union(reconstructed)

    if result.is_empty or not result.is_valid:

        raise ValueError(
            "Final multipolygon geometry invalid"
        )

    return result, len(outer_polygons), len(inner_polygons)


# ============================================================
# 5. PROCESS WATER-AREA RELATIONS
# ============================================================

features = []

validation_results = []

successful = 0
failed = 0


for element in elements:

    if element.get("type") != "relation":
        continue

    relation_id = element["id"]

    tags = element.get("tags", {})

    # Only process the mapped river water relations.
    if not (
        tags.get("type") == "multipolygon"
        and tags.get("natural") == "water"
        and tags.get("water") == "river"
    ):
        continue

    print(f"\nProcessing relation: {relation_id}")

    try:

        geometry, outer_count, inner_count = (
            reconstruct_relation(element)
        )

        print(
            f"  Geometry: {geometry.geom_type}"
        )

        print(
            f"  Outer rings: {outer_count}"
        )

        print(
            f"  Inner rings: {inner_count}"
        )

        print(
            f"  Valid: {geometry.is_valid}"
        )

        print(
            f"  Bounds: {geometry.bounds}"
        )

        print(
            f"  Area in geographic degrees²: "
            f"{geometry.area:.10f}"
        )

        feature = {

            "type": "Feature",

            "properties": {

                "waterbody_id": (
                    f"osm-relation-{relation_id}"
                ),

                "osm_relation_id": relation_id,

                "name": tags.get("name"),

                "classification": "river_water_area",

                "source": "OpenStreetMap",

                "source_timestamp": element.get(
                    "timestamp"
                ),

                "verification_status": (
                    "geometry_validated_not_field_verified"
                ),

                "outer_ring_count": outer_count,

                "inner_ring_count": inner_count
            },

            "geometry": mapping(geometry)
        }

        features.append(feature)

        validation_results.append({

            "relation_id": relation_id,

            "status": "valid",

            "geometry_type": geometry.geom_type,

            "outer_rings": outer_count,

            "inner_rings": inner_count,

            "bounds": list(geometry.bounds)
        })

        successful += 1

    except Exception as error:

        print(
            f"  Reconstruction failed: {error}"
        )

        validation_results.append({

            "relation_id": relation_id,

            "status": "failed",

            "error": str(error)
        })

        failed += 1


# ============================================================
# 6. BUILD OUTPUT DATASET
# ============================================================

collection = {

    "type": "FeatureCollection",

    "metadata": {

        "project": "AI NETRA",

        "workstream": "Hyderabad Building Intelligence",

        "dataset_version": "1.0",

        "source": "OpenStreetMap",

        "license": "ODbL-1.0",

        "attribution": "© OpenStreetMap contributors",

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "water_polygon_count": len(features),

        "successful_relations": successful,

        "failed_relations": failed,

        "coordinate_system": "EPSG:4326",

        "limitations": [

            "River geometry is crowdsourced",

            "Mapped water polygons are not flood boundaries",

            "Water boundaries may not represent current conditions",

            "Riverbank geometry is not field surveyed",

            "Geometry completeness beyond the mapped area is unknown",

            "Distances to these polygons are not flood risk scores"
        ]
    },

    "features": features
}


# ============================================================
# 7. SAVE OUTPUTS
# ============================================================

OUTPUT_FILE.write_text(
    json.dumps(
        collection,
        indent=2
    ),
    encoding="utf-8"
)

report = {

    "project": "AI NETRA",

    "step": "8.40",

    "source_file": INPUT_FILE.name,

    "successful_relations": successful,

    "failed_relations": failed,

    "validation_results": validation_results
}

REPORT_FILE.write_text(
    json.dumps(
        report,
        indent=2
    ),
    encoding="utf-8"
)


# ============================================================
# 8. VALIDATION SUMMARY
# ============================================================

print("\nRECONSTRUCTION SUMMARY")
print("=" * 60)

print(
    f"Successfully reconstructed relations: {successful}"
)

print(
    f"Failed relations: {failed}"
)

print(
    f"Valid water polygon features: {len(features)}"
)

print("\nOUTPUT FILES")
print("-" * 60)

print(OUTPUT_FILE)

print(REPORT_FILE)

if failed:
    print(
        "\nWARNING: Some relations failed reconstruction. "
        "Do not treat this dataset as complete."
    )

print("\nRIVER POLYGON RECONSTRUCTION COMPLETED")