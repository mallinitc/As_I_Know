import type { AskLlmCapability } from "@/types/api";

export type AskExecutionMode = "deterministic" | "llm_assisted";

export function selectAskExecutionMode(requested: AskExecutionMode, capability: AskLlmCapability | null): AskExecutionMode {
  if (requested === "llm_assisted" && !capability?.available) return "deterministic";
  return requested;
}
