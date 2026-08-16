<!-- Managed by Notebook 9 -->
# Usage and Deployment

## Prerequisites

- Linux host with Docker Engine and Docker Compose v2.
- NVIDIA driver and NVIDIA Container Toolkit for GPU-backed API deployment.
- At least 4 GiB free on the persistent data volume.
- Completed Notebook 8 readiness artifact at `/home/jovyan/apicdsa2-datavol-1/chest-xray-ai-assistant-data/outputs/ui/streamlit_interface_integration_readiness.json`.
- Persisted models, thresholds, prompt registry, caches, MLflow store, and configuration beneath `/home/jovyan/apicdsa2-datavol-1/chest-xray-ai-assistant-data` and `/home/jovyan/chest-xray-ai-assistant`.

## Configure

```bash
cd /home/jovyan/chest-xray-ai-assistant
cp .env.example .env
# Review CHEST_XRAY_DATA_ROOT and exposed ports before deployment.
```

Do not put credentials, access tokens, patient information, or private image paths in `.env`.

## Independent local launch

Terminal 1:
```bash
./deployment/start_api.sh
```

Terminal 2:
```bash
CHEST_XRAY_API_BASE_URL=http://127.0.0.1:8000 ./deployment/start_ui.sh
```

Validate:
```bash
python deployment/validate_services.py
```

## Docker Compose

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
python deployment/validate_services.py
```

Open `http://127.0.0.1:8501`, upload a PNG or JPEG no larger than 10 MiB, review the educational limitation, and explicitly start complete analysis.

## Stop services

```bash
docker compose down
```

The persistent data volume is a host bind mount and is not removed by `docker compose down`.

## Troubleshooting

- API startup may take longer while frozen models are loaded; retain the configured health-check start period.
- Confirm NVIDIA Container Toolkit availability when the API cannot access CUDA.
- Confirm `CHEST_XRAY_DATA_ROOT` points to the completed persistent data hierarchy.
- Confirm the UI uses `http://api:8000` inside Compose, not `127.0.0.1:8000`.
- Inspect `docker compose logs api` and `docker compose logs ui` without exposing uploaded images or credentials.
