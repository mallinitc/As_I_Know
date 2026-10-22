from backend.llm.schemas import LlmCallMetrics, LlmSynthesis, TokenUsage
from backend.repositories.azure import AzureRepository
from backend.services.ask_arca import AskArcaService
from backend.services.ask_arca_tools import AzureInvestigationTools


service = AskArcaService()


def test_all_original_v1_scenarios_are_available_unchanged():
    expected = {
        "ASK-UNDOCUMENTED": ("Find recent undocumented changes", "Show undocumented production changes in the last 24 hours."),
        "ASK-PIM": ("Review subscription Contributor requests", "Who requested Contributor access at subscription scope this week?"),
        "ASK-RESOURCE": ("Investigate a uniquely named resource", "Who modified starchprod04 during the last 48 hours?"),
        "ASK-ACCESS": ("Troubleshoot storage access loss", "I could access starchprod04 two days ago, but now I cannot. What changed?"),
        "ASK-AMBIGUOUS": ("Ambiguous Storage Account reference", "Who modified this Storage Account during the last 48 hours?"),
        "ASK-UNSUPPORTED": ("Unsupported question guardrail", "What is the weather tomorrow?"),
    }
    catalog = {item["scenario_id"]: item for item in service.scenarios()}
    for scenario_id, (name, question) in expected.items():
        assert catalog[scenario_id]["scenario_name"] == name
        assert catalog[scenario_id]["question"] == question


def test_read_only_resource_and_activity_tools_preserve_original_evidence():
    tools = AzureInvestigationTools()
    resource = tools.find_resources(query="starchprod04")["items"][0]
    details = tools.get_resource_details(resource["resource_id"])
    activity = tools.get_activity_logs(resource_id=resource["resource_id"], modifications_only=True)
    assert details["items"][0]["resource_id"] == resource["resource_id"]
    assert {item["event_data_id"] for item in activity["items"]} >= {"az-event-0012", "az-event-0007"}
    assert all(item["event_timestamp"].endswith("Z") for item in activity["items"])


def test_access_troubleshooting_clarifies_identity_then_correlates_context():
    first = service.ask("I cannot access starchprod04. What changed?", evaluation_timestamp="2026-10-26T08:20:00Z")
    assert first["clarification_request"].startswith("Which user or service-principal")
    assert first["conversation_context"]["selected_resource"].endswith("starchprod04")
    second = service.ask("engineer12@example.invalid", evaluation_timestamp="2026-10-26T08:20:00Z", conversation_context=first["conversation_context"])
    assert "firewall/network ACL modification possibly related" in second["investigation_summary"]
    assert "not confirmed root causes" in second["investigation_summary"]
    assert "az-event-0012" in {item["evidence_id"] for item in second["evidence_references"]}
    assert second["conversation_context"]["selected_identity"] == "engineer12@example.invalid"


def test_undocumented_and_pim_scenarios_retain_v1_outcomes():
    undocumented = service.ask("ignored", scenario_id="ASK-UNDOCUMENTED")
    assert len(undocumented["findings"]) == 10
    assert all(item["category"] == "UNMATCHED_IN_AVAILABLE_RECORDS" for item in undocumented["findings"])
    assert "not confirmed unauthorized" in undocumented["investigation_summary"]
    pim = service.ask("ignored", scenario_id="ASK-PIM")
    assert {item["evidence_id"] for item in pim["evidence_references"]} >= {"pim-az-0005", "pim-az-0025"}
    assert "do not independently prove active access" in pim["investigation_summary"]


def test_resource_change_history_includes_actor_operation_timestamp_and_approval():
    result = service.ask("Who modified starchprod01 during the last 7 days?", evaluation_timestamp="2026-10-26T08:20:00Z")
    assert result["activity_timeline"]
    assert any(item.get("caller") == "engineer01@example.invalid" for item in result["activity_timeline"])
    assert all(item.get("operation_name", {}).get("value") and item.get("event_timestamp") for item in result["activity_timeline"])
    assert any(item["category"] == "MATCHED_APPROVED_CHANGE" for item in result["findings"])
    assert "az-event-0001" in {item["evidence_id"] for item in result["evidence_references"]}


def test_multiturn_actor_and_approval_followups_keep_the_selected_resource():
    first = service.ask("What changed on starchprod01?", evaluation_timestamp="2026-10-26T08:20:00Z")
    second = service.ask("Who performed those changes?", evaluation_timestamp="2026-10-26T08:20:00Z", conversation_context=first["conversation_context"])
    third = service.ask("Were they approved?", evaluation_timestamp="2026-10-26T08:20:00Z", conversation_context=second["conversation_context"])
    assert "engineer01@example.invalid" in second["investigation_summary"]
    assert "exact matching approved synthetic change" in third["investigation_summary"]
    assert third["conversation_context"]["selected_resource"].endswith("starchprod01")


def test_ambiguous_and_missing_resources_request_clarification_without_fabrication():
    ambiguous = service.ask("Who modified this Storage Account during the last 48 hours?", evaluation_timestamp="2026-10-26T08:20:00Z")
    assert "multiple matching synthetic resources" in ambiguous["clarification_request"]
    assert ambiguous["activity_timeline"] == []
    missing = service.ask("What changed on resource-definitely-not-present?", evaluation_timestamp="2026-10-26T08:20:00Z")
    assert "could not uniquely identify" in missing["clarification_request"]
    assert missing["findings"] == []


def test_user_lookup_provider_isolation_and_new_context_isolation():
    user = service.ask("Investigate Azure activities performed by engineer12@example.invalid in the last 10 days.", evaluation_timestamp="2026-10-27T00:00:00Z")
    assert user["providers_investigated"] == ["azure"]
    assert all(item.get("provider") == "azure" for item in user["findings"])
    first = service.ask("What changed on starchprod01?", evaluation_timestamp="2026-10-26T08:20:00Z")
    fresh = service.ask("Who performed those changes?", evaluation_timestamp="2026-10-26T08:20:00Z", conversation_context={"provider": "azure"})
    assert first["conversation_context"]["previous_findings"]
    assert fresh["overall_status"] == "INSUFFICIENT_EVIDENCE"
    assert fresh["activity_timeline"] == []


def test_last_access_is_not_fabricated_when_v1_has_no_last_access_source():
    result = service.ask("When did engineer12@example.invalid last access starchprod04?", evaluation_timestamp="2026-10-26T08:20:00Z")
    assert not any("last access" in str(item).casefold() for item in result["findings"])
    assert all(item.get("source") != "last_access" for item in result["evidence_references"])


def test_agent4_extra_event_is_legitimate_unique_stage3_evidence():
    events = AzureRepository().activity_logs()
    matches = [item for item in events if item.get("event_data_id") == "az-event-0106"]
    assert len(matches) == 1
    assert matches[0]["operation_name"]["value"] == "Microsoft.Compute/virtualMachines/delete"
    assert matches[0]["properties"]["synthetic_scenario"] == "UNEXPECTED_ADDITIONAL_OPERATION"


class MockSynthesisGateway:
    def capability(self):
        return {"available": True, "provider": "mocked_openai", "model_identifier": "mock-gpt", "status": "available"}

    def synthesize(self, question, deterministic_result, evidence_ids):
        assert deterministic_result["findings"]
        usage = TokenUsage(
            input_tokens=20,
            output_tokens=5,
            total_tokens=25,
            calls=[LlmCallMetrics(provider="mocked_openai", model_identifier="mock-gpt", input_tokens=20, output_tokens=5, total_tokens=25)],
        )
        return LlmSynthesis(summary="Evidence-backed advisory explanation.", evidence_citations=evidence_ids[:1]), "mock-gpt", usage


def test_mocked_llm_synthesis_preserves_deterministic_findings_and_telemetry():
    assisted = AskArcaService(gateway=MockSynthesisGateway()).ask("Show undocumented production changes in the last 24 hours.", mode="llm_assisted", evaluation_timestamp="2026-10-26T08:20:00Z")
    deterministic = service.ask("Show undocumented production changes in the last 24 hours.", evaluation_timestamp="2026-10-26T08:20:00Z")
    assert assisted["findings"] == deterministic["findings"]
    assert assisted["llm_status"] == "completed"
    assert assisted["model_identifier"] == "mock-gpt"
    assert assisted["token_usage"]["total_tokens"] == 25
    assert assisted["execution_metrics"]["model_call_count"] == 1
