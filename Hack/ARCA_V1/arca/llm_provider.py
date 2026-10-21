"""Minimal, portable LLM provider selection for ARCA interpretation tasks."""
from __future__ import annotations

import json
import logging
import os
from time import perf_counter
from typing import Literal, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel
from .observability import (log_llm_call, log_performance, normalize_bedrock_usage,
                            normalize_openai_usage)

load_dotenv()

T = TypeVar("T", bound=BaseModel)
LOGGER = logging.getLogger("arca.llm")


def configured_provider(explicit: str | None = None) -> Literal["mock", "openai", "bedrock"]:
    legacy = os.getenv("ARCA_MODE", "mock").strip().lower()
    value = (explicit or os.getenv("LLM_PROVIDER") or (legacy if legacy in {"mock", "bedrock"} else "mock")).strip().lower()
    if value not in {"mock", "openai", "bedrock"}:
        raise ValueError(f"Unsupported LLM provider: {value}")
    return value  # type: ignore[return-value]


class OpenAIProvider:
    name = "openai"

    def __init__(self, client=None):
        if client is None:
            key = os.getenv("OPENAI_API_KEY", "").strip()
            if not key:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            from openai import OpenAI
            client = OpenAI(
                api_key=key,
                timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45")),
                max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "1")),
            )
        self.client = client
        self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    def parse(self, instructions: str, content: str, schema: type[T]) -> T:
        parsed, _ = self.parse_with_metrics(instructions, content, schema)
        return parsed

    def parse_with_metrics(self, instructions: str, content: str, schema: type[T]) -> tuple[T, dict]:
        request_started = perf_counter()
        options = {
            "model": self.model, "instructions": instructions, "input": content, "text_format": schema,
            "max_output_tokens": int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "1200")),
            "reasoning": {"effort": os.getenv("OPENAI_REASONING_EFFORT", "minimal")},
        }
        try:
            response = self.client.responses.parse(**options)
        except Exception as exc:
            elapsed = (perf_counter() - request_started) * 1000
            call_id = log_llm_call(provider="openai", model_id=self.model, duration_ms=elapsed,
                                   status="failure", error=exc, model_input={"instructions": instructions, "content": content})
            log_performance(component_name="LLM API invocation", stage="LLM", agent="OpenAIProvider",
                            duration_ms=elapsed, status="failure", llm_call_id=call_id)
            LOGGER.warning("llm provider=openai model=%s status=error error_type=%s request_ms=%.1f",
                           self.model, type(exc).__name__, elapsed)
            raise
        request_ms = (perf_counter() - request_started) * 1000
        parse_started = perf_counter()
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("OpenAI returned no validated structured output")
        validated = schema.model_validate(parsed)
        parse_ms = (perf_counter() - parse_started) * 1000
        usage = getattr(response, "usage", None)
        normalized = normalize_openai_usage(usage)
        call_id = log_llm_call(provider="openai", model_id=self.model, duration_ms=request_ms,
                               status="success", usage=normalized,
                               model_input={"instructions": instructions, "content": content},
                               model_output=parsed)
        log_performance(component_name="LLM API invocation", stage="LLM", agent="OpenAIProvider",
                        duration_ms=request_ms, llm_call_id=call_id)
        metrics = {
            "model": self.model, "request_ms": request_ms, "parse_ms": parse_ms,
            **normalized, "call_id": call_id, "status": "success",
        }
        LOGGER.info("llm provider=openai model=%s status=success request_ms=%.1f parse_ms=%.1f input_tokens=%s output_tokens=%s",
                    self.model, request_ms, parse_ms, metrics["input_tokens"], metrics["output_tokens"])
        return validated, metrics


class BedrockProvider:
    name = "bedrock"

    def __init__(self, client=None):
        if client is None:
            import boto3
            session = boto3.Session(profile_name=os.getenv("AWS_PROFILE") or None,
                                    region_name=os.getenv("AWS_REGION", "us-east-1"))
            client = session.client("bedrock-runtime")
        self.client = client
        self.model = os.getenv("BEDROCK_MODEL_ID") or os.getenv("ARCA_BEDROCK_MODEL_ID", "")
        if not self.model:
            raise RuntimeError("BEDROCK_MODEL_ID is not configured")

    def parse(self, instructions: str, content: str, schema: type[T]) -> T:
        parsed, _ = self.parse_with_metrics(instructions, content, schema)
        return parsed

    def parse_with_metrics(self, instructions: str, content: str, schema: type[T]) -> tuple[T, dict]:
        prompt = instructions + "\nReturn JSON only matching this schema:\n" + json.dumps(schema.model_json_schema()) + "\nINPUT:\n" + content
        started = perf_counter()
        try:
            response = self.client.converse(
                modelId=self.model,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 1800, "temperature": 0},
            )
            request_ms = (perf_counter() - started) * 1000
            parse_started = perf_counter()
            text = "".join(item["text"] for item in response["output"]["message"]["content"] if "text" in item)
            parsed = schema.model_validate_json(text)
            parse_ms = (perf_counter() - parse_started) * 1000
            usage = normalize_bedrock_usage(response)
            call_id = log_llm_call(provider="bedrock", model_id=self.model, duration_ms=request_ms,
                                   status="success", usage=usage,
                                   model_input={"instructions": instructions, "content": content}, model_output=text)
            log_performance(component_name="LLM API invocation", stage="LLM", agent="BedrockProvider",
                            duration_ms=request_ms, llm_call_id=call_id)
            return parsed, {"model": self.model, "request_ms": request_ms, "parse_ms": parse_ms,
                            **usage, "call_id": call_id, "status": "success"}
        except Exception as exc:
            elapsed = (perf_counter() - started) * 1000
            call_id = log_llm_call(provider="bedrock", model_id=self.model, duration_ms=elapsed,
                                   status="failure", error=exc,
                                   model_input={"instructions": instructions, "content": content})
            log_performance(component_name="LLM API invocation", stage="LLM", agent="BedrockProvider",
                            duration_ms=elapsed, status="failure", llm_call_id=call_id)
            raise


class MockProvider:
    name = "mock"

    def parse(self, instructions: str, content: str, schema: type[T]) -> T:
        raise RuntimeError("Mock mode does not perform LLM inference")


def get_llm_provider(name: str | None = None, client=None):
    selected = configured_provider(name)
    if selected == "openai": return OpenAIProvider(client=client)
    if selected == "bedrock": return BedrockProvider(client=client)
    return MockProvider()


def safe_provider_error(provider: str, exc: Exception) -> str:
    """Return a useful error without echoing request bodies, keys, or SDK messages."""
    return f"Configured {provider} inference is unavailable: {type(exc).__name__}. No model result was used."
