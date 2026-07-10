# API-driven AIOps Pipeline for Microservice Anomaly Detection and Root Cause Analysis

## Project Overview

This project was developed for the API-driven Cloud Native Solutions assignment.

The project builds an AIOps-style DataOps and MLOps pipeline using a microservice observability dataset. The dataset contains telemetry from a microservice-based Social Network application, including service-level metrics, logs, traces, and fault metadata.

The goal of this project is to detect anomalous microservice behavior and support root cause analysis using an automated API-driven pipeline.

## Business Problem

Modern cloud-native applications are built using many interconnected microservices. When one service experiences CPU load, network delay, or network loss, it can affect the reliability and performance of the complete application.

This project demonstrates how microservice telemetry data can be ingested, processed, analyzed, modeled, scheduled, monitored, and accessed through APIs.

## Dataset

Dataset used: **Traces, Metrics, and Logs for Anomaly Detection and Root Cause Localization in Microservices**.

The raw dataset contains multiple observation windows from a Social Network microservice application. Each observation window includes:

- Service-level metric files
- Log data
- Trace/span data
- Fault metadata files

The fault metadata identifies injected faults such as:

- `cpu_load`
- `network_delay`
- `network_loss`

The final processed dataset used for modeling contains labeled records for anomaly detection and root cause analysis.

## Final Processed Dataset Summary

| Item | Value |
|---|---:|
| Total records | 67,752 |
| Total columns | 14 |
| Observation windows | 4 |
| Microservices | 12 |
| Normal records | 63,792 |
| Anomalous records | 3,960 |
| Fault types | cpu_load, network_delay, network_loss |
| Root-cause services | 11 |

## Project Objective

The objective is to build an automated DataOps and MLOps pipeline for:

1. Ingesting microservice telemetry data
2. Preprocessing and validating the data
3. Performing exploratory data analysis
4. Training machine learning models
5. Evaluating model performance
6. Saving metrics, charts, and model artifacts
7. Scheduling the pipeline every 2 minutes
8. Accessing flow, deployment, run, and work-pool details using APIs

## Pipeline Components

The automated Prefect pipeline contains five main tasks:

1. `ingest_data`
2. `preprocess_data`
3. `perform_eda`
4. `train_models`
5. `evaluate_models`

## Machine Learning Models

Two machine learning models were trained:

1. Logistic Regression
2. Random Forest Classifier

The main target variable is:

```text
is_anomaly
```

This target identifies whether a metric record belongs to a normal period or an injected fault period.

## Evaluation Metrics

The models were evaluated using:

- Accuracy
- Precision
- Recall
- F1-score

## Model Results

| Model | Accuracy | Precision | Recall | F1-score |
|---|---:|---:|---:|---:|
| Logistic Regression | 0.9592 | 0.8795 | 0.3502 | 0.5009 |
| Random Forest | 0.9879 | 0.8793 | 0.9200 | 0.8992 |

Random Forest performed better because it achieved much higher recall and F1-score for anomaly detection.

## DataOps and Scheduling

Prefect was used to automate and monitor the pipeline.

The deployment was scheduled to run every 2 minutes.

Deployment details:

| Item | Value |
|---|---|
| Deployment name | `aiops-rca-every-2-min` |
| Flow name | `api-driven-aiops-microservice-rca-pipeline` |
| Work pool | `local-process-pool` |
| Schedule | Every 2 minutes |

The Prefect dashboard was used to verify:

- Completed flow runs
- Task-level execution
- Pipeline graph
- Logs
- Scheduled runs
- Work-pool execution

## API Access

A separate script retrieves application details using Prefect's built-in API.

The API script retrieves:

- Flow name
- Flow ID
- Deployment name
- Deployment ID
- Deployment status
- Latest completed flow run
- Next scheduled flow run
- Work-pool name
- Work-pool type
- API source URL

API output is saved to:

```text
outputs/prefect_api_details.json
```

## Project Structure

```text
api-driven-aiops-microservice-rca/
│
├── data/
│   └── processed/
│       └── microservice_rca_labeled_metrics.csv
│
├── notebooks/
│   └── 01_dataset_exploration.ipynb
│
├── outputs/
│   ├── charts/
│   │   ├── fault_type_distribution.png
│   │   ├── pipeline_cpu_by_fault_type.png
│   │   └── pipeline_fault_type_distribution.png
│   ├── model_metrics.json
│   └── prefect_api_details.json
│
├── src/
│   ├── assignment_pipeline.py
│   └── prefect_api_access.py
│
├── .gitignore
├── prefect.yaml
├── README.md
└── requirements.txt
```

## Files Not Included

The following files and folders are intentionally excluded from GitHub:

```text
.venv/
data/raw/
data/raw/sn_dataset_extracted/
models/
__pycache__/
.ipynb_checkpoints/
```

The raw dataset is excluded because it is large and can be downloaded separately from the original dataset source.

The model files are excluded because they can be regenerated by running the pipeline.

## How to Run

### 1. Create virtual environment

```bash
python -m venv .venv
```

### 2. Activate virtual environment on Windows

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Run the main pipeline

```bash
python src/assignment_pipeline.py
```

### 5. Start Prefect local server

```bash
prefect server start
```

### 6. Configure Prefect API URL in another terminal

```bash
prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
```

### 7. Start Prefect worker

```bash
prefect worker start --pool local-process-pool
```

### 8. Run API access script

```bash
python src/prefect_api_access.py
```

## Prefect Dashboard

The local Prefect dashboard can be accessed at:

```text
http://127.0.0.1:4200
```

The dashboard shows:

- Flow runs
- Deployment details
- Task logs
- Scheduled runs
- Work-pool details

## Key Outputs

| Output | Location |
|---|---|
| Processed dataset | `data/processed/microservice_rca_labeled_metrics.csv` |
| EDA charts | `outputs/charts/` |
| Model metrics | `outputs/model_metrics.json` |
| API details | `outputs/prefect_api_details.json` |
| Pipeline code | `src/assignment_pipeline.py` |
| API access code | `src/prefect_api_access.py` |
| Dataset exploration notebook | `notebooks/01_dataset_exploration.ipynb` |

## Technologies Used

- Python
- Pandas
- NumPy
- Matplotlib
- Scikit-learn
- Prefect
- Prefect local server
- Prefect built-in API
- HTTPX
- Joblib
- Jupyter Notebook

## Assignment Mapping

| Assignment Requirement | Implementation |
|---|---|
| Business understanding | Microservice anomaly detection and RCA problem |
| Data ingestion | Raw observability dataset processed into labeled metric records |
| Data preprocessing | Missing value check, service encoding, feature preparation |
| EDA | Fault distribution, CPU usage by fault type, network traffic analysis |
| DataOps | Prefect automated pipeline |
| Scheduled workflow | Prefect deployment scheduled every 2 minutes |
| Logging and dashboard | Prefect server dashboard and task logs |
| Model preparation | Logistic Regression and Random Forest |
| Model training | 70/30 train-test split |
| Model evaluation | Accuracy, precision, recall, F1-score |
| MLOps metrics | Metrics saved to JSON and logged in pipeline |
| API access | Prefect API script retrieves flow, deployment, run, and work-pool details |

## Author

Group assignment submission for API-driven Cloud Native Solutions.
