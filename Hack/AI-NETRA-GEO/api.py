"""
AI NETRA - Hyderabad Building Intelligence API
Version: 0.10.0
Step: 9.12.5

Capabilities:
- 11,659 OSM building polygons
- Exact building identification
- Nearby building candidates
- Google-estimated building heights
- Building footprint areas
- Musi River proximity
- Government waterlogging-location proximity
- Source investigation and evidence
- Historical mapped-area geometric overlap (legacy combined metric)
- Category-specific generic flood-affected-area and named-locality overlaps
- Historical Sentinel-1 neighbourhood radar-change evidence for 40 sampled buildings
- Read-only unified evidence and rescue-readiness assessment (no prioritization)
- Read-only, explicitly synthetic emergency demonstration endpoint

IMPORTANT:
Geographic proximity and mapped historical flood-area overlap do not establish flooding,
water depth, inundation probability, or flood risk.
Satellite radar-backscatter changes are exploratory historical observations, not flood detections.
"""

import csv
import math
import json
from collections import Counter
from copy import deepcopy

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder

from scripts.query_building import identify_building, buildings
from scripts.source_investigation import investigate_building
from scripts.assess_evidence_completeness import assess_evidence
from scripts.classify_evidence_quality import classify_evidence
from scripts.assess_rescue_readiness import assess_readiness


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"

RIVER_DISTANCE_FILE = (
    DATA_DIR / "ai_netra_musi_distances_v1.csv"
)

WATERLOGGING_DISTANCE_FILE = (
    DATA_DIR / "ai_netra_waterlogging_distances_v1.csv"
)

HISTORICAL_OVERLAP_FILE = (
    DATA_DIR / "ai_netra_historical_flood_building_overlap_v1.csv"
)

HISTORICAL_CATEGORY_FILE = (
    DATA_DIR / "ai_netra_historical_evidence_by_category_v1.csv"
)

SENTINEL1_EVIDENCE_FILE = (
    DATA_DIR / "ai_netra_targeted_radar_evidence_40_v1.csv"
)


# ============================================================
# 2. LOAD MUSI RIVER DISTANCES
# ============================================================

def load_river_distances():

    lookup = {}

    if not RIVER_DISTANCE_FILE.exists():
        print("WARNING: River distance dataset missing.")
        return lookup

    with RIVER_DISTANCE_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            building_id = row.get("building_id")
            raw_distance = row.get("distance_to_musi_water_m")

            if not building_id or not raw_distance:
                continue

            try:
                distance = float(raw_distance)

                if not math.isfinite(distance) or distance < 0:
                    continue

            except (ValueError, TypeError):
                continue

            lookup[building_id] = {
                "distance_to_musi_water_m": distance,
                "river_proximity_band": row.get("proximity_band"),
                "intersects_mapped_water": (
                    row.get(
                        "intersects_mapped_water",
                        ""
                    ).lower() == "true"
                ),
                "river_source": row.get("river_source"),
                "river_geometry_type": row.get(
                    "river_geometry_type"
                ),
                "river_geometry_ids": row.get(
                    "river_geometry_ids"
                ),
                "river_distance_method": row.get(
                    "distance_method"
                ),
                "river_verification": row.get(
                    "verification_status"
                ),
                "flood_risk_assigned": False
            }

    return lookup


# ============================================================
# 3. LOAD GOVERNMENT WATERLOGGING DISTANCES
# ============================================================

def load_waterlogging_distances():

    lookup = {}

    if not WATERLOGGING_DISTANCE_FILE.exists():
        print("WARNING: Waterlogging distance dataset missing.")
        return lookup

    with WATERLOGGING_DISTANCE_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            building_id = row.get("building_id")

            raw_distance = row.get(
                "distance_to_waterlogging_point_m"
            )

            if not building_id or not raw_distance:
                continue

            try:
                distance = float(raw_distance)

                if not math.isfinite(distance) or distance < 0:
                    continue

            except (ValueError, TypeError):
                continue

            lookup[building_id] = {
                "nearest_waterlogging_location": row.get(
                    "nearest_waterlogging_location"
                ),
                "nearest_waterlogging_id": row.get(
                    "nearest_waterlogging_id"
                ),
                "distance_to_waterlogging_point_m": distance,
                "waterlogging_proximity_band": row.get(
                    "proximity_band"
                ),
                "waterlogging_source": row.get("source"),
                "waterlogging_geometry_type": row.get(
                    "geometry_type"
                ),
                "waterlogging_distance_method": row.get(
                    "distance_method"
                ),
                "waterlogging_verification": row.get(
                    "verification_status"
                ),
                "historical_flood_confirmed": False,
                "building_flooding_confirmed": False,
                "flood_risk_assigned": False
            }

    return lookup


# ============================================================
# 3A. LOAD HISTORICAL MAPPED FLOOD-AREA OVERLAP
# ============================================================

def load_historical_overlap():
    """Load geometry-derived overlaps; do not infer verified inundation."""
    lookup = {}
    if not HISTORICAL_OVERLAP_FILE.exists():
        print("WARNING: Historical overlap CSV missing.")
        return lookup

    with HISTORICAL_OVERLAP_FILE.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        for row in csv.DictReader(file):
            building_id = (row.get("building_id") or "").strip()
            if not building_id:
                continue
            try:
                building_area = float(row["building_area_in_pilot_m2"])
                overlap_area = float(row["historical_polygon_overlap_m2"])
                overlap_pct = float(row["historical_polygon_overlap_pct"])
            except (ValueError, TypeError, KeyError):
                continue

            if not all(map(math.isfinite, (
                building_area, overlap_area, overlap_pct
            ))):
                continue
            if (building_area <= 0 or overlap_area < 0 or
                    overlap_area > building_area + 0.01 or
                    not 0 <= overlap_pct <= 100):
                continue
            if building_id in lookup:
                raise ValueError(
                    f"Duplicate historical overlap building ID: {building_id}"
                )

            lookup[building_id] = {
                "building_area_in_pilot_m2": building_area,
                "historical_polygon_overlap_m2": overlap_area,
                "historical_polygon_overlap_pct": overlap_pct,
                "historical_polygon_overlap_category": row.get(
                    "overlap_category"
                ),
                "historical_polygon_has_overlap": overlap_area > 0,
                "historical_polygon_source": row.get("evidence_source") or (
                    "Hyderabad Floods 2020 SpatialMap"
                ),
                "historical_polygon_evidence_status": (
                    "geometric_overlap_only"
                ),
            }
    return lookup


# ============================================================
# 3B. LOAD CATEGORY-SPECIFIC HISTORICAL MAPPED-AREA EVIDENCE
# ============================================================

HISTORICAL_CATEGORY_FIELDS = (
    "generic_flood_area_overlap_pct",
    "named_locality_overlap_pct",
    "generic_flood_area_overlap_m2",
    "named_locality_overlap_m2",
)

VALID_HISTORICAL_CATEGORIES = {
    "no_overlap", "generic_only", "locality_only", "both"
}


def load_historical_categories():
    """Read separately mapped categories, without inferring inundation.

    A missing file is an explicit error, since v0.7.0 depends on its
    presence to avoid presenting combined mapped areas as flood extents.
    """
    if not HISTORICAL_CATEGORY_FILE.is_file():
        raise FileNotFoundError(
            f"Required category evidence file not found: {HISTORICAL_CATEGORY_FILE}"
        )

    lookup = {}
    with HISTORICAL_CATEGORY_FILE.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)
        required = {
            "building_id", "historical_evidence_category",
            *HISTORICAL_CATEGORY_FIELDS,
        }
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Historical category CSV has missing required columns")

        for line_number, row in enumerate(reader, start=2):
            building_id = (row.get("building_id") or "").strip()
            if not building_id or building_id in lookup:
                raise ValueError(
                    f"Historical category CSV has missing/duplicate building ID at line {line_number}"
                )
            try:
                numeric = {field: float(row[field]) for field in HISTORICAL_CATEGORY_FIELDS}
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError(
                    f"Invalid historical category measurements at line {line_number}"
                ) from exc

            for field, value in numeric.items():
                limit = 100 if field.endswith("_pct") else None
                if not math.isfinite(value) or value < 0 or (
                    limit is not None and value > limit
                ):
                    raise ValueError(f"Out-of-range {field} at line {line_number}")

            category = row["historical_evidence_category"]
            if category not in VALID_HISTORICAL_CATEGORIES:
                raise ValueError(f"Unknown historical evidence category at line {line_number}")

            generic = numeric["generic_flood_area_overlap_m2"] > 0
            locality = numeric["named_locality_overlap_m2"] > 0
            expected = (
                "both" if generic and locality else
                "generic_only" if generic else
                "locality_only" if locality else "no_overlap"
            )
            if category != expected:
                raise ValueError(f"Category/area mismatch at line {line_number}")
            lookup[building_id] = {
                **numeric,
                "historical_evidence_category": category,
                "historical_category_source": row.get("evidence_source") or
                    "Hyderabad Floods 2020 SpatialMap",
                "historical_category_verification_status": "geometric_overlap_only",
                "building_inundation_status": "not_established",
            }

    if len(lookup) != len(buildings):
        raise ValueError(
            f"Historical category records ({len(lookup)}) do not match "
            f"loaded building catalog ({len(buildings)})"
        )
    return lookup


def get_historical_category_evidence(building_id):
    record = historical_category_lookup.get(building_id)
    if record is None:
        return {
            "source": "Hyderabad Floods 2020 SpatialMap",
            "source_file": HISTORICAL_CATEGORY_FILE.name,
            "verification_status": "unavailable",
            "historical_evidence_category": "unavailable",
            "building_inundation_status": "not_established",
            "building_flooding_confirmed": False,
            "flood_risk_assigned": False,
        }
    return {
        **record,
        "source": record["historical_category_source"],
        "source_file": HISTORICAL_CATEGORY_FILE.name,
        "source_geometry_file": "ai_netra_historical_flood_polygons_pilot_v1.geojson",
        "historical_period": "October 2020",
        "measurement_type": "building_footprint_intersection_by_polygon_category",
        "verification_status": "geometric_overlap_only_not_verified_inundation",
        "building_flooding_confirmed": False,
        "flood_risk_assigned": False,
        "note": (
            "SymbolID 0: generic flood-affected-area mapping; SymbolID 3: "
            "named affected localities. Both are mapped-area evidence, not "
            "verified floodwater footprints or confirmed building inundation."
        ),
    }


def attach_historical_category_fields(item, building_id):
    """Attach flat fields to exact matches and nearby candidates."""
    record = historical_category_lookup.get(building_id, {})
    for field in HISTORICAL_CATEGORY_FIELDS:
        item[field] = record.get(field)
    item["historical_evidence_category"] = record.get(
        "historical_evidence_category", "unavailable"
    )
    item["building_inundation_status"] = "not_established"
    item["historical_category_verification_status"] = (
        "geometric_overlap_only" if record else "unavailable"
    )
    # Legacy historical_polygon_* fields remain combined mapped-area coverage,
    # including named localities; they are NOT measured floodwater extent.
    item["historical_polygon_overlap_interpretation"] = (
        "combined_mapped_affected_area_coverage_not_inundation"
    )


def get_historical_overlap_evidence(building_id):
    record = historical_overlap_lookup.get(building_id)
    if record is None:
        return {
            "value": None,
            "unit": "percent_of_building_footprint_within_pilot",
            "source": "Hyderabad Floods 2020 SpatialMap",
            "source_file": HISTORICAL_OVERLAP_FILE.name,
            "measurement_type": "geometric_polygon_intersection",
            "verification_status": "unavailable",
            "building_flooding_confirmed": False,
            "historical_flood_confirmed": False,
            "flood_risk_assigned": False,
            "note": "No validated overlap record is available for this building."
        }
    return {
        "value": record["historical_polygon_overlap_pct"],
        "unit": "percent_of_building_footprint_within_pilot",
        "source": record["historical_polygon_source"],
        "source_file": HISTORICAL_OVERLAP_FILE.name,
        "source_geometry_file": (
            "ai_netra_historical_flood_polygons_pilot_v1.geojson"
        ),
        "historical_period": "October 2020",
        "measurement_type": "geometric_polygon_intersection",
        "verification_status": "mapped_area_overlap_not_verified_inundation",
        "building_area_in_pilot_m2": record["building_area_in_pilot_m2"],
        "overlap_area_m2": record["historical_polygon_overlap_m2"],
        "overlap_category": record["historical_polygon_overlap_category"],
        "building_flooding_confirmed": False,
        "historical_flood_confirmed": False,
        "flood_risk_assigned": False,
        "note": (
            "LEGACY COMBINED METRIC: overlap includes both generic mapped "
            "flood-affected areas and broad named-locality polygons. "
            "This is geographic coverage, NOT confirmed inundation. "
            "Use historical_area_by_category for category-specific evidence. "
            "Area percentage uses the building footprint clipped to the pilot."
        ),
    }




# ============================================================
# 3C. HISTORICAL SENTINEL-1 RADAR-CHANGE EVIDENCE
# ============================================================

SENTINEL1_FRACTION_FIELDS = (
    "control_VV_negative_fraction",
    "event_VV_negative_fraction",
    "control_VH_negative_fraction",
    "event_VH_negative_fraction",
)

SENTINEL1_COUNT_FIELDS = (
    "control_VV_sample_count",
    "event_VV_sample_count",
    "control_VH_sample_count",
    "event_VH_sample_count",
)

SENTINEL1_METADATA_FIELDS = (
    "satellite_source",
    "control_start",
    "control_end",
    "event_start",
    "event_end",
    "evidence_type",
    "flood_status",
)

SENTINEL1_GROUPS = {"intersecting", "within_50m", "100_to_200m"}


def load_sentinel1_evidence():
    """Load validated, sampled historical radar evidence; never infer flooding.

    Missing file is permitted so existing building services keep working.
    An existing malformed CSV fails loudly instead of serving misleading data.
    """
    lookup = {}
    if not SENTINEL1_EVIDENCE_FILE.is_file():
        print("WARNING: Sentinel-1 evidence CSV missing; radar evidence unavailable.")
        return lookup

    with SENTINEL1_EVIDENCE_FILE.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)
        required = {
            "building_id", "proximity_group", "distance_m",
            "footprint_area_m2", "neighbourhood_radius_m",
            *SENTINEL1_FRACTION_FIELDS, *SENTINEL1_COUNT_FIELDS,
            *SENTINEL1_METADATA_FIELDS,
        }
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "Sentinel-1 CSV missing columns: " + ", ".join(sorted(missing))
            )

        for line_number, row in enumerate(reader, start=2):
            building_id = (row.get("building_id") or "").strip()
            if not building_id or building_id in lookup:
                raise ValueError(
                    f"Missing/duplicate Sentinel-1 building ID at line {line_number}"
                )
            if row["proximity_group"] not in SENTINEL1_GROUPS:
                raise ValueError(f"Invalid proximity group at line {line_number}")
            try:
                fractions = {
                    key: float(row[key]) for key in SENTINEL1_FRACTION_FIELDS
                }
                counts_raw = {
                    key: float(row[key]) for key in SENTINEL1_COUNT_FIELDS
                }
                counts = {key: int(value) for key, value in counts_raw.items()}
                distance = float(row["distance_m"])
                area = float(row["footprint_area_m2"])
                radius = float(row["neighbourhood_radius_m"])
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(
                    f"Invalid Sentinel-1 numeric value at line {line_number}"
                ) from exc
            if any(
                not math.isfinite(value) or value < 0 or value > 1
                for value in fractions.values()
            ):
                raise ValueError(f"Out-of-range radar fraction at line {line_number}")
            if any(
                not math.isfinite(value) or value < 0 or value != counts[key]
                for key, value in counts_raw.items()
            ):
                raise ValueError(f"Invalid radar count at line {line_number}")
            if (not all(map(math.isfinite, (distance, area, radius)))
                    or distance < 0 or area <= 0 or radius <= 0):
                raise ValueError(f"Invalid spatial measurement at line {line_number}")
            if (row["flood_status"] != "not_verified" or
                    row["evidence_type"] != "historical_radar_change"):
                raise ValueError(f"Unsupported radar evidence status at line {line_number}")

            lookup[building_id] = {
                "proximity_group": row["proximity_group"],
                "distance_m": distance,
                "footprint_area_m2": area,
                "neighbourhood_radius_m": radius,
                **fractions,
                **counts,
                **{key: row.get(key) for key in SENTINEL1_METADATA_FIELDS},
            }

    if len(lookup) != 40:
        raise ValueError(
            f"Expected 40 targeted radar evidence records, got {len(lookup)}"
        )
    known_buildings = set(historical_category_lookup)
    unknown = set(lookup).difference(known_buildings)
    if unknown:
        raise ValueError(
            f"Sentinel-1 evidence refers to {len(unknown)} unknown building IDs"
        )
    return lookup


def get_sentinel1_evidence(building_id):
    """Return explicit availability and provenance for historical SAR evidence."""
    record = sentinel1_lookup.get(building_id)
    base = {
        "availability": "available" if record else "not_available",
        "source": "Sentinel-1A / Google Earth Engine",
        "source_file": SENTINEL1_EVIDENCE_FILE.name,
        "measurement_type": "neighbourhood_radar_backscatter_change_threshold",
        "threshold_db": -3,
        "threshold_direction": "below_minus_3_db",
        "verification_status": "exploratory_not_ground_verified" if record else "unavailable",
        "building_inundation_status": "not_established",
        "building_flooding_confirmed": False,
        "flood_risk_assigned": False,
        "note": (
            "Fractions describe 10 m raster sample locations with decreases "
            "greater than 3 dB in a 50 m building-centred neighbourhood; "
            "samples are not independent, neighbourhoods may overlap, and "
            "radar changes are not verified inundation or flood probabilities. "
            "Data exist only for the 40 targeted experimental buildings."
        ),
    }
    return {**base, **record} if record else base


def attach_sentinel1_fields(item, building_id):
    """Expose an additive, stable evidence shape on matches and candidates."""
    evidence = get_sentinel1_evidence(building_id)
    item["sentinel1_evidence_available"] = evidence["availability"] == "available"
    item["sentinel1_evidence_status"] = evidence["verification_status"]
    item["sentinel1_historical_radar"] = evidence


river_lookup = load_river_distances()

waterlogging_lookup = load_waterlogging_distances()

historical_overlap_lookup = load_historical_overlap()

historical_category_lookup = load_historical_categories()

sentinel1_lookup = load_sentinel1_evidence()

print(f"Loaded {len(historical_category_lookup)} category-specific historical records")

print(f"Loaded {len(sentinel1_lookup)} historical Sentinel-1 radar records")

print(f"Loaded {len(river_lookup)} Musi River distance records")

print(
    f"Loaded {len(waterlogging_lookup)} "
    "waterlogging distance records"
)


# ============================================================
# 4. FASTAPI INITIALIZATION
# ============================================================

app = FastAPI(
    title="AI NETRA - Building Intelligence API",
    description=(
        "Evidence-backed building, river, and government "
        "waterlogging-location and historical mapped-area overlap intelligence "
        "and historical Sentinel-1 radar evidence for Hyderabad; "
        "no verified building inundation."
    ),
    version="0.10.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3100",
        "http://127.0.0.1:3100"
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"]
)


# ============================================================
# 5. HEALTH ENDPOINT
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "healthy",
        "project": "AI NETRA",
        "workstream": "Building Intelligence",
        "buildings_loaded": len(buildings),
        "river_distances_loaded": len(river_lookup),
        "waterlogging_distances_loaded": len(waterlogging_lookup),
        "historical_overlap_records_loaded": len(historical_overlap_lookup),
        "historical_category_records_loaded": len(historical_category_lookup),
        "sentinel1_radar_records_loaded": len(sentinel1_lookup),
        "sentinel1_evidence_file_present": SENTINEL1_EVIDENCE_FILE.is_file(),
        "version": "0.10.0"
    }


# ============================================================
# 6. RIVER DISTANCE EVIDENCE
# ============================================================

def get_river_evidence(building_id):

    record = river_lookup.get(building_id)

    if record is None:
        return {
            "value": None,
            "unit": "metres",
            "source": "OpenStreetMap",
            "measurement_type": "geometry_derived",
            "verification_status": "unavailable",
            "calculation_method": None,
            "confidence": None,
            "flood_risk_assigned": False
        }

    return {
        "value": record["distance_to_musi_water_m"],
        "unit": "metres",
        "source": record["river_source"],
        "measurement_type": "geometry_derived",
        "verification_status": record["river_verification"],
        "calculation_method": record["river_distance_method"],
        "river_geometry_type": record["river_geometry_type"],
        "river_geometry_ids": record["river_geometry_ids"],
        "confidence": None,
        "flood_risk_assigned": False
    }


# ============================================================
# 7. WATERLOGGING DISTANCE EVIDENCE
# ============================================================

def get_waterlogging_evidence(building_id):

    record = waterlogging_lookup.get(building_id)

    if record is None:
        return {
            "value": None,
            "unit": "metres",
            "source": "Telangana Government TGRAC",
            "measurement_type": "geometry_derived",
            "verification_status": "unavailable",
            "confidence": None,
            "historical_flood_confirmed": False,
            "building_flooding_confirmed": False,
            "flood_risk_assigned": False
        }

    return {
        "value": record["distance_to_waterlogging_point_m"],
        "unit": "metres",
        "source": record["waterlogging_source"],
        "measurement_type": "geometry_derived",
        "geometry_type": record["waterlogging_geometry_type"],
        "nearest_location": record[
            "nearest_waterlogging_location"
        ],
        "nearest_location_id": record[
            "nearest_waterlogging_id"
        ],
        "verification_status": record[
            "waterlogging_verification"
        ],
        "calculation_method": record[
            "waterlogging_distance_method"
        ],
        "observation_date": None,
        "water_depth_m": None,
        "confidence": None,
        "historical_flood_confirmed": False,
        "building_flooding_confirmed": False,
        "flood_risk_assigned": False
    }


# ============================================================
# 8. BUILDING QUERY ENDPOINT
# ============================================================

@app.get("/building/query")
def query_building(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180)
):

    try:

        result = identify_building(lat, lon)

        # ----------------------------------------------------
        # EXACT MATCH
        # ----------------------------------------------------

        if result["match_type"] == "exact":

            building_id = result.get("building_id")

            river_record = river_lookup.get(building_id, {})

            waterlogging_record = waterlogging_lookup.get(
                building_id,
                {}
            )

            # Musi River
            result["distance_to_musi_water_m"] = (
                river_record.get("distance_to_musi_water_m")
            )

            result["river_proximity_band"] = (
                river_record.get("river_proximity_band")
            )

            result["intersects_mapped_water"] = (
                river_record.get("intersects_mapped_water")
            )

            result["river_source"] = (
                river_record.get("river_source")
            )

            result["river_distance_method"] = (
                river_record.get("river_distance_method")
            )

            result["river_verification"] = (
                river_record.get("river_verification")
            )

            # Government waterlogging proximity
            result["nearest_waterlogging_location"] = (
                waterlogging_record.get(
                    "nearest_waterlogging_location"
                )
            )

            result["nearest_waterlogging_id"] = (
                waterlogging_record.get(
                    "nearest_waterlogging_id"
                )
            )

            result["distance_to_waterlogging_point_m"] = (
                waterlogging_record.get(
                    "distance_to_waterlogging_point_m"
                )
            )

            result["waterlogging_proximity_band"] = (
                waterlogging_record.get(
                    "waterlogging_proximity_band"
                )
            )

            result["waterlogging_source"] = (
                waterlogging_record.get("waterlogging_source")
            )

            result["waterlogging_distance_method"] = (
                waterlogging_record.get(
                    "waterlogging_distance_method"
                )
            )

            result["waterlogging_verification"] = (
                waterlogging_record.get(
                    "waterlogging_verification"
                )
            )

            # Published historical flood-affected-area geometrical overlap
            overlap_record = historical_overlap_lookup.get(building_id, {})
            result["historical_polygon_overlap_pct"] = overlap_record.get(
                "historical_polygon_overlap_pct"
            )
            result["historical_polygon_overlap_m2"] = overlap_record.get(
                "historical_polygon_overlap_m2"
            )
            result["historical_polygon_overlap_category"] = overlap_record.get(
                "historical_polygon_overlap_category"
            )
            result["historical_polygon_has_overlap"] = overlap_record.get(
                "historical_polygon_has_overlap"
            )
            result["historical_polygon_source"] = overlap_record.get(
                "historical_polygon_source"
            )
            result["historical_polygon_evidence_status"] = (
                "geometric_overlap_only" if overlap_record else "unavailable"
            )

            # Separate generic affected polygons from broad named localities.
            attach_historical_category_fields(result, building_id)

            # Historical radar evidence is availability-gated and not flooding.
            attach_sentinel1_fields(result, building_id)

            # Safety: Do not infer flooding
            result["historical_flood_confirmed"] = False
            result["building_flooding_confirmed"] = False
            result["flood_risk_assigned"] = False

            # Preserve and extend attribute evidence
            result.setdefault("attribute_evidence", {})

            result["attribute_evidence"]["river_distance"] = (
                get_river_evidence(building_id)
            )

            result["attribute_evidence"][
                "waterlogging_distance"
            ] = get_waterlogging_evidence(building_id)

            result["attribute_evidence"][
                "historical_flood_area_overlap"
            ] = get_historical_overlap_evidence(building_id)
            result["attribute_evidence"][
                "historical_area_by_category"
            ] = get_historical_category_evidence(building_id)

            result["attribute_evidence"][
                "sentinel1_historical_radar"
            ] = get_sentinel1_evidence(building_id)

            # Preserve existing investigation
            result["source_investigation"] = (
                investigate_building(result)
            )

        # ----------------------------------------------------
        # NEARBY CANDIDATES
        # ----------------------------------------------------

        elif result["match_type"] == "none":

            for candidate in result.get(
                "nearby_candidates",
                []
            ):

                building_id = candidate.get("building_id")

                river_record = river_lookup.get(
                    building_id,
                    {}
                )

                waterlogging_record = waterlogging_lookup.get(
                    building_id,
                    {}
                )

                candidate["distance_to_musi_water_m"] = (
                    river_record.get(
                        "distance_to_musi_water_m"
                    )
                )

                candidate["river_proximity_band"] = (
                    river_record.get(
                        "river_proximity_band"
                    )
                )

                candidate[
                    "nearest_waterlogging_location"
                ] = waterlogging_record.get(
                    "nearest_waterlogging_location"
                )

                candidate[
                    "distance_to_waterlogging_point_m"
                ] = waterlogging_record.get(
                    "distance_to_waterlogging_point_m"
                )

                candidate[
                    "waterlogging_proximity_band"
                ] = waterlogging_record.get(
                    "waterlogging_proximity_band"
                )

                overlap_record = historical_overlap_lookup.get(building_id, {})
                candidate["historical_polygon_overlap_pct"] = (
                    overlap_record.get("historical_polygon_overlap_pct")
                )
                candidate["historical_polygon_overlap_category"] = (
                    overlap_record.get("historical_polygon_overlap_category")
                )
                candidate["historical_polygon_has_overlap"] = (
                    overlap_record.get("historical_polygon_has_overlap")
                )
                candidate["historical_polygon_evidence_status"] = (
                    "geometric_overlap_only" if overlap_record else "unavailable"
                )
                attach_historical_category_fields(candidate, building_id)
                attach_sentinel1_fields(candidate, building_id)
                candidate["building_flooding_confirmed"] = False
                candidate["historical_flood_confirmed"] = False
                candidate["flood_risk_assigned"] = False

        return jsonable_encoder(result)

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail="Building identification failed."
        ) from exc

# ============================================================
# 9. UNIFIED EVIDENCE ASSESSMENT (READ-ONLY, NO RESCUE SCORING)
# ============================================================

RESCUE_CONTRACT_FILE = DATA_DIR / "ai_netra_rescue_evidence_contract_v1.json"


@app.get("/rescue/assessment")
def get_rescue_assessment(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    """Return evidence completeness, provenance and gaps for a selected building.

    Current incident input is intentionally absent. This endpoint never
    calculates rescue urgency, flood probability or automatic dispatch.
    """
    if not RESCUE_CONTRACT_FILE.is_file():
        raise HTTPException(status_code=503, detail="Rescue evidence contract unavailable.")

    # Reuse the existing, validated building-query path to preserve all
    # enrichment logic and its exact-polygon matching behavior.
    building = query_building(lat=lat, lon=lon)
    if building.get("match_type") != "exact":
        raise HTTPException(status_code=404, detail="No exact mapped building at coordinates.")

    try:
        with RESCUE_CONTRACT_FILE.open("r", encoding="utf-8-sig") as handle:
            contract = deepcopy(json.load(handle))

        evidence = contract["evidence"]
        evidence["building"].update({
            "building_id": building.get("building_id"),
            "latitude": lat,
            "longitude": lon,
            "footprint_area_m2": building.get("footprint_area_m2"),
            "estimated_height_m": building.get("estimated_height_m"),
        })

        radar = (building.get("attribute_evidence") or {}).get("sentinel1_historical_radar")
        if not isinstance(radar, dict):
            radar = building.get("sentinel1_historical_radar")
        if not isinstance(radar, dict) or radar.get("availability") != "available":
            radar = None

        evidence["environmental"].update({
            "distance_to_musi_water_m": building.get("distance_to_musi_water_m"),
            "distance_to_waterlogging_point_m": building.get("distance_to_waterlogging_point_m"),
            "historical_evidence_category": building.get("historical_evidence_category"),
            "sentinel1_historical_radar": radar,
        })

        # The template's incident fields remain unpopulated: nothing in
        # historical or building metadata verifies a current emergency.
        completeness = assess_evidence(contract)
        quality = classify_evidence(contract)
        readiness = assess_readiness(contract)
        quality_counts = dict(Counter(
            record["classification"] for record in quality["records"]
        ))

        return jsonable_encoder({
            "project": "AI NETRA",
            "schema_version": "1.0.0",
            "assessment_type": "experimental_evidence_assessment",
            "building_id": building.get("building_id"),
            "building_evidence": evidence["building"],
            "environmental_evidence": evidence["environmental"],
            "incident_evidence": evidence["incident"],
            "evidence_completeness": completeness,
            "evidence_quality": {
                "classifications": quality_counts,
                "records": quality["records"],
            },
            "rescue_readiness": readiness,
            "assessment": {
                "current_flooding_status": "not_established",
                "rescue_priority": "not_assessed",
                "priority_score": None,
                "human_review_required": True,
                "automated_dispatch_authorized": False,
                "explanation": (
                    "Historical geographic and satellite observations are contextual. "
                    "Current incident observations are not provided; rescue urgency "
                    "cannot be inferred from these data alone. Missing values "
                    "must not delay action on credible emergency reports."
                ),
            },
        })
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="Rescue evidence assessment unavailable.") from exc


# ============================================================
# 10. EXPLICITLY SYNTHETIC INCIDENT DEMONSTRATION (READ-ONLY)
# ============================================================

# This fixture is produced by scripts.integrate_demo_incident.
# It contains fictional incident observations. It must NEVER be
# treated as a live report, verified flood observation, or dispatch order.
DEMO_INCIDENT_FILE = DATA_DIR / "ai_netra_integrated_incident_001.json"
DEMO_SCENARIO_ID = "AI_NETRA_DEMO_001"
DEMO_BUILDING_ID = "osm-way-357584220"


@app.get("/rescue/demo-incident")
def get_demo_incident(
    scenario_id: str = Query(..., description="Only AI_NETRA_DEMO_001 is supported"),
):
    """Return a pre-generated synthetic fixture; never accept live incident input."""
    if scenario_id != DEMO_SCENARIO_ID:
        raise HTTPException(status_code=404, detail="Synthetic demo scenario not found.")

    if not DEMO_INCIDENT_FILE.is_file():
        raise HTTPException(status_code=503, detail="Synthetic demo fixture unavailable.")

    try:
        with DEMO_INCIDENT_FILE.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=503, detail="Synthetic demo fixture could not be read."
        ) from exc

    # Fail closed if the fixture has been modified, mismatched, or
    # incorrectly relabeled as verified/current or as an operational action.
    scenario = payload.get("scenario")
    incident = payload.get("synthetic_incident")
    assessment = payload.get("assessment")
    baseline_incident = payload.get("incident_evidence")
    if not all(isinstance(item, dict) for item in (
        scenario, incident, assessment, baseline_incident
    )):
        raise HTTPException(status_code=503, detail="Synthetic demo fixture invalid.")

    triage = incident.get("triage")
    reported_values = incident.get("reported_values")
    indicators = incident.get("reported_indicators")
    disclaimer = payload.get("disclaimer")
    valid = (
        payload.get("building_id") == DEMO_BUILDING_ID
        and payload.get("assessment_type") == "synthetic_incident_evidence_assessment"
        and scenario.get("scenario_id") == DEMO_SCENARIO_ID
        and scenario.get("scenario_type") == "synthetic_training_scenario"
        and scenario.get("synthetic") is True
        and scenario.get("verification_status") == "unverified"
        and isinstance(reported_values, dict)
        and reported_values.get("verification_status") == "unverified"
        and isinstance(triage, dict)
        and isinstance(indicators, list)
        and assessment.get("incident_report_status") == "synthetic_unverified"
        and assessment.get("current_flooding_status") == "not_established"
        and assessment.get("rescue_priority") == "not_assessed"
        and assessment.get("priority_score") is None
        and assessment.get("human_review_required") is True
        and assessment.get("automated_dispatch_authorized") is False
        and triage.get("rescue_priority") == "not_assessed"
        and triage.get("automated_dispatch_authorized") is False
        and baseline_incident.get("estimated_people_stranded") is None
        and baseline_incident.get("observed_water_depth_m") is None
        and baseline_incident.get("observed_flow_velocity_mps") is None
        and isinstance(disclaimer, str)
        and "SYNTHETIC" in disclaimer.upper()
    )
    if not valid:
        raise HTTPException(status_code=503, detail="Synthetic demo fixture failed safety validation.")

    # The original building evidence is a saved snapshot from the fixture.
    # It is not recomputed here. The frontend must label it as a demo.
    return jsonable_encoder(payload)

