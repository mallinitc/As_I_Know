from pathlib import Path
import json

import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel


BASE_DIR = Path(r"D:\BITSP\Sem3\API_CDS\Assignment1")

MODEL_PATH = BASE_DIR / "models" / "random_forest.joblib"
MODEL_METRICS_PATH = BASE_DIR / "outputs" / "model_metrics.json"
PREFECT_API_DETAILS_PATH = BASE_DIR / "outputs" / "prefect_api_details.json"
PROCESSED_DATA_PATH = BASE_DIR / "data" / "processed" / "microservice_rca_labeled_metrics.csv"


app = FastAPI(
    title="AIOps Microservice RCA API",
    description="FastAPI service for microservice anomaly detection and project artifact access.",
    version="1.0.0"
)


class AnomalyInput(BaseModel):
    cpu_usage_system: float
    cpu_usage_total: float
    cpu_usage_user: float
    memory_usage: float
    memory_working_set: float
    rx_bytes: float
    tx_bytes: float
    service_encoded: int


def load_json_file(path: Path):
    if not path.exists():
        return {
            "status": "not_found",
            "path": str(path)
        }

    with open(path, "r") as file:
        return json.load(file)


@app.get("/")
def root():
    return {
        "message": "AIOps Microservice RCA API is running.",
        "available_endpoints": [
            "/health",
            "/model-metrics",
            "/prefect-summary",
            "/dataset-summary",
            "/predict-anomaly",
            "/docs"
        ]
    }


@app.get("/health")
def health_check():
    return {
        "status": "running",
        "application": "AIOps Microservice RCA API",
        "model_available": MODEL_PATH.exists(),
        "model_metrics_available": MODEL_METRICS_PATH.exists(),
        "prefect_summary_available": PREFECT_API_DETAILS_PATH.exists(),
        "processed_dataset_available": PROCESSED_DATA_PATH.exists()
    }


@app.get("/model-metrics")
def get_model_metrics():
    return load_json_file(MODEL_METRICS_PATH)


@app.get("/prefect-summary")
def get_prefect_summary():
    return load_json_file(PREFECT_API_DETAILS_PATH)


@app.get("/dataset-summary")
def get_dataset_summary():
    if not PROCESSED_DATA_PATH.exists():
        return {
            "status": "not_found",
            "path": str(PROCESSED_DATA_PATH)
        }

    df = pd.read_csv(PROCESSED_DATA_PATH)

    return {
        "total_records": int(df.shape[0]),
        "total_columns": int(df.shape[1]),
        "microservices": int(df["service"].nunique()),
        "observation_windows": int(df["run_id"].nunique()) if "run_id" in df.columns else None,
        "normal_records": int((df["is_anomaly"] == 0).sum()),
        "anomalous_records": int((df["is_anomaly"] == 1).sum()),
        "fault_type_distribution": df["fault_type"].value_counts().to_dict(),
        "root_cause_service_distribution": df["root_cause_service"].value_counts().to_dict()
        if "root_cause_service" in df.columns
        else {}
    }


@app.post("/predict-anomaly")
def predict_anomaly(input_data: AnomalyInput):
    if not MODEL_PATH.exists():
        return {
            "status": "model_not_found",
            "path": str(MODEL_PATH)
        }

    model = joblib.load(MODEL_PATH)

    feature_order = [
        "cpu_usage_system",
        "cpu_usage_total",
        "cpu_usage_user",
        "memory_usage",
        "memory_working_set",
        "rx_bytes",
        "tx_bytes",
        "service_encoded"
    ]

    input_df = pd.DataFrame([input_data.model_dump()])[feature_order]

    prediction = int(model.predict(input_df)[0])

    if hasattr(model, "predict_proba"):
        probability = float(model.predict_proba(input_df)[0][1])
    else:
        probability = None

    return {
        "prediction": prediction,
        "prediction_label": "anomaly" if prediction == 1 else "normal",
        "anomaly_probability": probability,
        "model_used": "random_forest",
        "input_features": input_data.model_dump()
    }