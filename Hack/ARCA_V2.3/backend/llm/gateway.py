from __future__ import annotations

from backend.config import LlmSettings, llm_settings
from backend.llm.prompts import agent_assistance_prompt, draft_refinement_prompt, planning_prompt, synthesis_prompt
from backend.llm.providers import HttpLlmProvider, LlmGatewayError
from backend.llm.schemas import AgentAssistanceOutput, DraftRefinementOutput, LlmPlan, LlmSynthesis, TokenUsage


class LlmGateway:
    def __init__(self, settings: LlmSettings | None = None, provider: HttpLlmProvider | None = None):
        self.settings = settings or llm_settings()
        self.provider = provider or (HttpLlmProvider(self.settings) if self.settings.configured else None)

    def capability(self) -> dict[str, object]:
        return {
            "enabled": self.settings.enabled,
            "available": self.settings.configured,
            "provider": self.settings.provider or None,
            "model_identifier": self.settings.model or None,
            "status": self.settings.status,
        }

    def _require_provider(self) -> HttpLlmProvider:
        if not self.settings.enabled:
            raise LlmGatewayError("disabled", "LLM Assisted mode is disabled.")
        if not self.settings.configured or self.provider is None:
            raise LlmGatewayError("configuration_error", "LLM Assisted mode is not fully configured.")
        return self.provider

    def plan(self, question: str, tools: list[dict[str, str]]) -> tuple[LlmPlan, str, TokenUsage]:
        return self._require_provider().complete(planning_prompt(question, tools), LlmPlan, "agent5_planning")

    def synthesize(self, question: str, deterministic_result: dict, evidence_ids: list[str]) -> tuple[LlmSynthesis, str, TokenUsage]:
        return self._require_provider().complete(synthesis_prompt(question, deterministic_result, evidence_ids), LlmSynthesis, "agent5_synthesis")

    def analyze(self, agent: str, deterministic_payload: dict, evidence_ids: list[str]) -> tuple[AgentAssistanceOutput, str, TokenUsage]:
        prompt = agent_assistance_prompt(agent, deterministic_payload, evidence_ids)
        if len(prompt) > self.settings.input_max_chars:
            raise LlmGatewayError("input_limit", "The bounded LLM input exceeded the configured size limit.")
        return self._require_provider().complete(prompt, AgentAssistanceOutput, f"{agent}_analysis")

    def improve_draft(self, draft: dict) -> tuple[DraftRefinementOutput, str, TokenUsage]:
        return self._require_provider().complete(draft_refinement_prompt(draft), DraftRefinementOutput, "agent1_draft_refinement")


__all__ = ["LlmGateway", "LlmGatewayError"]
