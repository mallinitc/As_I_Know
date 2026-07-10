from pathlib import Path
import json

import pandas as pd
import matplotlib.pyplot as plt

from prefect import flow, task
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report
import joblib


BASE_DIR = Path(r"D:\BITSP\Sem3\API_CDS\Assignment1")
PROCESSED_FILE = BASE_DIR / "data" / "processed" / "microservice_rca_labeled_metrics.csv"
OUTPUTS_DIR = BASE_DIR / "outputs"
CHARTS_DIR = OUTPUTS_DIR / "charts"
MODELS_DIR = BASE_DIR / "models"


@task
def ingest_data():
    print("Reading processed microservice RCA dataset...")
    df = pd.read_csv(PROCESSED_FILE)
    print(f"Dataset loaded successfully. Shape: {df.shape}")
    return df


@task
def preprocess_data(df):
    print("Starting preprocessing...")

    df = df.copy()

    required_columns = [
        "cpu_usage_system",
        "cpu_usage_total",
        "cpu_usage_user",
        "memory_usage",
        "memory_working_set",
        "rx_bytes",
        "tx_bytes",
        "service",
        "is_anomaly",
        "fault_type",
    ]

    df = df[required_columns]

    print("Missing values before preprocessing:")
    print(df.isnull().sum())

    numeric_cols = [
        "cpu_usage_system",
        "cpu_usage_total",
        "cpu_usage_user",
        "memory_usage",
        "memory_working_set",
        "rx_bytes",
        "tx_bytes",
    ]

    for col in numeric_cols:
        df[col] = df[col].fillna(df[col].median())

    service_encoder = LabelEncoder()
    df["service_encoded"] = service_encoder.fit_transform(df["service"])

    print("Preprocessing completed.")
    print(f"Processed shape: {df.shape}")

    return df


@task
def perform_eda(df):
    print("Generating EDA charts...")

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(7, 4))
    df["fault_type"].value_counts().plot(kind="bar")
    plt.title("Fault Type Distribution")
    plt.xlabel("Fault Type")
    plt.ylabel("Number of Records")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "pipeline_fault_type_distribution.png", dpi=150)
    plt.close()

    plt.figure(figsize=(7, 4))
    df.groupby("fault_type")["cpu_usage_total"].mean().plot(kind="bar")
    plt.title("Average CPU Usage by Fault Type")
    plt.xlabel("Fault Type")
    plt.ylabel("Average CPU Usage Total")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "pipeline_cpu_by_fault_type.png", dpi=150)
    plt.close()

    print("EDA charts saved successfully.")
    return str(CHARTS_DIR)


@task
def train_models(df):
    print("Starting model training...")

    feature_cols = [
        "cpu_usage_system",
        "cpu_usage_total",
        "cpu_usage_user",
        "memory_usage",
        "memory_working_set",
        "rx_bytes",
        "tx_bytes",
        "service_encoded",
    ]

    X = df[feature_cols]
    y = df["is_anomaly"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.30,
        random_state=42,
        stratify=y
    )

    models = {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=100,
            random_state=42,
            class_weight="balanced"
        )
    }

    trained_models = {}

    for model_name, model in models.items():
        print(f"Training model: {model_name}")
        model.fit(X_train, y_train)
        trained_models[model_name] = model

    print("Model training completed.")

    return trained_models, X_test, y_test


@task
def evaluate_models(model_bundle):
    print("Starting model evaluation...")

    trained_models, X_test, y_test = model_bundle

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    metrics = {}

    for model_name, model in trained_models.items():
        y_pred = model.predict(X_test)

        model_metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, zero_division=0),
            "recall": recall_score(y_test, y_pred, zero_division=0),
            "f1_score": f1_score(y_test, y_pred, zero_division=0),
        }

        metrics[model_name] = model_metrics

        print(f"\nModel: {model_name}")
        print(model_metrics)
        print(classification_report(y_test, y_pred, zero_division=0))

        joblib.dump(model, MODELS_DIR / f"{model_name}.joblib")

    metrics_file = OUTPUTS_DIR / "model_metrics.json"

    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=4)

    print(f"Metrics saved to: {metrics_file}")
    print("Model evaluation completed.")

    return metrics


@flow(name="api-driven-aiops-microservice-rca-pipeline")
def assignment_pipeline():
    df = ingest_data()
    processed_df = preprocess_data(df)
    perform_eda(processed_df)
    model_bundle = train_models(processed_df)
    evaluate_models(model_bundle)


if __name__ == "__main__":
    assignment_pipeline()