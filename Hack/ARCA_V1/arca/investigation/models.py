"""Configurable planning adapters for conversational investigation."""
from __future__ import annotations

import json
import os
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from arca.time_filters import calculate_time_window, parse_utc
from arca.llm_provider import get_llm_provider, safe_provider_error

MODEL_INTENTS = ("access_troubleshooting", "undocumented_changes", "resource_changes", "pim_requests",
                 "actors_followup", "approval_followup", "unsupported", "malformed")
ALLOWED_INTENTS = set(MODEL_INTENTS) | {"unavailable", "greeting", "capabilities", "known_cloud", "general_cloud", "unrelated"}
ALLOWED_PARAMETERS = {"identity", "role", "scope", "start", "end", "environment", "resource_query"}


class InvestigationParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str | None = None
    role: str | None = None
    scope: str | None = None
    start: str | None = None
    end: str | None = None
    environment: str | None = None
    resource_query: str | None = None


class InvestigationPlan(BaseModel):
    intent: Literal["access_troubleshooting", "undocumented_changes", "resource_changes", "pim_requests",
                    "actors_followup", "approval_followup", "unsupported", "malformed"]
    parameters: InvestigationParameters = Field(default_factory=InvestigationParameters)


class EvidenceNarrative(BaseModel):
    response: str


GREETING_RESPONSE = ("Hello! I'm ARCA, your Cloud Risk & Change Assurance Assistant.\n\n"
                     "I can help investigate infrastructure changes, privileged access, undocumented modifications, "
                     "and cloud access issues.\n\nWhat would you like to investigate?")

CAPABILITY_RESPONSE = ("ARCA helps validate cloud change records, assess privileged-access requests, verify execution "
                       "evidence, identify unmatched infrastructure modifications, and investigate access or change "
                       "questions using read-only Azure, AWS, and Snowflake evidence.")

KNOWN_EXPLANATIONS = {
    "azure pim": "Azure Privileged Identity Management (PIM) manages time-bound and approval-controlled activation of privileged Microsoft Entra roles and Azure resource roles. A PIM request or approval is not, by itself, proof that access was activated.",
    "least privilege": "Least privilege means granting only the permissions, resource scope, and activation duration required for the documented task. ARCA evaluates role suitability, scope breadth, identity, and timing separately.",
    "change window": "A change window is the approved start and end period during which implementation activity is expected. ARCA compares privileged-access and execution timestamps with that documented window.",
    "stage 2": "Stage 2 independently evaluates privileged-access evidence against an approved change: identity, role permissions, resource scope, activation status, justification, and duration. Its result is an ARCA recommendation, not an approval action.",
}


def classify_conversation(query: str) -> dict | None:
    """Route only obvious conversational inputs; investigations still use the model planner."""
    text = " ".join((query or "").strip().lower().split())
    normalized = re.sub(r"[^a-z0-9 ]", "", text)
    if normalized in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "thanks", "thank you"}:
        return {"intent": "greeting", "response": GREETING_RESPONSE}
    if any(phrase in text for phrase in ("what can arca do", "how can arca help", "arca capabilities", "help me use arca")):
        return {"intent": "capabilities", "response": CAPABILITY_RESPONSE}
    for phrase, response in KNOWN_EXPLANATIONS.items():
        if phrase in text and (text.startswith("what") or text.startswith("how") or text.startswith("explain")):
            return {"intent": "known_cloud", "response": response}
    if any(phrase in text for phrase in ("cricket match", "weather", "write me a poem", "write a poem", "capital of france")):
        return {"intent": "unrelated", "response": "ARCA focuses on cloud security, privileged access, and change governance. I can investigate infrastructure changes, access issues, PIM activity, or change-assurance evidence."}
    investigation_terms = ("access", "modified", "changed", "change", "resource", "storage", "pim", "role", "privilege", "undocumented", "activity log", "cloudtrail", "snowflake", "query history", "accountadmin")
    if any(term in text for term in investigation_terms): return None
    if re.match(r"^(what|how|why|explain|describe)\b", text):
        return {"intent": "general_cloud"}
    return None

def _window(query, as_of):
    if re.search(r"last 24 hours|last day", query, re.I): selection = "Last 24 Hours"
    elif re.search(r"last 2 days|two days ago|last 48 hours", query, re.I): selection = "Last 2 Days"
    elif re.search(r"last 15 days", query, re.I): selection = "Last 15 Days"
    elif re.search(r"last 30 days", query, re.I): selection = "Last 30 Days"
    else: selection = "Last 7 Days"
    start, end = calculate_time_window(selection, parse_utc(as_of))
    fmt = lambda value: value.isoformat(timespec="seconds").replace("+00:00", "Z")
    return fmt(start), fmt(end)


class MockModelAdapter:
    """Clearly deterministic parser; it does not perform LLM reasoning."""
    mode = "mock"
    label = "MOCK MODE · deterministic parser"

    def plan(self, query, context, evidence_as_of):
        text = (query or "").strip()
        if not text or len(text) > 2000:
            return {"intent": "malformed", "parameters": {}, "error": "Enter a non-empty investigation question under 2,000 characters."}
        lower = text.lower()
        start, end = _window(text, evidence_as_of)
        email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
        guid = re.search(r"\b[0-9a-f]{8}-[0-9a-f-]{27,36}\b", text, re.I)
        params = {"start": start, "end": end, "environment": "production" if "production" in lower else None}
        if email or guid: params["identity"] = (email or guid).group(0)
        pending = context.get("pending_clarification")
        if pending == "resource":
            return {"intent": context.get("pending_intent", "resource_changes"), "parameters": params}
        if pending == "identity" and (email or guid):
            return {"intent": "access_troubleshooting", "parameters": params}
        if "undocumented" in lower or "without approved" in lower:
            return {"intent": "undocumented_changes", "parameters": params}
        if ("pim" in lower or "requested" in lower) and ("access" in lower or "contributor" in lower or "role" in lower):
            if "contributor" in lower: params["role"] = "Contributor"
            if "subscription" in lower: params["scope"] = "/subscriptions/"
            return {"intent": "pim_requests", "parameters": params}
        if re.search(r"who (performed|made) (those|the) changes", lower):
            return {"intent": "actors_followup", "parameters": params}
        if re.search(r"were (they|those) approved|was (it|that) approved", lower):
            return {"intent": "approval_followup", "parameters": params}
        if re.search(r"could access|cannot access|can't access|access loss|lost access", lower):
            return {"intent": "access_troubleshooting", "parameters": params}
        if re.search(r"what changed|who modified|modified this|changes on", lower):
            return {"intent": "resource_changes", "parameters": params}
        return {"intent": "unsupported", "parameters": params}


class BedrockModelAdapter:
    """Opt-in Bedrock planner. Tool execution remains local and validated."""
    mode = "bedrock"
    label = "BEDROCK MODE"

    def plan(self, query, context, evidence_as_of):
        try:
            instructions = (
                "Select one investigation intent. Valid intents: " + ", ".join(MODEL_INTENTS) +
                ". Valid parameter keys: " + ", ".join(sorted(ALLOWED_PARAMETERS)) +
                ". Never invent identifiers. Ask through missing parameters. Available read-only tools: find_resources, "
                "get_resource_details, get_activity_logs, get_role_assignments, get_pim_requests, get_change_records, "
                "find_undocumented_changes. Context: " + json.dumps(context, default=str) +
                ". Evidence as-of: " + evidence_as_of
            )
            proposed = get_llm_provider("bedrock").parse(instructions, query, InvestigationPlan)
            intent = proposed.intent
            params = proposed.parameters.model_dump(exclude_none=True)
            if intent not in ALLOWED_INTENTS or not isinstance(params, dict) or set(params) - ALLOWED_PARAMETERS:
                raise ValueError("Model returned an invalid investigation plan")
            return {"intent": intent, "parameters": {key: value for key, value in params.items() if key in ALLOWED_PARAMETERS}}
        except Exception as exc:
            return {"intent": "unavailable", "parameters": {},
                    "error": f"Configured Bedrock planning is unavailable: {type(exc).__name__}. No model reasoning was used."}


class OpenAIModelAdapter:
    """OpenAI planner and evidence narrator; all tool execution remains local/read-only."""
    mode = "openai"
    label = "OPENAI MODE"

    def plan(self, query, context, evidence_as_of):
        try:
            instructions = (
                "Select exactly one ARCA investigation intent. Valid intents: " + ", ".join(MODEL_INTENTS) +
                ". Use only these parameters: " + ", ".join(sorted(ALLOWED_PARAMETERS)) +
                ". Never invent identifiers. Use clarification-compatible intent when a resource or identity is missing. "
                "ARCA tools are read-only and the model must never approve access or execute infrastructure changes. "
                "Conversation context: " + json.dumps(context, default=str) + ". Evidence reference time: " + evidence_as_of
            )
            proposed = get_llm_provider("openai").parse(instructions, query, InvestigationPlan)
            if proposed.intent not in ALLOWED_INTENTS:
                raise ValueError("Model returned an invalid investigation intent")
            params = proposed.parameters.model_dump(exclude_none=True)
            start, end = _window(query, evidence_as_of)
            params.setdefault("start", start); params.setdefault("end", end)
            return {"intent": proposed.intent, "parameters": params}
        except Exception as exc:
            return {"intent": "unavailable", "parameters": {}, "error": safe_provider_error("OpenAI", exc)}

    def respond(self, deterministic_response, results, context):
        instructions = (
            "Write a concise cloud-investigation response based only on the supplied local tool results. Cite original "
            "evidence IDs and UTC timestamps when present. Distinguish possible causes from confirmed facts, unmatched "
            "events from unauthorized activity, and requests from active access. Never claim approval or perform an action. "
            "If evidence is insufficient, say so explicitly."
        )
        content = json.dumps({"baseline": deterministic_response, "tool_results": results, "context": context}, default=str)
        return get_llm_provider("openai").parse(instructions, content, EvidenceNarrative).response

    def answer_general(self, query):
        instructions = ("Answer this general cloud-security question concisely. Do not claim to have inspected the user's "
                        "environment or cite ARCA evidence. Clearly state when an answer would require current external data.")
        return get_llm_provider("openai").parse(instructions, query, EvidenceNarrative).response


def get_model_adapter(mode=None):
    configured = (mode or os.getenv("ARCA_INVESTIGATION_MODEL") or os.getenv("LLM_PROVIDER", "mock")).lower()
    if configured == "mock": return MockModelAdapter()
    if configured == "openai": return OpenAIModelAdapter()
    if configured == "bedrock": return BedrockModelAdapter()
    raise ValueError(f"Unsupported investigation model mode: {configured}")
