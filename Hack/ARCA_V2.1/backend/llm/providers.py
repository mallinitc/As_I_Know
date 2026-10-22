from __future__ import annotations

import json
import socket
import ssl
from time import perf_counter
from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from backend.config import LlmSettings
from backend.llm.schemas import LlmCallMetrics, TokenUsage


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
    def __init__(self, status: str, message: str, usage: TokenUsage | None = None):
        super().__init__(message)
        self.status = status
        self.usage = usage or TokenUsage()


class HttpLlmProvider:
    def __init__(self, settings: LlmSettings, client: httpx.Client | None = None):
        self.settings = settings
        # HTTPX honors standard proxy and certificate environment variables.
        # TLS verification stays enabled and redirects remain disallowed.
        self.client = client or httpx.Client(
            timeout=settings.timeout_seconds, follow_redirects=False, trust_env=True,
        )

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
    def _usage(payload: dict[str, Any], *, operation: str, duration_ms: float, status: str) -> TokenUsage:
        raw_usage = payload.get("usage")
        usage = raw_usage if isinstance(raw_usage, dict) else {}
        input_value = usage.get("input_tokens", usage.get("prompt_tokens"))
        output_value = usage.get("output_tokens", usage.get("completion_tokens"))
        total_value = usage.get("total_tokens")
        input_tokens = int(input_value) if input_value is not None else None
        output_tokens = int(output_value) if output_value is not None else None
        total_tokens = int(total_value) if total_value is not None else (input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None)
        input_details = usage.get("input_tokens_details") or {}
        output_details = usage.get("output_tokens_details") or {}
        call = LlmCallMetrics(
            operation=operation, status=status, provider="", model_identifier=str(payload.get("model") or ""),
            duration_ms=duration_ms, input_tokens=input_tokens, output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
        return TokenUsage(
            input_tokens=input_tokens or 0, output_tokens=output_tokens or 0, total_tokens=total_tokens or 0,
            cached_input_tokens=input_details.get("cached_tokens"),
            reasoning_output_tokens=output_details.get("reasoning_tokens"), calls=[call],
        )

    def _failed_usage(self, operation: str, status: str, duration_ms: float) -> TokenUsage:
        return TokenUsage(calls=[LlmCallMetrics(
            operation=operation, status=status, provider=self.settings.provider,
            model_identifier=self.settings.model, duration_ms=duration_ms,
        )])

    @staticmethod
    def _connection_status(exc: httpx.HTTPError) -> str:
        if isinstance(exc, httpx.ProxyError):
            return "proxy_error"
        cause: BaseException | None = exc
        while cause is not None:
            if "[WinError 10013]" in str(cause):
                return "network_blocked"
            if isinstance(cause, ssl.SSLError):
                return "tls_error"
            if isinstance(cause, socket.gaierror):
                return "dns_error"
            if isinstance(cause, OSError) and getattr(cause, "winerror", None) == 10013:
                return "network_blocked"
            cause = cause.__cause__
        return "provider_error"

    def complete(self, prompt: str, output_model: type[T], operation: str = "structured_output") -> tuple[T, str, TokenUsage]:
        url, headers, body = self._contract(prompt, output_model)
        started = perf_counter()
        try:
            response = self.client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            duration = (perf_counter() - started) * 1000
            raise LlmGatewayError("timeout", "The configured LLM endpoint timed out.", self._failed_usage(operation, "timeout", duration)) from exc
        except httpx.HTTPError as exc:
            duration = (perf_counter() - started) * 1000
            status = self._connection_status(exc)
            raise LlmGatewayError(status, "The configured LLM endpoint could not be reached.", self._failed_usage(operation, status, duration)) from exc
        duration = (perf_counter() - started) * 1000
        if response.status_code in {401, 403}:
            raise LlmGatewayError("authentication_error", "The configured LLM endpoint rejected authentication.", self._failed_usage(operation, "authentication_error", duration))
        if response.status_code == 429:
            raise LlmGatewayError("rate_limited", "The configured LLM endpoint rate-limited the request.", self._failed_usage(operation, "rate_limited", duration))
        if response.status_code >= 400:
            raise LlmGatewayError("provider_error", f"The configured LLM endpoint returned HTTP {response.status_code}.", self._failed_usage(operation, "provider_error", duration))
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise LlmGatewayError("invalid_response", "The LLM returned an invalid structured response.", self._failed_usage(operation, "invalid_response", duration)) from exc
        try:
            parsed = output_model.model_validate(json.loads(self._text(payload, self.settings.provider)))
        except (ValueError, ValidationError, TypeError, LlmGatewayError) as exc:
            failed_usage = self._usage(payload, operation=operation, duration_ms=duration, status="invalid_response")
            failed_call = failed_usage.calls[0].model_copy(update={"provider": self.settings.provider, "model_identifier": str(payload.get("model") or self.settings.model)})
            raise LlmGatewayError("invalid_response", "The LLM returned an invalid structured response.", failed_usage.model_copy(update={"calls": [failed_call]})) from exc
        usage = self._usage(payload, operation=operation, duration_ms=duration, status="completed")
        call = usage.calls[0].model_copy(update={
            "provider": self.settings.provider,
            "model_identifier": str(payload.get("model") or self.settings.model),
        })
        return parsed, str(payload.get("model") or self.settings.model), usage.model_copy(update={"calls": [call]})
