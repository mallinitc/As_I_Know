#!/usr/bin/env bash
# Managed by Notebook 9
set -euo pipefail
exec "${PYTHON_EXECUTABLE:-python}" -m uvicorn api.main:app \
  --host "${CHEST_XRAY_API_HOST:-0.0.0.0}" \
  --port "${CHEST_XRAY_API_PORT:-8000}"
