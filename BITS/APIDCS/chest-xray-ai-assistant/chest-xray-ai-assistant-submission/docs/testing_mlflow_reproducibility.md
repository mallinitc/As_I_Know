<!-- Managed by Notebook 9 -->
# Testing, MLflow, and Reproducibility

## Reusable tests

```bash
cd /home/jovyan/chest-xray-ai-assistant
python -m pytest tests/api -q
```

Notebook 8 additionally persists focused HTTP-client and Streamlit state/component evidence. Pytest process exit code `0` is authoritative; do not compare executed cases with raw `test_...` function counts because parameterization changes case counts.

## Post-deployment validation

```bash
python deployment/validate_services.py
```

This checks FastAPI health, twelve OpenAPI paths, Streamlit health, and Streamlit root HTML through HTTP.

## MLflow

```bash
export MLFLOW_TRACKING_URI=file:///home/jovyan/apicdsa2-datavol-1/chest-xray-ai-assistant-data/mlflow
mlflow ui --host 0.0.0.0 --port 5000
```

The tracking store contains model, explainability, language, FastAPI, Streamlit, and final packaging lineage. MLflow may emit a non-blocking `pkg_resources` deprecation warning; do not change the validated environment solely for that warning.

## Evidence locations

- API readiness: `/home/jovyan/apicdsa2-datavol-1/chest-xray-ai-assistant-data/outputs/api/api_integration_readiness.json`
- API registry: `/home/jovyan/apicdsa2-datavol-1/chest-xray-ai-assistant-data/outputs/api/api_artifact_registry.json`
- Streamlit readiness: `/home/jovyan/apicdsa2-datavol-1/chest-xray-ai-assistant-data/outputs/ui/streamlit_interface_integration_readiness.json`
- UI registry: `/home/jovyan/apicdsa2-datavol-1/chest-xray-ai-assistant-data/outputs/ui/ui_artifact_registry.json`
- Packaging evidence: `/home/jovyan/apicdsa2-datavol-1/chest-xray-ai-assistant-data/outputs/packaging`

## Reproduction order

1. Provision Python 3.11 and the validated CUDA 12.1 GPU runtime.
2. Restore the solution repository and persistent data-volume hierarchy.
3. Install the pinned dependency contract.
4. Verify checksums and readiness artifacts from Notebooks 1–8.
5. Build the API and UI images without embedding the persistent data volume.
6. Mount the existing data volume and start FastAPI before Streamlit.
7. Run the post-deployment validator and reusable API tests.
8. Review the educational limitation and demonstration evidence.

Do not retrain models, regenerate datasets, recalculate frozen thresholds, or redownload model artifacts as part of packaging reproduction.
