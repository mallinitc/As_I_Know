"""
AI NETRA — Source Investigation Engine
Version: GEO-001.0.1

Tracks available evidence and missing attributes.

Important:
Only sources actually queried are marked as searched.
"""

from datetime import datetime, timezone


def investigate_building(building_result):
    """
    Generate a source investigation report for a building.

    This version reports evidence already loaded by the backend.
    It does not make live external API requests.
    """

    timestamp = datetime.now(timezone.utc).isoformat()

    investigations = []

    # --------------------------------------------------
    # OpenStreetMap
    # --------------------------------------------------

    osm_attributes = {
        "building_id": building_result.get("building_id"),
        "building_type": building_result.get("building_type"),
        "building_levels": building_result.get("building_levels"),
        "height": building_result.get("height"),
        "construction_date": building_result.get("construction_date"),
    }

    osm_found = {
        key: value
        for key, value in osm_attributes.items()
        if value is not None
    }

    osm_missing = [
        key
        for key, value in osm_attributes.items()
        if value is None
    ]

    investigations.append({
        "source": "OpenStreetMap",
        "status": "completed",
        "access_method": "Local OSM GeoJSON",
        "attributes_found": osm_found,
        "attributes_missing": osm_missing,
        "source_timestamp": building_result.get(
            "source_timestamp"
        ),
        "investigated_at": timestamp
    })

    # --------------------------------------------------
    # Google Open Buildings 2.5D
    # --------------------------------------------------

    google_height = building_result.get(
        "estimated_height_m"
    )

    investigations.append({
        "source": "Google Open Buildings 2.5D",
        "status": (
            "completed"
            if google_height is not None
            else "no_value_available"
        ),
        "access_method": "Local Earth Engine CSV export",
        "attributes_found": (
            {"estimated_height_m": google_height}
            if google_height is not None
            else {}
        ),
        "attributes_missing": (
            []
            if google_height is not None
            else ["estimated_height_m"]
        ),
        "dataset_year": 2023,
        "verification": "model_estimate",
        "investigated_at": timestamp
    })

    # --------------------------------------------------
    # Sources not yet integrated
    # --------------------------------------------------

    pending_sources = [
        "Overture Maps",
        "Google Open Buildings V3",
        "GOBS India",
        "Telangana TG-bPASS",
        "GHMC Building Records",
        "NRSC Flood Data"
    ]

    for source in pending_sources:
        investigations.append({
            "source": source,
            "status": "not_searched",
            "attributes_found": {},
            "attributes_missing": [],
            "investigated_at": None
        })

    return {
        "building_id": building_result.get("building_id"),
        "report_generated_at": timestamp,
        "sources_checked": 2,
        "sources_pending": len(pending_sources),
        "investigations": investigations
    }