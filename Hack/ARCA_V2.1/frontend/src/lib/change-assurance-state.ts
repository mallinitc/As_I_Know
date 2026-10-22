import type { SnowflakeChange, SnowflakeDemoScenario } from "@/types/api";

export function resolveScenarioSelection(scenarios: SnowflakeDemoScenario[], scenarioId: string) {
  if (!scenarioId) return null;
  const scenario = scenarios.find((item) => item.scenario_id === scenarioId);
  return scenario ? {
    scenario,
    changeId: scenario.change_id,
    evaluationTimestamp: scenario.evaluation_timestamp,
  } : undefined;
}

export function resolveChangeSelection(changes: SnowflakeChange[], changeId: string) {
  return changes.find((item) => item.change_id === changeId);
}
