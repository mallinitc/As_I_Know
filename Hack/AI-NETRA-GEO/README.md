
$readme = @'
# AI NETRA
## Next-Gen Emergency Triage & Rescue Assistant

**Team:** AI-vengers  
**Hackathon:** CipherCop 2026  
**Track:** AI for Disaster Resilience  
**Pilot Area:** Moosarambagh / Musi River Corridor, Hyderabad

## 1. Project Overview

AI NETRA is a flood-rescue intelligence prototype designed to support
emergency response planning through geographic building intelligence.

The current GEO module integrates building footprints, model-estimated
building heights, river proximity, and government-mapped waterlogging
locations into an interactive map.

The broader project vision includes computer vision-based identification
of stranded individuals and evidence-based rescue prioritization.

## 2. Implemented Features

- Interactive geographic map using Next.js and Leaflet.
- Building identification through map clicks.
- Exact building polygon matching and nearby building identification.
- Building footprint highlighting.
- Estimated building heights from Google Open Buildings 2.5D.
- Approximate building footprint area calculations.
- Distance to mapped Musi River water polygons.
- Distance to government-mapped waterlogging locations.
- Government waterlogging markers and dropdown navigation.
- Source provenance and missing-data indicators.

## 3. Technology Stack

### Backend
- Python 3.11
- FastAPI
- GeoPandas
- Shapely STRtree
- Pandas
- NumPy

### Frontend
- Next.js
- React
- TypeScript
- Leaflet

### Data Sources
- OpenStreetMap building footprints
- Google Open Buildings 2.5D
- OpenStreetMap Musi water polygons
- TGRAC government waterlogging locations

## 4. Architecture

Building and geospatial datasets are processed locally.

Building datasets -> Spatial Index -> FastAPI (8000)
Waterlogging data -> FastAPI (8001)
FastAPI Services -> Next.js / Leaflet UI (3000)

For detailed architecture documentation:

docs/ARCHITECTURE.md

## 5. Installation

Requirements:

- Windows
- Python 3.11
- Node.js and npm

### Install Backend Dependencies

Open PowerShell:

```powershell
cd <extracted-folder>\AI-NETRA-GEO

py -3.11 -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
---

## Standalone Installation and Demonstration

### Installation

Extract the package to any Windows directory.

Requirements:
- Windows PowerShell
- Python 3.11
- Node.js and npm
- Internet access for initial dependency installation

Open PowerShell in the extracted `AI-NETRA-GEO` directory.

Run:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Install-AI-NETRA.ps1"

The installer creates a Python virtual environment and installs the backend
and frontend dependencies.

### Start the Application

Run:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Start-AI-NETRA-PORTABLE.ps1"

The launcher starts:

- Building Intelligence API: http://127.0.0.1:8000
- Waterlogging API: http://127.0.0.1:8001
- Interactive Map: http://127.0.0.1:3000

Keep the service terminals running during the demonstration.

### Configurable API Endpoints

The frontend uses these environment variables:

    NEXT_PUBLIC_BUILDING_API_URL
    NEXT_PUBLIC_WATERLOGGING_API_URL

Default values:

    http://127.0.0.1:8000
    http://127.0.0.1:8001

To override them, copy:

    frontend/.env.example

to:

    frontend/.env.local

Update the endpoint values and restart the frontend.

For a standalone test using alternate backend ports, ensure the backend
CORS configuration also permits the frontend origin.

### Recorded Demonstration

A recorded demonstration of the working AI NETRA GEO prototype is included:

    docs/demo/demo_NETRA.mp4

The recording provides a visual walkthrough of the application.

If installation or runtime issues prevent a live demonstration,
reviewers can use this recording to inspect the implemented interface.

### Implementation Scope

The GEO module provides:

- Interactive building polygon identification
- Model-estimated building height information
- Approximate building footprint areas
- Musi River proximity measurements
- Government-mapped waterlogging locations
- Historical mapped-area overlap evidence
- Historical Sentinel-1 radar evidence where available
- Source provenance and missing-data indicators

The application does not provide validated real-time flood depth,
submergence-time prediction, or automated rescue prioritization.

### Dataset Information

The package includes 62 files within the GEO data directory.

The building catalog contains 11,659 building records.

See the following documentation:

- docs/ARCHITECTURE.md
- docs/DATA_SOURCES.md
- docs/DATA_PIPELINE.md
- docs/KNOWN_LIMITATIONS.md

### Team Integration

This standalone package represents the AI NETRA GEO workstream.

Other project modules can be integrated separately after testing.

The frontend API addresses can be configured without modifying
the active BuildingMap component.


