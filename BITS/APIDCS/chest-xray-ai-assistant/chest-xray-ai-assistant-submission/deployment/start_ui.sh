#!/usr/bin/env bash
# Managed by Notebook 9
set -euo pipefail
exec "${PYTHON_EXECUTABLE:-python}" -m streamlit run ui/app.py \
  --server.address "${CHEST_XRAY_UI_HOST:-0.0.0.0}" \
  --server.port "${CHEST_XRAY_UI_PORT:-8501}" \
  --server.maxUploadSize 10 \
  --server.headless true \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
