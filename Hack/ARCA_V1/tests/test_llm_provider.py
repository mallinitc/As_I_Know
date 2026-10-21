from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from arca.change_extraction import LLMChangeExtractor, MockChangeExtractor, get_extractor
from arca.investigation.models import BedrockModelAdapter, MockModelAdapter, OpenAIModelAdapter, get_model_adapter
from arca.llm_provider import BedrockProvider, MockProvider, OpenAIProvider, configured_provider, get_llm_provider, safe_provider_error


class SampleOutput(BaseModel):
    value: str


class FakeResponses:
    def __init__(self): self.calls = []
    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=SampleOutput(value="validated"))


class FakeOpenAIClient:
    def __init__(self): self.responses = FakeResponses()


class FakeBedrockClient:
    def __init__(self): self.calls = []
    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": '{"value":"validated"}'}]}}}


def test_provider_selection_defaults_to_offline_mock(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert configured_provider() == "mock"
    assert isinstance(get_llm_provider(), MockProvider)


def test_openai_provider_selection_and_structured_parse_is_injected_offline(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")
    client = FakeOpenAIClient()
    provider = get_llm_provider(client=client)
    result = provider.parse("instructions", "input", SampleOutput)
    assert isinstance(provider, OpenAIProvider)
    assert result.value == "validated"
    assert client.responses.calls[0]["model"] == "gpt-5-mini"
    assert client.responses.calls[0]["text_format"] is SampleOutput


def test_bedrock_provider_selection_and_structured_parse_is_injected_offline(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "placeholder-model")
    client = FakeBedrockClient()
    provider = get_llm_provider(client=client)
    assert isinstance(provider, BedrockProvider)
    assert provider.parse("instructions", "input", SampleOutput).value == "validated"
    assert client.calls[0]["modelId"] == "placeholder-model"


@pytest.mark.parametrize("name,extractor,planner", [
    ("mock", MockChangeExtractor, MockModelAdapter),
    ("openai", LLMChangeExtractor, OpenAIModelAdapter),
    ("bedrock", LLMChangeExtractor, BedrockModelAdapter),
])
def test_agent_provider_selection_does_not_construct_network_clients(monkeypatch, name, extractor, planner):
    monkeypatch.setenv("LLM_PROVIDER", name)
    monkeypatch.delenv("ARCA_CHANGE_EXTRACTOR", raising=False)
    monkeypatch.delenv("ARCA_INVESTIGATION_MODEL", raising=False)
    assert isinstance(get_extractor(), extractor)
    assert isinstance(get_model_adapter(), planner)


def test_missing_openai_key_is_sanitized(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        OpenAIProvider()
    message = safe_provider_error("OpenAI", RuntimeError("secret-value-should-not-appear"))
    assert "secret-value-should-not-appear" not in message


def test_invalid_provider_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        configured_provider()
