import assert from "node:assert/strict";
import test from "node:test";

import { ArcaApiError, createArcaApiClient } from "./arca-api.ts";

const names = [
  "Azure execution potential match", "Execution timing deviation", "Unexpected engineer deviation",
  "Unexpected resource modification", "Approved future change without execution evidence",
];
const scenarios = names.map((scenario_name, index) => ({
  scenario_id: ["S3-MATCH", "S3-TIMING", "S3-UNEXPECTED-ACTOR", "S3-UNEXPECTED-RESOURCE", "S3-NO-EVIDENCE"][index],
  scenario_name, mode: "change", change_id: ["CHG-AZ-2001", "CHG-AZ-2007", "CHG-AZ-2008", "CHG-AZ-2009", "CHG-AZ-2021"][index],
  user_identity: null, evaluation_timestamp: "2026-10-27T00:00:00Z", window_days: 10,
  event_data_ids: index === 4 ? [] : [`az-event-000${index === 0 ? 1 : index + 6}`], expected_findings: [],
  source: "v1", description: "Original V1 scenario", expected_outcome: index === 0 ? "POTENTIAL_MATCH" : index === 4 ? "EVIDENCE_INCOMPLETE" : "DEVIATION_DETECTED",
}));
const result = {
  schema_version: 1, investigation_id: "AZ-EXEC-TEST", provider: "azure", mode: "change", change_id: "CHG-AZ-2001", user: null,
  evaluation_timestamp: "2026-10-27T00:00:00Z", period_start: null, period_end: "2026-10-27T00:00:00Z", overall_status: "POTENTIAL_MATCH",
  findings: [], event_ids: ["az-event-0001"], confidence: "high", timeline: [], expected_operations: [], observed_operations: [], evidence: [], recommendations: [], limitations: [],
  v1_assessment: { status: "POTENTIAL_MATCH", events: [], missing_expected: [], impact_signals: [], warning: "Matching activity is not proof of intended state." },
};
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }); }

test("Stage 3 exposes the original V1 scenarios and uses only Azure execution routes", async () => {
  const calls: Array<{ url: string; body?: string }> = [];
  const client = createArcaApiClient({ baseUrl: "http://arca.test", fetchImpl: (async (input, init) => {
    const url = String(input); calls.push({ url, body: init?.body ? String(init.body) : undefined });
    if (url.endsWith("/azure/execution-scenarios")) return response({ provider: "azure", synthetic: true, count: 5, items: scenarios });
    return response(result);
  }) as typeof fetch });
  const loaded = await client.getAzureExecutionScenarios();
  assert.deepEqual(loaded.items.map((item) => item.scenario_name), names);
  const assessed = await client.assureAzureChangeExecution({ change_id: "CHG-AZ-2001", scenario_id: "S3-MATCH" });
  assert.equal(assessed.v1_assessment?.status, "POTENTIAL_MATCH");
  assert.equal(calls.every((call) => call.url.includes("/api/v1/azure/")), true);
  assert.equal(calls.some((call) => call.url.includes("snowflake")), false);
  assert.deepEqual(JSON.parse(calls[1].body || "{}"), { change_id: "CHG-AZ-2001", scenario_id: "S3-MATCH" });
});

test("Stage 3 Azure errors never use Snowflake wording", async () => {
  const client = createArcaApiClient({ fetchImpl: (async () => response({ detail: "hidden" }, 404)) as typeof fetch });
  await assert.rejects(client.assureAzureChangeExecution({ change_id: "CHG-AZ-9999" }), (error: unknown) =>
    error instanceof ArcaApiError && error.message.includes("Azure") && !error.message.includes("Snowflake"));
});
