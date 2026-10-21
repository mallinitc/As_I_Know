from __future__ import annotations

import json
from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from backend.config import LlmSettings
from backend.llm.schemas import TokenUsage


T = TypeVar("T", bound=BaseModel)


def _strict_json_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_strict_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {key: _strict_json_schema(item) for key, item in value.items()}
    if normalized.get("type") == "object" and isinstance(normalized.get("properties"), dict):
        normalized["additionalProperties"] = False
        normalized["required"] = list(normalized["properties"])
    return normalized


class LlmGatewayError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


class HttpLlmProvider:
    def __init__(self, settings: LlmSettings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.timeout_seconds, follow_redirects=False)

    def _contract(self, prompt: str, output_model: type[T]) -> tuple[str, dict[str, str], dict[str, Any]]:
        schema = _strict_json_schema(output_model.model_json_schema())
        if self.settings.provider == "azure_openai":
            url = f"{self.settings.endpoint}/openai/deployments/{quote(self.settings.model, safe='')}/chat/completions?api-version={quote(self.settings.api_version, safe='')}"
            headers = {"api-key": self.settings.api_key, "Content-Type": "application/json"}
            body = {
                "messages": [{"role": "system", "content": "Return only the requested structured result."}, {"role": "user", "content": prompt}],
                "temperature": 0,
                "response_format": {"type": "json_schema", "json_schema": {"name": output_model.__name__, "strict": True, "schema": schema}},
            }
            return url, headers, body
        if self.settings.provider in {"openai", "openai_compatible"}:
            url = f"{self.settings.endpoint}/v1/responses"
            headers = {"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"}
            body = {
                "model": self.settings.model,
                "input": [{"role": "system", "content": "Return only the requested structured result."}, {"role": "user", "content": prompt}],
                "store": False,
                "max_output_tokens": self.settings.max_output_tokens,
                "text": {"format": {"type": "json_schema", "name": output_model.__name__, "strict": True, "schema": schema}},
            }
            if self.settings.provider == "openai":
                body["reasoning"] = {"effort": self.settings.reasoning_effort}
            return url, headers, body
        raise LlmGatewayError("configuration_error", "The configured LLM provider is unsupported.")

    @staticmethod
    def _text(payload: dict[str, Any], provider: str) -> str:
        if provider == "azure_openai":
            try:
                return payload["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise LlmGatewayError("invalid_response", "The LLM response did not contain structured output.") from exc
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise LlmGatewayError("invalid_response", "The LLM response did not contain structured output.")

    @staticmethod
    def _usage(payload: dict[str, Any]) -> TokenUsage:
        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
        output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
        return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=int(usage.get("total_tokens", input_tokens + output_tokens) or 0))

    def complete(self, prompt: str, output_model: type[T]) -> tuple[T, str, TokenUsage]:
        url, headers, body = self._contract(prompt, output_model)
        try:
            response = self.client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise LlmGatewayError("timeout", "The configured LLM endpoint timed out.") from exc
        except httpx.HTTPError as exc:
            raise LlmGatewayError("provider_error", "The configured LLM endpoint could not be reached.") from exc
        if response.status_code in {401, 403}:
            raise LlmGatewayError("authentication_error", "The configured LLM endpoint rejected authentication.")
        if response.status_code == 429:
            raise LlmGatewayError("rate_limited", "The configured LLM endpoint rate-limited the request.")
        if response.status_code >= 400:
            raise LlmGatewayError("provider_error", f"The configured LLM endpoint returned HTTP {response.status_code}.")
        try:
            payload = response.json()
            parsed = output_model.model_validate(json.loads(self._text(payload, self.settings.provider)))
        except (ValueError, ValidationError, TypeError) as exc:
            raise LlmGatewayError("invalid_response", "The LLM returned an invalid structured response.") from exc
        return parsed, str(payload.get("model") or self.settings.model), self._usage(payload)
