
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



---

## Computer Vision - YOLO Person Detection Experiments

AI NETRA includes experimental computer vision work for detecting and tracking people in flood footage.

### Technologies

- Ultralytics YOLO11n and YOLO11s
- OpenCV for video and image processing
- ByteTrack for multi-object tracking
- CLAHE for experimental low-light image enhancement
- Google Colab GPU environment

### Quantitative Evaluation

Metrics were calculated against manually annotated person bounding boxes.
Detection matching used Intersection over Union (IoU) >= 0.50 unless otherwise specified.

| Experiment | Model | Precision | Recall | F1 |
|---|---|---:|---:|---:|
| Night flood, 4s | YOLO11n | 66.67% | 50.00% | 57.14% |
| Night flood, 5s | YOLO11n | 100.00% | 80.00% | 88.89% |
| Night flood, 4s | YOLO11s, conf 0.10 | 100.00% | 100.00% | 100.00% |
| Night flood, 4s and 5s combined | YOLO11s, conf 0.10 | 80.00% | 88.89% | 84.21% |
| Day flood, rotated 2s | YOLO11s, IoU 0.50 | 44.44% | 44.44% | 44.44% |

### Nighttime Combined Evaluation

- Model: YOLO11s
- Confidence threshold: 0.10
- IoU matching threshold: 0.50
- Manually annotated people: 9
- True positives: 8
- False positives: 2
- False negatives: 1
- Precision: 80.00%
- Recall: 88.89%
- F1-score: 84.21%

### Video Tracking

- Model: YOLO11n
- Tracker: ByteTrack
- Frames processed: 596
- Unique tracking IDs observed: 8
- Identity consistency and tracking accuracy were not quantitatively validated.

### Multi-Video Experiments

- Five flood videos were used.
- Twenty-five frames were sampled for additional evaluation.
- YOLO11s produced person detections in 14 sampled frames.
- Complete ground-truth annotation of these frames remains pending.

### Research Notebook

Notebook: computer_vision/01_environment_validation.ipynb

The notebook contains model inference, experimental outputs,
video tracking, image enhancement, manual annotation comparisons,
and quantitative evaluation.

The notebook uses Google Colab and Google Drive paths.
Its external videos, model weights, and annotation files may need
to be supplied separately for complete reproduction.

### Limitations

- Results are from a small experimental evaluation sample.
- Reported precision and recall are not production-wide accuracy.
- Performance varies with lighting, orientation, and occlusion.
- The day-flood test showed substantially weaker performance.
- Person detection is not personal identity recognition.
- Computer vision experiments are not yet integrated into the GEO application.
- No validated real-time victim count or rescue-priority model is claimed.

### Potential Integration

Future integration can combine person detections with building-level
geographic intelligence to support evidence-based rescue assessment.
This integration requires additional validation.
