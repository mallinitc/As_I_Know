"""
AI NETRA — Musi River Geometry Validation
Workstream: GEO-001
Step: 8.39

Purpose:
- Inspect real OSM Musi River features
- Identify river centreline geometry
- Inspect river water-area relations
- Validate available coordinate sequences
- Determine whether relation geometry needs reconstruction

Dependencies:
- Python 3.11
- Shapely

Read-only operation.
Does not modify existing datasets.
"""

import json

from pathlib import Path
from collections import Counter

from shapely.geometry import LineString, Polygon


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = (
    ROOT
    / "data"
    / "musi_river_osm_raw_v1.json"
)


# ============================================================
# 2. LOAD RIVER DATA
# ============================================================

with open(
    DATA_FILE,
    "r",
    encoding="utf-8"
) as file:

    osm_data = json.load(file)

elements = osm_data.get("elements", [])

print("\nAI NETRA — MUSI RIVER GEOMETRY VALIDATION")
print("=" * 60)

print(f"Total OSM features: {len(elements)}")


# ============================================================
# 3. VALIDATE OSM WAYS
# ============================================================

print("\nRIVER CENTRELINE / WAY VALIDATION")
print("-" * 60)

for element in elements:

    if element.get("type") != "way":
        continue

    osm_id = element.get("id")

    tags = element.get("tags", {})

    points = element.get("geometry", [])

    coordinates = [
        (point["lon"], point["lat"])
        for point in points
    ]

    print(f"\nOSM Way ID: {osm_id}")

    print(f"Name: {tags.get('name')}")

    print(f"Waterway: {tags.get('waterway')}")

    print(f"Coordinate count: {len(coordinates)}")

    if len(coordinates) < 2:

        print("Status: Insufficient line coordinates")

        continue

    line = LineString(coordinates)

    print(f"Geometry type: {line.geom_type}")

    print(f"Geometry valid: {line.is_valid}")

    print(f"Geometry empty: {line.is_empty}")

    print(f"Closed line: {line.is_ring}")

    print(f"Bounds: {line.bounds}")


# ============================================================
# 4. INSPECT WATER-AREA RELATIONS
# ============================================================

print("\nRIVER WATER-AREA RELATION VALIDATION")
print("-" * 60)

for element in elements:

    if element.get("type") != "relation":
        continue

    relation_id = element.get("id")

    tags = element.get("tags", {})

    members = element.get("members", [])

    print(f"\nRelation ID: {relation_id}")

    print(f"Relation type: {tags.get('type')}")

    print(f"Water classification: {tags.get('water')}")

    print(f"Total members: {len(members)}")

    role_counts = Counter(
        member.get("role", "")
        for member in members
    )

    print(f"Member roles: {dict(role_counts)}")

    valid_closed_rings = 0

    open_segments = 0

    invalid_segments = 0

    members_with_geometry = 0

    for member in members:

        geometry = member.get("geometry", [])

        if not geometry:
            continue

        members_with_geometry += 1

        coordinates = [
            (point["lon"], point["lat"])
            for point in geometry
        ]

        if len(coordinates) < 2:

            invalid_segments += 1

            continue

        if (
            len(coordinates) >= 4
            and coordinates[0] == coordinates[-1]
        ):

            polygon = Polygon(coordinates)

            if polygon.is_valid and not polygon.is_empty:

                valid_closed_rings += 1

            else:

                invalid_segments += 1

        else:

            open_segments += 1

    print(
        f"Members with geometry: {members_with_geometry}"
    )

    print(
        f"Individually valid closed rings: {valid_closed_rings}"
    )

    print(
        f"Open geometry segments: {open_segments}"
    )

    print(
        f"Invalid geometry segments: {invalid_segments}"
    )

    if open_segments > 0:

        print(
            "Status: Relation requires polygon "
            "topology reconstruction."
        )

    elif valid_closed_rings > 0:

        print(
            "Status: Closed rings found; "
            "full multipolygon topology still requires validation."
        )

    else:

        print(
            "Status: No independently valid "
            "closed polygon rings identified."
        )


# ============================================================
# 5. SUMMARY
# ============================================================

print("\nVALIDATION SUMMARY")
print("=" * 60)

print(
    "River centrelines and water-area relations "
    "have been inspected."
)

print(
    "No riverbank distances have been calculated."
)

print(
    "No flood-exposure classifications have been assigned."
)

print(
    "\nRIVER GEOMETRY VALIDATION COMPLETED"
)