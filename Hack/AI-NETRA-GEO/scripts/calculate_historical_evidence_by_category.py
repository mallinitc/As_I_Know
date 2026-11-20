import csv
import json
import math
from pathlib import Path

from shapely.geometry import shape, box
from shapely.ops import unary_union

# ============================================================
# AI NETRA — STEP 9.4
# Category-Specific Historical Building Evidence
#
# Category A: Generic flood-affected areas
# Category B: Named affected localities
#
# No building inundation is confirmed.
# ============================================================

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BUILDINGS_FILE = DATA / "ai_netra_building_catalog_v1.geojson"

FLOOD_FILE = DATA / "ai_netra_historical_flood_polygons_pilot_v1.geojson"

OUTPUT_FILE = DATA / "ai_netra_historical_evidence_by_category_v1.csv"

PILOT = box(78.50, 17.36, 78.53, 17.38)

GENERIC_INDICES = {
    6125, 6137, 6207, 6218,
    6221, 6237, 6358
}

LOCALITY_INDICES = {13310, 13314}

# Approximate local metric conversion
R = 6371008.8
LAT0 = 17.37
COS_LAT = math.cos(math.radians(LAT0))


def area_m2(geometry):
    # Constant-scale local approximation.
    return (
        geometry.area
        * (math.pi / 180 * R) ** 2
        * COS_LAT
    )


def load_features(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)["features"]


buildings = load_features(BUILDINGS_FILE)
historical = load_features(FLOOD_FILE)

generic_geometries = []
locality_geometries = []

for feature in historical:
    index = feature["properties"]["source_polygon_index"]
    geometry = shape(feature["geometry"])

    if not geometry.is_valid:
        raise ValueError(f"Invalid geometry: {index}")

    clipped = geometry.intersection(PILOT)

    if clipped.is_empty:
        continue

    if index in GENERIC_INDICES:
        generic_geometries.append(clipped)

    elif index in LOCALITY_INDICES:
        locality_geometries.append(clipped)

    else:
        raise ValueError(f"Unclassified polygon: {index}")

generic_union = unary_union(generic_geometries)
locality_union = unary_union(locality_geometries)

rows = []

counts = {
    "no_overlap": 0,
    "generic_only": 0,
    "locality_only": 0,
    "both": 0,
}

for index, feature in enumerate(buildings, start=1):
    properties = feature.get("properties", {})

    building_id = (
        properties.get("building_id")
        or feature.get("id")
        or f"building-{index}"
    )

    building = shape(feature["geometry"])

    if not building.is_valid or building.is_empty:
        raise ValueError(f"Invalid building: {building_id}")

    clipped = building.intersection(PILOT)

    if clipped.is_empty or clipped.area <= 0:
        raise ValueError(
            f"Building has no positive pilot area: {building_id}"
        )

    building_area = area_m2(clipped)

    generic_area = area_m2(
        clipped.intersection(generic_union)
    )

    locality_area = area_m2(
        clipped.intersection(locality_union)
    )

    generic_pct = min(
        100.0,
        generic_area / building_area * 100
    )

    locality_pct = min(
        100.0,
        locality_area / building_area * 100
    )

    has_generic = generic_area > 0
    has_locality = locality_area > 0

    if has_generic and has_locality:
        category = "both"
    elif has_generic:
        category = "generic_only"
    elif has_locality:
        category = "locality_only"
    else:
        category = "no_overlap"

    counts[category] += 1

    rows.append({
        "building_id": building_id,
        "generic_flood_area_overlap_pct": round(generic_pct, 4),
        "named_locality_overlap_pct": round(locality_pct, 4),
        "generic_flood_area_overlap_m2": round(generic_area, 4),
        "named_locality_overlap_m2": round(locality_area, 4),
        "historical_evidence_category": category,
        "evidence_source": "Hyderabad Floods 2020 SpatialMap",
        "verification_status": "geometric_overlap_only",
        "building_inundation_status": "not_established"
    })


if len(rows) != 11659:
    raise RuntimeError(
        f"Expected 11659 buildings, obtained {len(rows)}"
    )

if counts != {
    "no_overlap": 7008,
    "generic_only": 0,
    "locality_only": 4647,
    "both": 4,
}:
    raise RuntimeError(
        f"Category totals differ from Step 9.2: {counts}"
    )

with OUTPUT_FILE.open(
    "w",
    newline="",
    encoding="utf-8"
) as file:
    writer = csv.DictWriter(
        file,
        fieldnames=list(rows[0].keys())
    )
    writer.writeheader()
    writer.writerows(rows)


print("\n=== AI NETRA — STEP 9.4 ===")

print("Buildings processed:", len(rows))
print("Generic flood polygons:", len(generic_geometries))
print("Named locality polygons:", len(locality_geometries))

print("\n=== BUILDING CLASSIFICATIONS ===")

for category, count in counts.items():
    print(f"{category}: {count}")

print("\n=== VALIDATION ===")
print("Category reconciliation: PASS")

print("\nOutput:", OUTPUT_FILE)
print("Output size:", OUTPUT_FILE.stat().st_size, "bytes")

print("\nOriginal datasets unchanged.")
print("Building inundation remains unverified.")
