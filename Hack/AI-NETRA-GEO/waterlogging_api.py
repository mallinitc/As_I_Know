"""
AI NETRA â€” Government Waterlogging Locations API
Step 8.56

Provides a separate FastAPI application exposing
TGRAC government-mapped waterlogging locations.

Source:
Telangana Government â€” TGRAC ArcGIS

Important:
These are mapped waterlogging locations,
not confirmed building-level inundation boundaries.
"""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


ROOT = Path(__file__).resolve().parent

DATA_FILE = (
    ROOT
    / "data"
    / "tgrac_waterlogging_points_v1.geojson"
)


app = FastAPI(
    title="AI NETRA â€” Waterlogging Intelligence API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3100",
        "http://127.0.0.1:3100",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/waterlogging/locations")
def get_waterlogging_locations():

    if not DATA_FILE.exists():
        return JSONResponse(
            status_code=503,
            content={
                "error": "Waterlogging dataset unavailable"
            },
        )

    with DATA_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        collection = json.load(file)

    return collection


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "service": "AI NETRA Waterlogging API",
        "dataset_available": DATA_FILE.exists(),
    }
