from __future__ import annotations

from fastapi.testclient import TestClient

from backend.llm.schemas import DraftRefinementOutput, TokenUsage
from backend.main import app
from backend.services.change_draft import ChangeDraftService


class DraftGateway:
    def __init__(self, output: DraftRefinementOutput):
        self.output = output
        self.calls = 0

    def capability(self):
        return {"available": True, "model_identifier": "test-model"}

    def improve_draft(self, draft):
        self.calls += 1
        return self.output, "test-model", TokenUsage(input_tokens=5, output_tokens=3, total_tokens=8)


def test_deterministic_draft_preserves_evidence_and_leaves_unknowns_empty():
    response = TestClient(app).post("/api/v1/agents/change-quality/improve-draft", json={
        "provider": "azure", "change_id": "CHG-AZ-2001", "execution_mode": "deterministic",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["change_number"] == "CHG-AZ-2001"
    assert body["draft"]["resource_name_or_id"].startswith("/subscriptions/")
    assert body["draft"]["business_justification"] == ""
    assert "business_justification" in body["missing_fields"]
    assert body["llm_invoked"] is False


def test_llm_refinement_cannot_fill_unknown_fields_or_change_technical_facts():
    generated = DraftRefinementOutput(
        change_title="Clearer title", business_justification="Invented justification",
        implementation_steps=["Refined supported operation"], validation_plan=["Invented validation"],
        rollback_plan="Invented rollback", expected_outcome="Invented outcome", risk_and_impact="Refined moderate risk",
    )
    gateway = DraftGateway(generated)
    result = ChangeDraftService(gateway=gateway).improve("azure", "CHG-AZ-2001", "llm_assisted")
    assert gateway.calls == 1 and result["llm_invoked"] is True
    assert result["draft"]["business_justification"] == ""
    assert result["draft"]["validation_plan"] == []
    assert result["draft"]["rollback_plan"] == ""
    assert result["draft"]["resource_name_or_id"].startswith("/subscriptions/")


def test_unknown_change_returns_404_without_internal_trace():
    response = TestClient(app).post("/api/v1/agents/change-quality/improve-draft", json={
        "provider": "aws", "change_id": "DOES-NOT-EXIST", "execution_mode": "deterministic",
    })
    assert response.status_code == 404
    assert "Traceback" not in response.text
