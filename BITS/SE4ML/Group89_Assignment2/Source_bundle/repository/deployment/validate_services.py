# Managed by Notebook 9
from __future__ import annotations

import json
import os
import urllib.request

api_url = os.getenv("CHEST_XRAY_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ui_url = os.getenv("CHEST_XRAY_UI_BASE_URL", "http://127.0.0.1:8501").rstrip("/")

def read(url: str) -> tuple[int, str, str]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.status, response.headers.get("content-type", ""), response.read().decode("utf-8")

api_status, _, api_body = read(f"{api_url}/health")
openapi_status, _, openapi_body = read(f"{api_url}/openapi.json")
ui_status, _, ui_health = read(f"{ui_url}/_stcore/health")
ui_root_status, ui_root_type, _ = read(ui_url)
openapi = json.loads(openapi_body)

checks = {
    "fastapi_health": api_status == 200 and json.loads(api_body).get("status") == "success",
    "openapi_paths": openapi_status == 200 and len(openapi.get("paths", {})) == 12,
    "streamlit_health": ui_status == 200 and ui_health.strip().lower() == "ok",
    "streamlit_root": ui_root_status == 200 and "text/html" in ui_root_type.lower(),
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise RuntimeError(f"Deployment health validation failed: {failed}")
print(json.dumps({"status": "pass", "checks": checks}, indent=2))
