import json
from pathlib import Path

import httpx


PREFECT_API_URL = "http://127.0.0.1:4200/api"

TARGET_FLOW_NAME = "api-driven-aiops-microservice-rca-pipeline"
TARGET_DEPLOYMENT_NAME = "aiops-rca-every-2-min"

BASE_DIR = Path(r"D:\BITSP\Sem3\API_CDS\Assignment1")
OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUT_FILE = OUTPUTS_DIR / "prefect_api_details.json"


def post(endpoint, payload=None):
    url = f"{PREFECT_API_URL}{endpoint}"
    response = httpx.post(url, json=payload or {}, timeout=30)
    response.raise_for_status()
    return response.json()


def main():
    print("Fetching application details from Prefect built-in API...\n")

    flows = post("/flows/filter")

    deployments = post("/deployments/filter")

    completed_flow_runs = post(
        "/flow_runs/filter",
        {
            "flow_runs": {
                "state": {
                    "type": {
                        "any_": ["COMPLETED"]
                    }
                }
            },
            "sort": "END_TIME_DESC",
            "limit": 5
        }
    )

    scheduled_flow_runs = post(
        "/flow_runs/filter",
        {
            "flow_runs": {
                "state": {
                    "type": {
                        "any_": ["SCHEDULED"]
                    }
                }
            },
            "sort": "START_TIME_ASC",
            "limit": 5
        }
    )

    work_pools = post("/work_pools/filter")

    target_flow = next(
        (flow for flow in flows if flow.get("name") == TARGET_FLOW_NAME),
        None
    )

    target_deployment = next(
        (deployment for deployment in deployments if deployment.get("name") == TARGET_DEPLOYMENT_NAME),
        None
    )

    latest_completed_run = completed_flow_runs[0] if completed_flow_runs else None
    next_scheduled_run = scheduled_flow_runs[0] if scheduled_flow_runs else None
    target_work_pool = work_pools[0] if work_pools else None

    api_details = {
        "application_name": "API-driven AIOps Microservice RCA Pipeline",

        "flow_name": target_flow.get("name") if target_flow else None,
        "flow_id": target_flow.get("id") if target_flow else None,

        "deployment_name": target_deployment.get("name") if target_deployment else None,
        "deployment_id": target_deployment.get("id") if target_deployment else None,
        "deployment_status": target_deployment.get("status") if target_deployment else None,

        "latest_completed_flow_run_name": latest_completed_run.get("name") if latest_completed_run else None,
        "latest_completed_flow_run_state": latest_completed_run.get("state", {}).get("type") if latest_completed_run else None,
        "latest_completed_flow_run_start_time": latest_completed_run.get("start_time") if latest_completed_run else None,
        "latest_completed_flow_run_end_time": latest_completed_run.get("end_time") if latest_completed_run else None,

        "next_scheduled_flow_run_name": next_scheduled_run.get("name") if next_scheduled_run else None,
        "next_scheduled_flow_run_state": next_scheduled_run.get("state", {}).get("type") if next_scheduled_run else None,
        "next_scheduled_flow_run_expected_start_time": next_scheduled_run.get("expected_start_time") if next_scheduled_run else None,

        "work_pool_name": target_work_pool.get("name") if target_work_pool else None,
        "work_pool_type": target_work_pool.get("type") if target_work_pool else None,

        "api_source": PREFECT_API_URL,
        "total_completed_flow_runs_checked": len(completed_flow_runs),
        "total_scheduled_flow_runs_checked": len(scheduled_flow_runs)
    }

    print(json.dumps(api_details, indent=4))

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(api_details, f, indent=4)

    print(f"\nAPI details saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()