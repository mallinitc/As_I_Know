from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import evaluation
from backend.services.evaluation_judge import validate_judge_output


MANAGER = {"X-ARCA-Demo-Role": "arca_manager"}
ANALYST = {"X-ARCA-Demo-Role": "arca_analyst"}


def _wait(client: TestClient, run_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/v1/analytics/evaluation/runs/{run_id}", headers=MANAGER)
        assert response.status_code == 200
        if response.json()["status"] not in {"queued", "running"}:
            return response.json()
        time.sleep(0.02)
    raise AssertionError("evaluation did not finish")


@pytest.fixture()
def isolated_history(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(evaluation, "HISTORY_FILE", tmp_path / "history.json")
    evaluation._jobs.clear()
    yield
    evaluation._jobs.clear()


def test_bounded_harness_metrics_evidence_and_trajectory(isolated_history):
    evaluation.execute_evaluation("eval-test")
    run = evaluation.get_run("eval-test")
    assert run and run["status"] == "completed"
    assert run["scorecard"]["total_evaluation_cases"] == 29
    assert run["scorecard"]["failed_cases"] == 0
    assert run["scorecard"]["high_risk_recall"] is None
    assert run["scorecard"]["false_positive_rate"] is None
    assert run["live_llm_calls"] == 0
    assert all(case["expected_decision"] == case["actual_decision"] for case in run["cases"] if case["agent"] in {"A1", "A2", "A3", "A4", "A5"})
    assert all(case["execution_trace"]["tool_calls"] for case in run["cases"] if case["agent"] == "A5" and case["evaluation_mode"] == "mocked_llm")


def test_history_regression_and_exports(isolated_history):
    evaluation.execute_evaluation("eval-one")
    evaluation.execute_evaluation("eval-two")
    latest = evaluation.get_run("eval-two")
    assert latest and latest["regression"]["comparable"] is True
    assert latest["regression"]["newly_failing"] == []
    csv_body, csv_type = evaluation.export_run(latest, "csv")
    json_body, json_type = evaluation.export_run(latest, "json")
    assert "case_id,agent,provider" in csv_body and csv_type == "text/csv"
    assert '"run_id": "eval-two"' in json_body and json_type == "application/json"


def test_mock_judge_parsing_and_critical_contradiction():
    base = {
        key: {"score": 5, "justification": "Consistent with deterministic evidence."}
        for key in ("correctness", "groundedness", "relevance", "clarity", "concision", "actionability")
    }
    value = {**base, "unsupported_claims": False, "contradicts_deterministic_findings": False, "cited_evidence_ids": ["EV-1"], "overall_result": "PASS"}
    assert validate_judge_output(value, ["EV-1"])["overall_result"] == "PASS"
    value["contradicts_deterministic_findings"] = True
    assert validate_judge_output(value, ["EV-1"])["overall_result"] == "FAIL"
    value["contradicts_deterministic_findings"] = False
    value["cited_evidence_ids"] = ["INVENTED"]
    with pytest.raises(ValueError, match="not supplied"):
        validate_judge_output(value, ["EV-1"])


def test_manager_api_run_history_export_and_analyst_denial(isolated_history):
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/v1/analytics/evaluation/latest", headers=ANALYST).status_code == 403
    response = client.post("/api/v1/analytics/evaluation/runs", headers=MANAGER, json={"mode": "deterministic_and_mocked_llm"})
    assert response.status_code == 202
    run = _wait(client, response.json()["run_id"])
    assert run["scorecard"]["security_guardrail_pass_rate"] == 100.0
    assert client.get("/api/v1/analytics/evaluation/history", headers=MANAGER).status_code == 200
    assert client.get(f"/api/v1/analytics/evaluation/runs/{run['run_id']}/export/csv", headers=ANALYST).status_code == 403
    assert client.get(f"/api/v1/analytics/evaluation/runs/{run['run_id']}/export/csv", headers=MANAGER).status_code == 200


def test_runner_rejects_unallowlisted_modes_and_paths(isolated_history):
    client = TestClient(app, raise_server_exceptions=False)
    bad_mode = client.post("/api/v1/analytics/evaluation/runs", headers=MANAGER, json={"mode": "live_llm"})
    arbitrary_path = client.post("/api/v1/analytics/evaluation/runs", headers=MANAGER, json={"mode": "deterministic_and_mocked_llm", "script": "cmd.exe"})
    assert bad_mode.status_code == 422
    assert arbitrary_path.status_code == 422


def test_zero_data_state_is_explicit(isolated_history):
    assert evaluation.latest_run() is None
    assert evaluation.history() == []
