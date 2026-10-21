import assert from "node:assert/strict";
import test from "node:test";

import { ArcaApiError, createArcaApiClient } from "./arca-api.ts";
import { resolveChangeSelection, resolveScenarioSelection } from "./change-assurance-state.ts";

const change = {
  change_id: "CHG-SF-1007", provider: "snowflake", short_description: "Grant role",
  description: "Approved role grant", state: "approved", environment: "production",
  start: "2026-11-07T10:00:00Z", end: "2026-11-07T10:30:00Z", expected: [],
};
const scenario = {
  scenario_id: "SF-UNIFIED-01", scenario_name: "Appropriate Role", description: "Verified",
  change_id: "CHG-SF-1007", evaluation_timestamp: "2026-11-07T10:15:00Z",
  expected_check_outcomes: { overall: "PASS" },
};
const section = { status: "APPROPRIATE", evidence: [], findings: [] };
const validation = {
  schema_version: 1, change_id: "CHG-SF-1007", provider: "snowflake", status: "PASS", overall_status: "PASS",
  change_quality: { ...section, status: "VALID" }, window_assessment: { ...section, status: "ACTIVE" },
  role_assessment: section, missing_information: [], findings: [], evidence: ["sf-object-grant-001"],
  evaluation_timestamp: "2026-11-07T10:15:00Z",
};
const executionScenario = {
  scenario_id: "SF-POST-01", scenario_name: "Compliant execution", change_id: "CHG-SF-1007",
  user_identity: null, evaluation_timestamp: "2026-11-24T00:00:00Z", investigation_mode: "change",
  evidence_query_ids: ["SF-QRY-001"], window_days: 10, expected_findings: ["COMPLIANT_EXECUTION"],
};
const execution = {
  schema_version: 1, investigation_id: "SF-EXEC-TEST", provider: "snowflake", mode: "change",
  change_id: "CHG-SF-1007", user: null, evaluation_timestamp: "2026-11-24T00:00:00Z",
  period_start: null, period_end: "2026-11-24T00:00:00Z", overall_status: "COMPLIANT",
  findings: [], query_ids: ["SF-QRY-001"], confidence: "high", timeline: [],
  expected_operations: [], observed_operations: [], evidence: [], recommendations: [], limitations: [],
};
const azureChange = {
  change_id: "CHG-AZ-2001", provider: "azure", environment: "production", description: "Update storage",
  state: "approved", implementer: { principal_id: "principal-1", principal_name: "engineer@example.invalid" },
  start: "2026-10-20T10:00:00Z", end: "2026-10-20T11:00:00Z",
  expected: [{ operation: "Microsoft.Storage/storageAccounts/write", resource_id: "/subscriptions/demo/storage" }],
};
const azureScenario = { scenario_id: "AZ-CHANGE-01", scenario_name: "Valid Change", stage: "change", change_id: "CHG-AZ-2001", description: "Verified", source_scenario: "VALID_APPROVED_CHANGE" };
const azureBase = {
  schema_version: 1, provider: "azure", change_id: "CHG-AZ-2001", overall_status: "VALID",
  findings: [], missing_information: [], evidence: [], recommendations: [], change: azureChange,
};
const azureExecutionScenario = {
  scenario_id: "AZ-EXEC-01", scenario_name: "Compliant Storage Change", mode: "change",
  change_id: "CHG-AZ-2001", user_identity: null, evaluation_timestamp: "2026-10-27T00:00:00Z",
  window_days: 10, event_data_ids: ["az-event-0001"],
  expected_findings: ["COMPLIANT_EXECUTION"],
};
const azureExecution = {
  schema_version: 1, investigation_id: "AZ-EXEC-TEST", provider: "azure", mode: "change",
  change_id: "CHG-AZ-2001", user: null, evaluation_timestamp: "2026-10-27T00:00:00Z",
  period_start: null, period_end: "2026-10-27T00:00:00Z", overall_status: "COMPLIANT",
  findings: [], event_ids: ["az-event-0001"], confidence: "high", timeline: [],
  expected_operations: [], observed_operations: [], evidence: [], recommendations: [], limitations: [],
};
const awsChange = { change_id: "CHG1007", environment: "prod", actor: "aws-user-7", state: "approved", start: "2026-10-22T10:00:00Z", end: "2026-10-22T11:00:00Z", description: "Read report", expected: [{ eventName: "GetObject", resource: "arn:aws:s3:::arca-reports/report.csv" }] };
const awsScenario = { scenario_id: "AWS-ACCESS-06", scenario_name: "Appropriate S3 Permission", stage: "access", change_id: "CHG1007", expected_findings: [] };
const awsBase = { schema_version: 1, provider: "aws", change_id: "CHG1007", findings: [], missing_information: [], recommendations: [], evidence: [], change: awsChange };
const awsExecutionScenario = { scenario_id: "AWS-EXEC-01", scenario_name: "Compliant", mode: "change", change_id: "CHG1007", user_identity: null, evaluation_timestamp: "2026-10-22T12:00:00Z", window_days: 10, event_ids: ["aws-exec-001"], expected_findings: ["COMPLIANT_EXECUTION"] };
const awsExecution = { schema_version: 1, investigation_id: "AWS-EXEC-TEST", provider: "aws", mode: "change", change_id: "CHG1007", user: null, evaluation_timestamp: "2026-10-22T12:00:00Z", period_start: null, period_end: "2026-10-22T12:00:00Z", overall_status: "COMPLIANT", findings: [], event_ids: ["aws-exec-001"], confidence: "high", timeline: [], expected_operations: [], observed_operations: [], evidence: [], recommendations: [], limitations: [] };
const riskScenario = { scenario_id: "RISK-01", scenario_name: "AWS risk", environment: "aws", evaluation_timestamp: "2026-10-22T12:00:00Z", window_days: 10, identity: null, role: null, resource: null, severity: "all", expected_providers: ["aws"], expected_findings: ["POSSIBLE_UNAPPROVED_ACTIVITY"] };
const riskResult = { investigation_id: "RISK-TEST", providers_investigated: ["aws"], period_start: "2026-10-12T12:00:00Z", period_end: "2026-10-22T12:00:00Z", summary: "Reviewed evidence", risk_counts: { high: 1 }, findings: [], evidence_references: [], activity_timeline: [], confidence: "limited", evidence_limitations: [] };
const askScenario = { scenario_id: "ASK-01", scenario_name: "AWS investigation", question: "Find AWS risks", evaluation_timestamp: "2026-10-22T12:00:00Z", expected_intent: "unauthorized_activity", expected_providers: ["aws"] };
const askCapabilities = { default_mode: "deterministic", modes: ["deterministic", "llm_assisted"], providers: ["aws", "all"], tools: [{ name: "find_potentially_unapproved_activity", description: "Find risks" }], supported_periods: ["last 10 days"], llm: { enabled: false, available: false, provider: null, model_identifier: null, status: "disabled" } };
const askResult = { investigation_id: "ASK-TEST", original_question: "Find AWS risks", resolved_intent: { provider: "aws" }, providers_investigated: ["aws"], execution_mode: "deterministic", overall_status: "POTENTIAL_RISK", investigation_summary: "Evidence-backed result", findings: [], evidence_references: [], activity_timeline: [], tool_execution_trace: [], confidence: "limited", evidence_limitations: [], recommended_actions: [], clarification_request: null, llm_provider: null, llm_status: "not_invoked", model_identifier: null, token_usage: null, model_generated_explanation: null, llm_evidence_citations: [], llm_error: null };

function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

test("typed client requests every versioned endpoint", async () => {
  const calls: { url: string; init?: RequestInit }[] = [];
  const mockFetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/environments")) return response({ environments: [{ provider: "snowflake", display_name: "Snowflake", capabilities: ["change_access_validation", "execution_assurance"] }] });
    if (url.endsWith("/azure/changes")) return response({ provider: "azure", evidence_source: "Synthetic", synthetic: true, count: 1, items: [azureChange] });
    if (url.endsWith("/azure/demo-scenarios")) return response({ provider: "azure", synthetic: true, count: 1, items: [azureScenario] });
    if (url.endsWith("/azure/validate/change")) return response({ ...azureBase, stage: "change" });
    if (url.endsWith("/azure/validate/access")) return response({ ...azureBase, stage: "access", overall_status: "APPROVE_RECOMMENDED", pim_assessments: [], covered_operations: [], missing_operations: [] });
    if (url.endsWith("/azure/execution-scenarios")) return response({ provider: "azure", synthetic: true, count: 1, items: [azureExecutionScenario] });
    if (url.endsWith("/azure/execution-assurance/user")) return response({ ...azureExecution, mode: "user", change_id: null, user: { principal_id: "principal-1" } });
    if (url.endsWith("/azure/execution-assurance/change")) return response(azureExecution);
    if (url.endsWith("/aws/changes")) return response({ provider: "aws", evidence_source: "Synthetic", synthetic: true, count: 1, items: [awsChange] });
    if (url.endsWith("/aws/demo-scenarios")) return response({ provider: "aws", synthetic: true, count: 1, items: [awsScenario] });
    if (url.endsWith("/aws/validate/change")) return response({ ...awsBase, stage: "change", overall_status: "VALID" });
    if (url.endsWith("/aws/validate/access")) return response({ ...awsBase, stage: "access", overall_status: "APPROPRIATE_WITH_LIMITATIONS", permission_evaluations: [], limitations: [] });
    if (url.endsWith("/aws/execution-scenarios")) return response({ provider: "aws", synthetic: true, count: 1, items: [awsExecutionScenario] });
    if (url.endsWith("/aws/execution-assurance/user")) return response({ ...awsExecution, mode: "user", change_id: null, user: { principal_id: "AIDA-BOB" } });
    if (url.endsWith("/aws/execution-assurance/change")) return response(awsExecution);
    if (url.endsWith("/investigations/risk/scenarios")) return response({ synthetic: true, count: 1, items: [riskScenario] });
    if (url.endsWith("/investigations/risk")) return response(riskResult);
    if (url.endsWith("/agents/ask-arca/scenarios")) return response({ synthetic: true, count: 1, items: [askScenario] });
    if (url.endsWith("/agents/ask-arca/capabilities")) return response(askCapabilities);
    if (url.endsWith("/agents/ask-arca")) return response(askResult);
    if (url.endsWith("/changes")) return response({ provider: "snowflake", evidence_source: "Synthetic", synthetic: true, count: 1, items: [change] });
    if (url.endsWith("/demo-scenarios")) return response({ provider: "snowflake", synthetic: true, count: 1, items: [scenario] });
    if (url.endsWith("/execution-scenarios")) return response({ provider: "snowflake", synthetic: true, count: 1, items: [executionScenario] });
    if (url.endsWith("/execution-assurance/user")) return response({ ...execution, mode: "user", change_id: null, user: { user_id: "SF-USER-001" } });
    if (url.endsWith("/execution-assurance/change")) return response(execution);
    return response(validation);
  }) as typeof fetch;
  const client = createArcaApiClient({ baseUrl: "http://arca.test/", fetchImpl: mockFetch });

  assert.equal((await client.getEnvironments()).environments[0].provider, "snowflake");
  assert.equal((await client.getSnowflakeChanges()).items[0].change_id, "CHG-SF-1007");
  assert.equal((await client.getSnowflakeDemoScenarios()).items[0].scenario_id, "SF-UNIFIED-01");
  assert.equal((await client.validateSnowflakeChange({ change_id: "CHG-SF-1007", evaluation_timestamp: scenario.evaluation_timestamp })).overall_status, "PASS");
  assert.equal((await client.getSnowflakeExecutionScenarios()).items[0].scenario_id, "SF-POST-01");
  assert.equal((await client.assureSnowflakeChangeExecution({ change_id: "CHG-SF-1007" })).overall_status, "COMPLIANT");
  assert.equal((await client.assureSnowflakeUserExecution({ user_identity: "SFSECURITY01", window_days: 10 })).mode, "user");
  assert.equal((await client.getAzureChanges()).items[0].change_id, "CHG-AZ-2001");
  assert.equal((await client.getAzureDemoScenarios()).items[0].scenario_id, "AZ-CHANGE-01");
  assert.equal((await client.validateAzureChange("CHG-AZ-2001")).overall_status, "VALID");
  assert.equal((await client.validateAzureAccess("CHG-AZ-2001")).overall_status, "APPROVE_RECOMMENDED");
  assert.equal((await client.getAzureExecutionScenarios()).items[0].scenario_id, "AZ-EXEC-01");
  assert.equal((await client.assureAzureChangeExecution({ change_id: "CHG-AZ-2001" })).event_ids[0], "az-event-0001");
  assert.equal((await client.assureAzureUserExecution({ user_identity: "principal-1", window_days: 10 })).mode, "user");
  assert.equal((await client.getAwsChanges()).items[0].change_id, "CHG1007");
  assert.equal((await client.getAwsDemoScenarios()).items[0].scenario_id, "AWS-ACCESS-06");
  assert.equal((await client.validateAwsChange("CHG1007")).overall_status, "VALID");
  assert.equal((await client.validateAwsAccess("CHG1007")).overall_status, "APPROPRIATE_WITH_LIMITATIONS");
  assert.equal((await client.getAwsExecutionScenarios()).items[0].scenario_id, "AWS-EXEC-01");
  assert.equal((await client.assureAwsChangeExecution({ change_id: "CHG1007" })).overall_status, "COMPLIANT");
  assert.equal((await client.assureAwsUserExecution({ user_identity: "AIDA-BOB", window_days: 10 })).mode, "user");
  assert.equal((await client.getRiskScenarios()).items[0].scenario_id, "RISK-01");
  assert.equal((await client.investigateRisk({ environment: "aws", window_days: 10, severity: "all" })).investigation_id, "RISK-TEST");
  assert.equal((await client.getAskArcaScenarios()).items[0].scenario_id, "ASK-01");
  assert.equal((await client.getAskArcaCapabilities()).default_mode, "deterministic");
  assert.equal((await client.askArca({ question: "Find AWS risks", mode: "deterministic" })).execution_mode, "deterministic");
  assert.deepEqual(calls.map((item) => new URL(item.url).pathname), [
    "/api/v1/environments", "/api/v1/snowflake/changes", "/api/v1/snowflake/demo-scenarios", "/api/v1/snowflake/validate",
    "/api/v1/snowflake/execution-scenarios", "/api/v1/snowflake/execution-assurance/change", "/api/v1/snowflake/execution-assurance/user",
    "/api/v1/azure/changes", "/api/v1/azure/demo-scenarios", "/api/v1/azure/validate/change", "/api/v1/azure/validate/access",
    "/api/v1/azure/execution-scenarios", "/api/v1/azure/execution-assurance/change", "/api/v1/azure/execution-assurance/user",
    "/api/v1/aws/changes", "/api/v1/aws/demo-scenarios", "/api/v1/aws/validate/change", "/api/v1/aws/validate/access",
    "/api/v1/aws/execution-scenarios", "/api/v1/aws/execution-assurance/change", "/api/v1/aws/execution-assurance/user",
    "/api/v1/investigations/risk/scenarios", "/api/v1/investigations/risk",
    "/api/v1/agents/ask-arca/scenarios", "/api/v1/agents/ask-arca/capabilities", "/api/v1/agents/ask-arca",
  ]);
  assert.equal(calls[3].init?.method, "POST");
  assert.deepEqual(JSON.parse(String(calls[3].init?.body)), { change_id: "CHG-SF-1007", evaluation_timestamp: scenario.evaluation_timestamp });
});

test("scenario and manual change selection use API evidence", () => {
  const selection = resolveScenarioSelection([scenario], "SF-UNIFIED-01");
  assert.equal(selection?.changeId, "CHG-SF-1007");
  assert.equal(selection?.evaluationTimestamp, scenario.evaluation_timestamp);
  assert.equal(resolveChangeSelection([change], "CHG-SF-1007")?.description, change.description);
  assert.equal(resolveScenarioSelection([scenario], ""), null);
  assert.equal(resolveScenarioSelection([scenario], "missing"), undefined);
});

test("HTTP and unexpected-schema failures are actionable", async () => {
  const missing = createArcaApiClient({ fetchImpl: (async () => response({ detail: "hidden" }, 404)) as typeof fetch });
  await assert.rejects(missing.validateSnowflakeChange({ change_id: "missing" }), (error: unknown) =>
    error instanceof ArcaApiError && error.kind === "http" && error.status === 404 && !error.message.includes("hidden"));

  const malformed = createArcaApiClient({ fetchImpl: (async () => response({ result: "PASS" })) as typeof fetch });
  await assert.rejects(malformed.validateSnowflakeChange({ change_id: "CHG-SF-1007" }), (error: unknown) =>
    error instanceof ArcaApiError && error.kind === "schema");
});

test("network and timeout failures do not return synthetic fallback results", async () => {
  const offline = createArcaApiClient({ fetchImpl: (async () => { throw new TypeError("connection refused"); }) as typeof fetch });
  await assert.rejects(offline.getSnowflakeChanges(), (error: unknown) => error instanceof ArcaApiError && error.kind === "network");

  const waitsForAbort = ((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  })) as typeof fetch;
  const slow = createArcaApiClient({ fetchImpl: waitsForAbort, timeoutMs: 5 });
  await assert.rejects(slow.getSnowflakeChanges(), (error: unknown) => error instanceof ArcaApiError && error.kind === "timeout");
});

test("Agent 1-4 requests preserve explicit LLM Assisted mode", async () => {
  const bodies: Record<string, unknown>[] = [];
  const mockFetch = (async (_input: string | URL | Request, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body)));
    return response({ ...azureBase, stage: "change", overall_status: "VALID", ai_analysis: { execution_mode: "llm_assisted", llm_invoked: true, llm_status: "completed", model_identifier: "approved-model", ai_summary: "Grounded", ai_observations: [], ai_recommendations: [], evidence_references: [], limitations: [] } });
  }) as typeof fetch;
  const client = createArcaApiClient({ baseUrl: "http://arca.test", fetchImpl: mockFetch });
  const result = await client.validateAzureChange("CHG-AZ-2001", "llm_assisted");
  assert.equal(result.ai_analysis?.llm_invoked, true);
  assert.deepEqual(bodies[0], { change_id: "CHG-AZ-2001", execution_mode: "llm_assisted" });
});

test("LLM operations use a longer operation-specific timeout while retrieval stays fast", async () => {
  const delayed = ((_input: string | URL | Request, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
    const timer = setTimeout(() => resolve(response({ ...azureBase, stage: "change", overall_status: "VALID" })), 15);
    init?.signal?.addEventListener("abort", () => { clearTimeout(timer); reject(new DOMException("aborted", "AbortError")); });
  })) as typeof fetch;
  const client = createArcaApiClient({ fetchImpl: delayed, timeoutMs: 5, llmTimeoutMs: 40 });
  await assert.rejects(client.validateAzureChange("CHG-AZ-2001", "deterministic"), (error: unknown) => error instanceof ArcaApiError && error.kind === "timeout");
  assert.equal((await client.validateAzureChange("CHG-AZ-2001", "llm_assisted")).overall_status, "VALID");
});

test("improved draft client preserves empty unknown fields", async () => {
  const mockFetch = (async () => response({
    provider:"azure",change_id:"CHG-AZ-2001",draft:{change_title:"Update storage",change_number:"CHG-AZ-2001",business_justification:"",environment:"production",subscription:"sub",resource_group:"rg",resource_name_or_id:"/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/demo",implementer:"engineer@example.invalid",change_start:"2026-10-20T10:00:00Z",change_end:"2026-10-20T11:00:00Z",timezone:"UTC",required_role:"",required_access_scope:"",implementation_steps:["Update storage"],validation_plan:[],rollback_plan:"",expected_outcome:"",risk_and_impact:"moderate"},missing_fields:["business_justification","validation_plan","rollback_plan","expected_outcome"],source_evidence_ids:["sn-az-0001"],llm_invoked:false,llm_status:"not_invoked",model_identifier:null,token_usage:null,disclosure:"Source template",
  })) as typeof fetch;
  const draft=await createArcaApiClient({fetchImpl:mockFetch}).improveChangeDraft("azure","CHG-AZ-2001","deterministic");
  assert.equal(draft.draft.business_justification,"");
  assert.equal(draft.llm_invoked,false);
});
