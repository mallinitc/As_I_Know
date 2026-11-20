from __future__ import annotations

import json

import httpx
import pytest

from backend.config import LlmSettings, llm_settings
from backend.llm.bedrock_token import REFRESH_MARGIN_SECONDS, BedrockTokenProvider
from backend.llm.providers import HttpLlmProvider, LlmGatewayError
from backend.llm.schemas import LlmPlan


def risk_plan() -> dict:
    parameters = {"provider": "aws", "change_id": None, "user_identifier": None, "role": None, "resource": None, "time_period_days": 10, "severity": "all"}
    return {
        "intent": {"investigation_type": "unauthorized_activity", "provider": "aws", "change_id": None, "user_identifier": None, "role": None, "resource": None, "time_period_days": 10, "severity": "all", "clarification": None},
        "tool_calls": [
            {"tool_name": "find_potentially_unapproved_activity", "parameters": parameters, "purpose": "Retrieve risk evidence."},
            {"tool_name": "retrieve_supporting_evidence", "parameters": parameters, "purpose": "Preserve evidence identifiers."},
        ],
    }


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def counting_generator():
    minted = []
    def generate(region: str, ttl_seconds: int) -> str:
        minted.append((region, ttl_seconds))
        return f"bedrock-api-key-{len(minted)}"
    return generate, minted


def bedrock_settings(**overrides) -> LlmSettings:
    values = {
        "enabled": True,
        "provider": "bedrock",
        "endpoint": "https://bedrock-runtime.us-east-1.amazonaws.com",
        "model": "amazon.nova-lite-v1:0",
        "api_key": "",
        "aws_region": "us-east-1",
        "timeout_seconds": 5,
    }
    values.update(overrides)
    return LlmSettings(**values)


def converse_payload(value: dict) -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": [
            {"text": "<thinking>Recording the plan.</thinking>"},
            {"toolUse": {"toolUseId": "tooluse-1", "name": "LlmPlan", "input": value}},
        ]}},
        "stopReason": "tool_use",
        "usage": {"inputTokens": 21, "outputTokens": 9, "totalTokens": 30},
    }


def bedrock_provider(handler, token_provider: BedrockTokenProvider) -> HttpLlmProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5)
    return HttpLlmProvider(bedrock_settings(), client=client, token_provider=token_provider)


def test_bedrock_settings_default_to_nova_lite_without_stored_key(monkeypatch):
    monkeypatch.setenv("ARCA_LLM_ENABLED", "true")
    monkeypatch.setenv("ARCA_LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("ARCA_LLM_AWS_REGION", "us-east-1")
    for name in ("ARCA_LLM_ENDPOINT", "ARCA_LLM_MODEL", "ARCA_LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    configured = llm_settings()
    assert configured.configured
    assert configured.model == "amazon.nova-lite-v1:0"
    assert configured.endpoint == "https://bedrock-runtime.us-east-1.amazonaws.com"
    assert configured.bedrock_token_ttl_seconds == 3600


@pytest.mark.parametrize("model", ["amazon.nova-lite-v1:0", "us.amazon.nova-lite-v1:0", "eu.amazon.nova-lite-v1:0"])
def test_bedrock_accepts_nova_lite_identifiers(model):
    assert bedrock_settings(model=model).configured


@pytest.mark.parametrize("model", ["amazon.nova-pro-v1:0", "amazon.nova-2-lite-v1:0", "anthropic.claude-haiku", "amazon.nova-lite-v1:0-extra"])
def test_bedrock_rejects_models_other_than_nova_lite(model):
    assert not bedrock_settings(model=model).configured


def test_bedrock_requires_region():
    assert not bedrock_settings(aws_region="").configured


def test_bedrock_token_ttl_is_bounded(monkeypatch):
    monkeypatch.setenv("ARCA_BEDROCK_TOKEN_TTL_SECONDS", "60")
    with pytest.raises(ValueError, match="ARCA_BEDROCK_TOKEN_TTL_SECONDS"):
        llm_settings()


def test_token_is_cached_and_replaced_before_expiry():
    generate, minted = counting_generator()
    clock = FakeClock()
    tokens = BedrockTokenProvider("us-east-1", 3600, generator=generate, clock=clock)
    assert tokens.token() == "bedrock-api-key-1"
    clock.now += 3600 - REFRESH_MARGIN_SECONDS - 1
    assert tokens.token() == "bedrock-api-key-1"
    clock.now += 1
    assert tokens.token() == "bedrock-api-key-2"
    assert minted == [("us-east-1", 3600), ("us-east-1", 3600)]


def test_token_generation_failure_does_not_expose_details():
    def broken(region, ttl):
        raise RuntimeError("AKIA-secret-detail")
    provider = bedrock_provider(lambda request: httpx.Response(200, request=request), BedrockTokenProvider("us-east-1", 3600, generator=broken))
    with pytest.raises(LlmGatewayError) as failure:
        provider.complete("prompt", LlmPlan)
    assert failure.value.status == "authentication_error"
    assert "AKIA" not in str(failure.value)


def test_converse_contract_forces_schema_tool_and_parses_tool_input():
    generate, _ = counting_generator()
    captured = {}
    def handler(request: httpx.Request):
        captured["url"] = str(request.url); captured["auth"] = request.headers.get("authorization"); captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=converse_payload(risk_plan()), request=request)
    plan, model, usage = bedrock_provider(handler, BedrockTokenProvider("us-east-1", 3600, generator=generate)).complete("prompt", LlmPlan)
    assert captured["url"] == "https://bedrock-runtime.us-east-1.amazonaws.com/model/amazon.nova-lite-v1%3A0/converse"
    assert captured["auth"] == "Bearer bedrock-api-key-1"
    tool_config = captured["body"]["toolConfig"]
    assert tool_config["toolChoice"] == {"tool": {"name": "LlmPlan"}}
    schema = tool_config["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert "$defs" not in json.dumps(schema) and "$ref" not in json.dumps(schema)
    assert captured["body"]["inferenceConfig"] == {"maxTokens": 1200, "temperature": 0}
    assert plan.intent.provider == "aws" and model == "amazon.nova-lite-v1:0"
    assert usage.total_tokens == 30 and usage.calls[0].provider == "bedrock"


def test_rejected_key_is_reminted_and_retried_once():
    generate, minted = counting_generator()
    seen = []
    def handler(request: httpx.Request):
        seen.append(request.headers.get("authorization"))
        if len(seen) == 1:
            return httpx.Response(403, json={"message": "expired"}, request=request)
        return httpx.Response(200, json=converse_payload(risk_plan()), request=request)
    plan, _, _ = bedrock_provider(handler, BedrockTokenProvider("us-east-1", 3600, generator=generate)).complete("prompt", LlmPlan)
    assert plan.intent.provider == "aws"
    assert seen == ["Bearer bedrock-api-key-1", "Bearer bedrock-api-key-2"] and len(minted) == 2


def test_repeated_rejection_reports_authentication_error():
    generate, minted = counting_generator()
    provider = bedrock_provider(lambda request: httpx.Response(403, json={"message": "denied"}, request=request), BedrockTokenProvider("us-east-1", 3600, generator=generate))
    with pytest.raises(LlmGatewayError) as failure:
        provider.complete("prompt", LlmPlan)
    assert failure.value.status == "authentication_error" and len(minted) == 2


def test_nova_null_strings_become_json_null():
    generate, _ = counting_generator()
    plan = risk_plan()
    plan["intent"].update({"user_identifier": "null", "clarification": "null"})
    plan["tool_calls"][0]["parameters"]["role"] = "null"
    provider = bedrock_provider(lambda request: httpx.Response(200, json=converse_payload(plan), request=request), BedrockTokenProvider("us-east-1", 3600, generator=generate))
    parsed, _, _ = provider.complete("prompt", LlmPlan)
    assert parsed.intent.user_identifier is None and parsed.intent.clarification is None
    assert parsed.tool_calls[0].parameters.role is None


def test_missing_tool_use_is_invalid_response():
    generate, _ = counting_generator()
    payload = {"output": {"message": {"role": "assistant", "content": [{"text": "plain answer"}]}}, "usage": {}}
    provider = bedrock_provider(lambda request: httpx.Response(200, json=payload, request=request), BedrockTokenProvider("us-east-1", 3600, generator=generate))
    with pytest.raises(LlmGatewayError) as failure:
        provider.complete("prompt", LlmPlan)
    assert failure.value.status == "invalid_response"


def test_bedrock_resource_not_found_is_model_unavailable():
    generate, _ = counting_generator()
    def handler(request):
        return httpx.Response(400, json={"message": "hidden"}, headers={"x-amzn-ErrorType": "ResourceNotFoundException:http://internal.amazon.com/"}, request=request)
    with pytest.raises(LlmGatewayError) as failure:
        bedrock_provider(handler, BedrockTokenProvider("us-east-1", 3600, generator=generate)).complete("prompt", LlmPlan)
    assert failure.value.status == "model_unavailable" and "hidden" not in str(failure.value)
