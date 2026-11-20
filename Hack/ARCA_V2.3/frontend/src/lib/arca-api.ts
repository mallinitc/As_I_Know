import type {
  EnvironmentsResponse,
  SnowflakeChangesResponse,
  SnowflakeDemoScenariosResponse,
  SnowflakeValidationRequest,
  SnowflakeValidationResponse,
  SnowflakeChangeExecutionRequest,
  SnowflakeExecutionResponse,
  SnowflakeExecutionScenariosResponse,
  SnowflakeUserExecutionRequest,
  AzureAccessValidationResponse,
  AzureChangeValidationResponse,
  AzureChangesResponse,
  AzureDemoScenariosResponse,
  AzureChangeExecutionRequest,
  AzureExecutionResponse,
  AzureExecutionScenariosResponse,
  AzureUserExecutionRequest,
  AwsAccessValidationResponse,
  AwsChangeValidationResponse,
  AwsChangesResponse,
  AwsDemoScenariosResponse,
  AwsExecutionRequest,
  AwsExecutionResponse,
  AwsExecutionScenariosResponse,
  AwsUserExecutionRequest,
  RiskRequest,
  RiskResponse,
  RiskScenariosResponse,
  AskCapabilities,
  AskRequest,
  AskResponse,
  AskScenariosResponse,
  AnalyticsAccessResponse,
  AnalyticsExecutionResponse,
  AnalyticsFilters,
  AnalyticsOverviewResponse,
  AnalyticsRisksResponse,
  AssistanceMode,
  ChangeDraftResponse,
  Stage1ScenariosResponse,
  Stage1ValidationResult,
  Stage1DraftImproveResponse,
  Stage1ExtractedChange,
  ImprovedChangeDraft,
  Stage2ScenariosResponse,
  Stage2AssessmentRequest,
  Stage2AssessmentResponse,
  FeedbackRecord,
  FeedbackRequest,
  ObservabilityFilters,
  ObservabilityResponse,
  EvaluationRun,
  EvaluationHistoryResponse,
} from "@/types/api";
import { apiCapability, currentPersona } from "./persona.ts";

const DEFAULT_API_URL = "http://127.0.0.1:8000";
const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_LLM_TIMEOUT_MS = 55_000;

type FetchLike = typeof fetch;
type ErrorKind = "network" | "timeout" | "http" | "schema";

export class ArcaApiError extends Error {
  readonly kind: ErrorKind;
  readonly status?: number;

  constructor(message: string, kind: ErrorKind, status?: number) {
    super(message);
    this.name = "ArcaApiError";
    this.kind = kind;
    this.status = status;
  }
}

interface ClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: FetchLike;
  llmTimeoutMs?: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasString(value: Record<string, unknown>, key: string): boolean {
  return typeof value[key] === "string";
}

function hasValidExecutionMetrics(value: unknown): boolean {
  return isRecord(value) && hasString(value, "agent_id") && hasString(value, "execution_mode") &&
    hasString(value, "llm_invocation_status") && typeof value.model_call_count === "number" &&
    typeof value.model_execution_time_ms === "number" && typeof value.total_analysis_time_ms === "number" &&
    hasString(value, "cost_status") && Array.isArray(value.call_details);
}

function hasValidAiAnalysis(value: Record<string, unknown>): boolean {
  const analysis = value.ai_analysis;
  if (analysis === undefined || analysis === null) return true;
  return isRecord(analysis) && ["deterministic", "llm_assisted"].includes(String(analysis.execution_mode)) &&
    typeof analysis.llm_invoked === "boolean" && hasString(analysis, "llm_status") &&
    Array.isArray(analysis.ai_observations) && Array.isArray(analysis.ai_recommendations) &&
    Array.isArray(analysis.evidence_references) && Array.isArray(analysis.limitations) &&
    (analysis.token_usage === undefined || analysis.token_usage === null || isRecord(analysis.token_usage)) &&
    (analysis.execution_metrics === undefined || analysis.execution_metrics === null || hasValidExecutionMetrics(analysis.execution_metrics));
}

function assertEnvironments(value: unknown): asserts value is EnvironmentsResponse {
  if (!isRecord(value) || !Array.isArray(value.environments) || value.environments.some((item) =>
    !isRecord(item) || !hasString(item, "provider") || !hasString(item, "display_name") || !Array.isArray(item.capabilities)
  )) throw new ArcaApiError("The environments response did not match the ARCA API contract.", "schema");
}

function assertChanges(value: unknown): asserts value is SnowflakeChangesResponse {
  if (!isRecord(value) || value.provider !== "snowflake" || value.synthetic !== true ||
      typeof value.count !== "number" || !Array.isArray(value.items) ||
      value.items.some((item) => !isRecord(item) || !hasString(item, "change_id") || !Array.isArray(item.expected))) {
    throw new ArcaApiError("The Snowflake changes response did not match the ARCA API contract.", "schema");
  }
}

function assertScenarios(value: unknown): asserts value is SnowflakeDemoScenariosResponse {
  if (!isRecord(value) || value.provider !== "snowflake" || value.synthetic !== true ||
      typeof value.count !== "number" || !Array.isArray(value.items) ||
      value.items.some((item) => !isRecord(item) || !hasString(item, "scenario_id") ||
        !hasString(item, "scenario_name") || !hasString(item, "change_id") || !hasString(item, "evaluation_timestamp"))) {
    throw new ArcaApiError("The Snowflake scenarios response did not match the ARCA API contract.", "schema");
  }
}

function assessment(value: unknown): boolean {
  return isRecord(value) && hasString(value, "status") && Array.isArray(value.evidence) && Array.isArray(value.findings);
}

function assertValidation(value: unknown): asserts value is SnowflakeValidationResponse {
  if (!isRecord(value) || value.provider !== "snowflake" || typeof value.schema_version !== "number" ||
      !hasString(value, "change_id") || !hasString(value, "overall_status") || !hasString(value, "evaluation_timestamp") ||
      !assessment(value.change_quality) || !assessment(value.window_assessment) || !assessment(value.role_assessment) ||
      !Array.isArray(value.missing_information) || !Array.isArray(value.findings) || !Array.isArray(value.evidence) || !hasValidAiAnalysis(value)) {
    throw new ArcaApiError("The validation response did not match the ARCA API contract.", "schema");
  }
}

function assertExecutionScenarios(value: unknown): asserts value is SnowflakeExecutionScenariosResponse {
  if (!isRecord(value) || value.provider !== "snowflake" || value.synthetic !== true ||
      typeof value.count !== "number" || !Array.isArray(value.items) || value.items.some((item) =>
        !isRecord(item) || !hasString(item, "scenario_id") || !hasString(item, "scenario_name") ||
        !hasString(item, "investigation_mode") || !hasString(item, "evaluation_timestamp") ||
        !Array.isArray(item.evidence_query_ids) || !Array.isArray(item.expected_findings))) {
    throw new ArcaApiError("The execution-scenarios response did not match the ARCA API contract.", "schema");
  }
}

function assertExecution(value: unknown): asserts value is SnowflakeExecutionResponse {
  if (!isRecord(value) || value.provider !== "snowflake" || typeof value.schema_version !== "number" ||
      !hasString(value, "investigation_id") || !hasString(value, "mode") || !hasString(value, "evaluation_timestamp") ||
      !hasString(value, "period_end") || !hasString(value, "overall_status") || !hasString(value, "confidence") ||
      !Array.isArray(value.findings) || !Array.isArray(value.query_ids) || !Array.isArray(value.timeline) ||
      !Array.isArray(value.expected_operations) || !Array.isArray(value.observed_operations) ||
      !Array.isArray(value.evidence) || !Array.isArray(value.recommendations) || !Array.isArray(value.limitations) || !hasValidAiAnalysis(value)) {
    throw new ArcaApiError("The execution-assurance response did not match the ARCA API contract.", "schema");
  }
}

function assertAzureChanges(value: unknown): asserts value is AzureChangesResponse {
  if (!isRecord(value) || value.provider !== "azure" || value.synthetic !== true ||
      typeof value.count !== "number" || !Array.isArray(value.items) || value.items.some((item) =>
        !isRecord(item) || !hasString(item, "change_id") || !Array.isArray(item.expected))) {
    throw new ArcaApiError("The Azure changes response did not match the ARCA API contract.", "schema");
  }
}

function assertAzureScenarios(value: unknown): asserts value is AzureDemoScenariosResponse {
  if (!isRecord(value) || value.provider !== "azure" || value.synthetic !== true ||
      typeof value.count !== "number" || !Array.isArray(value.items) || value.items.some((item) =>
        !isRecord(item) || !hasString(item, "scenario_id") || !hasString(item, "scenario_name") ||
        !hasString(item, "stage") || !hasString(item, "change_id"))) {
    throw new ArcaApiError("The Azure scenarios response did not match the ARCA API contract.", "schema");
  }
}

function assertAzureBase(value: unknown): value is Record<string, unknown> {
  return isRecord(value) && value.provider === "azure" && typeof value.schema_version === "number" &&
    hasString(value, "change_id") && hasString(value, "stage") && hasString(value, "overall_status") &&
    Array.isArray(value.findings) && Array.isArray(value.missing_information) &&
    Array.isArray(value.evidence) && Array.isArray(value.recommendations) && isRecord(value.change) && hasValidAiAnalysis(value);
}

function assertAzureChangeValidation(value: unknown): asserts value is AzureChangeValidationResponse {
  if (!assertAzureBase(value) || value.stage !== "change") {
    throw new ArcaApiError("The Azure change-validation response did not match the ARCA API contract.", "schema");
  }
}

function assertAzureAccessValidation(value: unknown): asserts value is AzureAccessValidationResponse {
  if (!assertAzureBase(value) || value.stage !== "access" || !Array.isArray(value.pim_assessments) ||
      !Array.isArray(value.covered_operations) || !Array.isArray(value.missing_operations)) {
    throw new ArcaApiError("The Azure access-validation response did not match the ARCA API contract.", "schema");
  }
}

function assertAzureExecutionScenarios(value: unknown): asserts value is AzureExecutionScenariosResponse {
  if (!isRecord(value) || value.provider !== "azure" || value.synthetic !== true || typeof value.count !== "number" ||
      !Array.isArray(value.items) || value.items.some((item) => !isRecord(item) || !hasString(item, "scenario_id") ||
        !hasString(item, "scenario_name") || !hasString(item, "mode") || !hasString(item, "evaluation_timestamp") ||
        !Array.isArray(item.event_data_ids) || !Array.isArray(item.expected_findings))) {
    throw new ArcaApiError("The Azure execution-scenarios response did not match the ARCA API contract.", "schema");
  }
}

function assertAzureExecution(value: unknown): asserts value is AzureExecutionResponse {
  if (!isRecord(value) || value.provider !== "azure" || typeof value.schema_version !== "number" ||
      !hasString(value, "investigation_id") || !hasString(value, "mode") || !hasString(value, "evaluation_timestamp") ||
      !hasString(value, "period_end") || !hasString(value, "overall_status") || !hasString(value, "confidence") ||
      !Array.isArray(value.findings) || !Array.isArray(value.event_ids) || !Array.isArray(value.timeline) ||
      !Array.isArray(value.expected_operations) || !Array.isArray(value.observed_operations) ||
      !Array.isArray(value.evidence) || !Array.isArray(value.recommendations) || !Array.isArray(value.limitations) || !hasValidAiAnalysis(value)) {
    throw new ArcaApiError("The Azure execution-assurance response did not match the ARCA API contract.", "schema");
  }
}

function assertAwsChanges(value: unknown): asserts value is AwsChangesResponse {
  if (!isRecord(value) || value.provider !== "aws" || typeof value.synthetic !== "boolean" || typeof value.count !== "number" || !Array.isArray(value.items) || value.items.some((item) => !isRecord(item) || !hasString(item, "change_id") || !Array.isArray(item.expected))) throw new ArcaApiError("The AWS changes response did not match the ARCA API contract.", "schema");
}

function assertAwsScenarios(value: unknown): asserts value is AwsDemoScenariosResponse {
  if (!isRecord(value) || value.provider !== "aws" || typeof value.synthetic !== "boolean" || typeof value.count !== "number" || !Array.isArray(value.items) || value.items.some((item) => !isRecord(item) || !hasString(item, "scenario_id") || !hasString(item, "scenario_name") || !hasString(item, "stage") || !hasString(item, "change_id"))) throw new ArcaApiError("The AWS scenarios response did not match the ARCA API contract.", "schema");
}

function assertAwsBase(value: unknown): value is Record<string, unknown> {
  return isRecord(value) && value.provider === "aws" && typeof value.schema_version === "number" && hasString(value, "change_id") && hasString(value, "stage") && hasString(value, "overall_status") && Array.isArray(value.findings) && Array.isArray(value.missing_information) && Array.isArray(value.evidence) && Array.isArray(value.recommendations) && isRecord(value.change) && hasValidAiAnalysis(value);
}
function assertAwsChange(value: unknown): asserts value is AwsChangeValidationResponse { if (!assertAwsBase(value) || value.stage !== "change") throw new ArcaApiError("The AWS change-validation response did not match the ARCA API contract.", "schema"); }
function assertAwsAccess(value: unknown): asserts value is AwsAccessValidationResponse { if (!assertAwsBase(value) || value.stage !== "access" || !Array.isArray(value.permission_evaluations) || !Array.isArray(value.limitations)) throw new ArcaApiError("The AWS access-validation response did not match the ARCA API contract.", "schema"); }
function assertAwsExecutionScenarios(value: unknown): asserts value is AwsExecutionScenariosResponse { if (!isRecord(value) || value.provider !== "aws" || typeof value.synthetic !== "boolean" || typeof value.count !== "number" || !Array.isArray(value.items) || value.items.some((item) => !isRecord(item) || !hasString(item, "scenario_id") || !hasString(item, "mode") || !Array.isArray(item.event_ids))) throw new ArcaApiError("The AWS execution-scenarios response did not match the ARCA API contract.", "schema"); }
function assertAwsExecution(value: unknown): asserts value is AwsExecutionResponse { if (!isRecord(value) || value.provider !== "aws" || typeof value.schema_version !== "number" || !hasString(value, "investigation_id") || !hasString(value, "mode") || !hasString(value, "overall_status") || !Array.isArray(value.findings) || !Array.isArray(value.timeline) || !Array.isArray(value.event_ids) || !Array.isArray(value.limitations) || !hasValidAiAnalysis(value)) throw new ArcaApiError("The AWS execution response did not match the ARCA API contract.", "schema"); }
function assertRiskScenarios(value:unknown):asserts value is RiskScenariosResponse{if(!isRecord(value)||value.synthetic!==true||typeof value.count!=="number"||!Array.isArray(value.items)||value.items.some(x=>!isRecord(x)||!hasString(x,"scenario_id")||!hasString(x,"environment")||!Array.isArray(x.expected_findings)))throw new ArcaApiError("The risk-scenarios response did not match the ARCA API contract.","schema")}
function assertRisk(value:unknown):asserts value is RiskResponse{if(!isRecord(value)||!hasString(value,"investigation_id")||!hasString(value,"summary")||!Array.isArray(value.providers_investigated)||!Array.isArray(value.findings)||!Array.isArray(value.activity_timeline)||!isRecord(value.risk_counts)||!Array.isArray(value.evidence_limitations)||!hasValidAiAnalysis(value))throw new ArcaApiError("The risk investigation response did not match the ARCA API contract.","schema")}
function assertAskScenarios(value:unknown):asserts value is AskScenariosResponse{if(!isRecord(value)||value.synthetic!==true||typeof value.count!=="number"||!Array.isArray(value.items)||value.items.some(x=>!isRecord(x)||!hasString(x,"scenario_id")||!hasString(x,"question")))throw new ArcaApiError("The Ask ARCA scenarios response did not match the API contract.","schema")}
function assertAskCapabilities(value:unknown):asserts value is AskCapabilities{if(!isRecord(value)||!hasString(value,"default_mode")||!Array.isArray(value.modes)||!Array.isArray(value.providers)||!Array.isArray(value.tools)||!isRecord(value.llm)||typeof value.llm.available!=="boolean"||!hasString(value.llm,"status"))throw new ArcaApiError("The Ask ARCA capabilities response did not match the API contract.","schema")}
function assertAsk(value:unknown):asserts value is AskResponse{if(!isRecord(value)||!hasString(value,"investigation_id")||!hasString(value,"overall_status")||!hasString(value,"investigation_summary")||!hasString(value,"execution_mode")||!hasString(value,"llm_status")||!isRecord(value.resolved_intent)||!isRecord(value.conversation_context)||!Array.isArray(value.findings)||!Array.isArray(value.evidence_references)||!Array.isArray(value.activity_timeline)||!Array.isArray(value.tool_execution_trace)||!hasValidExecutionMetrics(value.execution_metrics))throw new ArcaApiError("The Ask ARCA response did not match the API contract.","schema")}
function assertChangeDraft(value:unknown):asserts value is ChangeDraftResponse{if(!isRecord(value)||!hasString(value,"provider")||!hasString(value,"change_id")||!isRecord(value.draft)||!Array.isArray(value.missing_fields)||!Array.isArray(value.source_evidence_ids)||typeof value.llm_invoked!=="boolean"||!hasString(value,"llm_status")||!hasString(value,"disclosure")||!hasValidExecutionMetrics(value.execution_metrics))throw new ArcaApiError("The improved-draft response did not match the API contract.","schema")}
function assertStage1Scenarios(value:unknown):asserts value is Stage1ScenariosResponse{if(!isRecord(value)||value.synthetic!==true||typeof value.count!=="number"||!Array.isArray(value.items)||value.items.some(x=>!isRecord(x)||!hasString(x,"scenario_id")||!hasString(x,"name")||!hasString(x,"text")))throw new ArcaApiError("The Stage 1 scenarios response did not match the API contract.","schema")}
function assertStage1Validation(value:unknown):asserts value is Stage1ValidationResult{if(!isRecord(value)||!hasString(value,"status")||typeof value.ready_for_submission!=="boolean"||!isRecord(value.completeness)||!isRecord(value.extracted_change)||!Array.isArray(value.issues)||!Array.isArray(value.missing_mandatory)||!Array.isArray(value.clarification_questions)||!Array.isArray(value.expected_operations))throw new ArcaApiError("The Stage 1 validation response did not match the API contract.","schema")}
function assertStage1Improve(value:unknown):asserts value is Stage1DraftImproveResponse{if(!isRecord(value)||!isRecord(value.draft)||!isRecord(value.validation)||!hasString(value,"copy_text")||typeof value.llm_invoked!=="boolean"||!hasString(value,"llm_status")||!hasValidExecutionMetrics(value.execution_metrics))throw new ArcaApiError("The Stage 1 draft response did not match the API contract.","schema")}
function assertStage2Scenarios(value:unknown):asserts value is Stage2ScenariosResponse{if(!isRecord(value)||value.provider!=="azure"||value.synthetic!==true||typeof value.count!=="number"||!Array.isArray(value.items)||value.items.some(x=>!isRecord(x)||!hasString(x,"scenario_id")||!hasString(x,"name")||!hasString(x,"mode")||!Array.isArray(x.pim_request_ids)))throw new ArcaApiError("The Stage 2 scenarios response did not match the API contract.","schema")}
function assertStage2Assessment(value:unknown):asserts value is Stage2AssessmentResponse{if(!isRecord(value)||value.provider!=="azure"||!hasString(value,"mode")||!hasString(value,"overall_assessment")||!hasString(value,"risk_classification")||!hasString(value,"evaluation_timestamp")||!Array.isArray(value.records)||!Array.isArray(value.assessments)||!Array.isArray(value.findings)||!Array.isArray(value.missing_information)||!Array.isArray(value.recommendations)||!Array.isArray(value.evidence)||!hasValidAiAnalysis(value))throw new ArcaApiError("The Stage 2 assessment response did not match the API contract.","schema")}
function analyticsBase(value:unknown):value is Record<string,unknown>{return isRecord(value)&&isRecord(value.metadata)&&value.metadata.synthetic===true&&hasString(value.metadata,"reference_timestamp")}
function assertAnalyticsOverview(value:unknown):asserts value is AnalyticsOverviewResponse{if(!analyticsBase(value)||typeof value.total_unique_changes!=="number"||typeof value.high_risk_findings!=="number"||typeof value.potentially_undocumented_changes!=="number"||!Array.isArray(value.findings_by_severity)||!Array.isArray(value.recent_significant_findings)||!Array.isArray(value.undocumented_activity))throw new ArcaApiError("The analytics overview response did not match the API contract.","schema")}
function assertAnalyticsRisks(value:unknown):asserts value is AnalyticsRisksResponse{if(!analyticsBase(value)||typeof value.total_findings!=="number"||!Array.isArray(value.findings_by_provider)||!Array.isArray(value.findings_by_category)||!Array.isArray(value.findings_over_time))throw new ArcaApiError("The analytics risk response did not match the API contract.","schema")}
function assertAnalyticsExecution(value:unknown):asserts value is AnalyticsExecutionResponse{if(!analyticsBase(value)||!isRecord(value.summary)||!Array.isArray(value.categories)||!isRecord(value.evidence_coverage))throw new ArcaApiError("The analytics execution response did not match the API contract.","schema")}
function assertAnalyticsAccess(value:unknown):asserts value is AnalyticsAccessResponse{if(!analyticsBase(value)||typeof value.access_risk_findings!=="number"||!Array.isArray(value.categories)||!Array.isArray(value.provider_counts))throw new ArcaApiError("The analytics access response did not match the API contract.","schema")}
function assertFeedback(value:unknown):asserts value is FeedbackRecord{if(!isRecord(value)||!hasString(value,"feedback_id")||!hasString(value,"assessment_id")||!hasString(value,"feedback_decision")||!hasString(value,"timestamp_utc"))throw new ArcaApiError("The feedback response did not match the API contract.","schema")}
function assertLatestFeedback(value:unknown):asserts value is {item:FeedbackRecord|null}{if(!isRecord(value)||!(value.item===null||isRecord(value.item)))throw new ArcaApiError("The saved feedback response did not match the API contract.","schema")}
function assertObservability(value:unknown):asserts value is ObservabilityResponse{if(!isRecord(value)||!isRecord(value.metadata)||!isRecord(value.summary)||!isRecord(value.performance)||!Array.isArray(value.llm_by_agent)||!Array.isArray(value.feedback_by_stage)||!Array.isArray(value.recent_executions)||!Array.isArray(value.recent_feedback))throw new ArcaApiError("The observability response did not match the API contract.","schema")}
function assertEvaluationRun(value:unknown):asserts value is EvaluationRun{if(!isRecord(value)||!hasString(value,"status")||!hasString(value,"evaluation_mode")||typeof value.live_llm_calls!=="number")throw new ArcaApiError("The evaluation response did not match the API contract.","schema")}
function assertEvaluationHistory(value:unknown):asserts value is EvaluationHistoryResponse{if(!isRecord(value)||!Array.isArray(value.items))throw new ArcaApiError("The evaluation history did not match the API contract.","schema")}

function analyticsQuery(filters: AnalyticsFilters): string {
  const query = new URLSearchParams({ provider: filters.provider, severity: filters.severity });
  if (filters.days !== null) query.set("days", String(filters.days));
  return `?${query.toString()}`;
}
function observabilityQuery(filters:ObservabilityFilters):string{const query=new URLSearchParams(Object.entries(filters).map(([key,value])=>[key,String(value)]));return`?${query.toString()}`}

function httpMessage(status: number, path: string): string {
  const provider = path.includes("/azure/") || path.includes("/access-intelligence/stage2/") ? "Azure" : path.includes("/aws/") ? "AWS" : path.includes("/snowflake/") ? "Snowflake" : "requested";
  if (status === 404 && path.includes("demo-scenarios")) return `The ${provider} demo scenarios endpoint was not found. Restart the ARCA API and try again.`;
  if (status === 404) return `The selected ${provider} record was not found. Refresh the evidence and try again.`;
  if (status === 422) return "The validation request was rejected. Check the change and evaluation timestamp.";
  if (status >= 500) return "The ARCA validation service could not complete the request. Try again or contact the platform team.";
  return `The ARCA API returned an unexpected status (${status}).`;
}

export function createArcaApiClient(options: ClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? process.env.NEXT_PUBLIC_ARCA_API_URL ?? DEFAULT_API_URL).replace(/\/$/, "");
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const llmTimeoutMs = options.llmTimeoutMs ?? Number(process.env.NEXT_PUBLIC_ARCA_LLM_TIMEOUT_MS || DEFAULT_LLM_TIMEOUT_MS);
  const fetchImpl = options.fetchImpl ?? fetch;

  async function request<T>(path: string, validate: (value: unknown) => asserts value is T, init?: RequestInit, operationTimeoutMs = timeoutMs): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), operationTimeoutMs);
    try {
      const response = await fetchImpl(`${baseUrl}${path}`, {
        ...init,
        headers: { Accept: "application/json", "X-ARCA-Demo-Role":currentPersona(), ...(apiCapability(path)?{"X-ARCA-Capability":apiCapability(path)!}:{}), ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
        signal: controller.signal,
      });
      if (!response.ok) throw new ArcaApiError(httpMessage(response.status, path), "http", response.status);
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        throw new ArcaApiError("The ARCA API returned unreadable data.", "schema");
      }
      validate(payload);
      return payload;
    } catch (error) {
      if (error instanceof ArcaApiError) throw error;
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ArcaApiError(`The ARCA API did not respond within ${Math.ceil(operationTimeoutMs / 1000)} seconds.`, "timeout");
      }
      throw new ArcaApiError(`Unable to reach the ARCA API at ${baseUrl}. Confirm the backend is running.`, "network");
    } finally {
      clearTimeout(timeout);
    }
  }

  return {
    getEnvironments: () => request("/api/v1/environments", assertEnvironments),
    getSnowflakeChanges: () => request("/api/v1/snowflake/changes", assertChanges),
    getSnowflakeDemoScenarios: () => request("/api/v1/snowflake/demo-scenarios", assertScenarios),
    validateSnowflakeChange: (payload: SnowflakeValidationRequest) => request(
      "/api/v1/snowflake/validate",
      assertValidation,
      { method: "POST", body: JSON.stringify(payload) }, payload.execution_mode === "llm_assisted" ? llmTimeoutMs : timeoutMs,
    ),
    getSnowflakeExecutionScenarios: () => request(
      "/api/v1/snowflake/execution-scenarios", assertExecutionScenarios,
    ),
    assureSnowflakeChangeExecution: (payload: SnowflakeChangeExecutionRequest) => request(
      "/api/v1/snowflake/execution-assurance/change", assertExecution,
      { method: "POST", body: JSON.stringify(payload) }, payload.execution_mode === "llm_assisted" ? llmTimeoutMs : timeoutMs,
    ),
    assureSnowflakeUserExecution: (payload: SnowflakeUserExecutionRequest) => request(
      "/api/v1/snowflake/execution-assurance/user", assertExecution,
      { method: "POST", body: JSON.stringify(payload) }, payload.execution_mode === "llm_assisted" ? llmTimeoutMs : timeoutMs,
    ),
    getAzureChanges: () => request("/api/v1/azure/changes", assertAzureChanges),
    getAzureDemoScenarios: () => request("/api/v1/azure/demo-scenarios", assertAzureScenarios),
    validateAzureChange: (changeId: string, executionMode: AssistanceMode = "deterministic") => request(
      "/api/v1/azure/validate/change", assertAzureChangeValidation,
      { method: "POST", body: JSON.stringify({ change_id: changeId, execution_mode: executionMode }) }, executionMode === "llm_assisted" ? llmTimeoutMs : timeoutMs,
    ),
    validateAzureAccess: (changeId: string, executionMode: AssistanceMode = "deterministic") => request(
      "/api/v1/azure/validate/access", assertAzureAccessValidation,
      { method: "POST", body: JSON.stringify({ change_id: changeId, execution_mode: executionMode }) }, executionMode === "llm_assisted" ? llmTimeoutMs : timeoutMs,
    ),
    getAzureExecutionScenarios: () => request(
      "/api/v1/azure/execution-scenarios", assertAzureExecutionScenarios,
    ),
    assureAzureChangeExecution: (payload: AzureChangeExecutionRequest) => request(
      "/api/v1/azure/execution-assurance/change", assertAzureExecution,
      { method: "POST", body: JSON.stringify(payload) }, payload.execution_mode === "llm_assisted" ? llmTimeoutMs : timeoutMs,
    ),
    assureAzureUserExecution: (payload: AzureUserExecutionRequest) => request(
      "/api/v1/azure/execution-assurance/user", assertAzureExecution,
      { method: "POST", body: JSON.stringify(payload) }, payload.execution_mode === "llm_assisted" ? llmTimeoutMs : timeoutMs,
    ),
    getAwsChanges: () => request("/api/v1/aws/changes", assertAwsChanges),
    getAwsDemoScenarios: () => request("/api/v1/aws/demo-scenarios", assertAwsScenarios),
    validateAwsChange: (changeId: string, executionMode: AssistanceMode = "deterministic") => request("/api/v1/aws/validate/change", assertAwsChange, { method: "POST", body: JSON.stringify({ change_id: changeId, execution_mode: executionMode }) }, executionMode === "llm_assisted" ? llmTimeoutMs : timeoutMs),
    validateAwsAccess: (changeId: string, executionMode: AssistanceMode = "deterministic") => request("/api/v1/aws/validate/access", assertAwsAccess, { method: "POST", body: JSON.stringify({ change_id: changeId, execution_mode: executionMode }) }, executionMode === "llm_assisted" ? llmTimeoutMs : timeoutMs),
    getAwsExecutionScenarios: () => request("/api/v1/aws/execution-scenarios", assertAwsExecutionScenarios),
    assureAwsChangeExecution: (payload: AwsExecutionRequest) => request("/api/v1/aws/execution-assurance/change", assertAwsExecution, { method: "POST", body: JSON.stringify(payload) }, payload.execution_mode === "llm_assisted" ? llmTimeoutMs : timeoutMs),
    assureAwsUserExecution: (payload: AwsUserExecutionRequest) => request("/api/v1/aws/execution-assurance/user", assertAwsExecution, { method: "POST", body: JSON.stringify(payload) }, payload.execution_mode === "llm_assisted" ? llmTimeoutMs : timeoutMs),
    getRiskScenarios:()=>request("/api/v1/investigations/risk/scenarios",assertRiskScenarios),
    investigateRisk:(payload:RiskRequest)=>request("/api/v1/investigations/risk",assertRisk,{method:"POST",body:JSON.stringify(payload)},payload.execution_mode==="llm_assisted"?llmTimeoutMs:timeoutMs),
    getAskArcaScenarios:()=>request("/api/v1/agents/ask-arca/scenarios",assertAskScenarios),
    getAskArcaCapabilities:()=>request("/api/v1/agents/ask-arca/capabilities",assertAskCapabilities),
    askArca:(payload:AskRequest)=>request("/api/v1/agents/ask-arca",assertAsk,{method:"POST",body:JSON.stringify(payload)},payload.mode==="llm_assisted"||payload.mode==="ai"?llmTimeoutMs:timeoutMs),
    improveChangeDraft:(provider:"aws"|"azure"|"snowflake",changeId:string,executionMode:AssistanceMode)=>request("/api/v1/agents/change-quality/improve-draft",assertChangeDraft,{method:"POST",body:JSON.stringify({provider,change_id:changeId,execution_mode:executionMode})},executionMode==="llm_assisted"?llmTimeoutMs:timeoutMs),
    getStage1Scenarios:(provider:"aws"|"azure")=>request(`/api/v1/agents/change-quality/stage1/demo-scenarios?provider=${provider}`,assertStage1Scenarios),
    validateStage1Draft:(provider:"aws"|"azure",text:string,overrides:Record<string,string>)=>request("/api/v1/agents/change-quality/stage1/validate-draft",assertStage1Validation,{method:"POST",body:JSON.stringify({provider,text,overrides})}),
    revalidateStage1Draft:(draft:ImprovedChangeDraft)=>request("/api/v1/agents/change-quality/stage1/revalidate-draft",assertStage1Validation,{method:"POST",body:JSON.stringify({draft})}),
    improveStage1Draft:(extractedChange:Stage1ExtractedChange,executionMode:AssistanceMode)=>request("/api/v1/agents/change-quality/stage1/improve-draft",assertStage1Improve,{method:"POST",body:JSON.stringify({extracted_change:extractedChange,execution_mode:executionMode})},executionMode==="llm_assisted"?llmTimeoutMs:timeoutMs),
    getStage2Scenarios:()=>request("/api/v1/agents/access-intelligence/stage2/demo-scenarios",assertStage2Scenarios),
    getStage2ScenarioRecords:(requestIds:string[])=>request(`/api/v1/agents/access-intelligence/stage2/scenario-records?request_ids=${encodeURIComponent(requestIds.join(","))}`,(value:unknown):asserts value is {records_text:string}=>{if(!isRecord(value)||!hasString(value,"records_text"))throw new ArcaApiError("The Stage 2 records response did not match the API contract.","schema")}),
    assessStage2:(payload:Stage2AssessmentRequest)=>request("/api/v1/agents/access-intelligence/stage2/assess",assertStage2Assessment,{method:"POST",body:JSON.stringify(payload)},payload.execution_mode==="llm_assisted"?llmTimeoutMs:timeoutMs),
    getAnalyticsOverview:(filters:AnalyticsFilters)=>request(`/api/v1/analytics/overview${analyticsQuery(filters)}`,assertAnalyticsOverview),
    getAnalyticsRisks:(filters:AnalyticsFilters)=>request(`/api/v1/analytics/risks${analyticsQuery(filters)}`,assertAnalyticsRisks),
    getAnalyticsExecution:(filters:AnalyticsFilters)=>request(`/api/v1/analytics/execution${analyticsQuery(filters)}`,assertAnalyticsExecution),
    getAnalyticsAccess:(filters:AnalyticsFilters)=>request(`/api/v1/analytics/access${analyticsQuery(filters)}`,assertAnalyticsAccess),
    getObservability:(filters:ObservabilityFilters)=>request(`/api/v1/analytics/observability${observabilityQuery(filters)}`,assertObservability),
    getLatestEvaluation:()=>request("/api/v1/analytics/evaluation/latest",assertEvaluationRun),
    getEvaluationHistory:()=>request("/api/v1/analytics/evaluation/history",assertEvaluationHistory),
    runEvaluation:()=>request("/api/v1/analytics/evaluation/runs",assertEvaluationRun,{method:"POST",body:JSON.stringify({mode:"deterministic_and_mocked_llm"})}),
    getEvaluationRun:(runId:string)=>request(`/api/v1/analytics/evaluation/runs/${encodeURIComponent(runId)}`,assertEvaluationRun),
    submitFeedback:(payload:FeedbackRequest)=>request("/api/v1/analytics/feedback",assertFeedback,{method:"POST",body:JSON.stringify(payload)}),
    getLatestFeedback:(assessmentId:string,stage:FeedbackRequest["stage"]="A5")=>request(`/api/v1/analytics/feedback/latest?assessment_id=${encodeURIComponent(assessmentId)}&stage=${stage}`,assertLatestFeedback),
  };
}

const client = createArcaApiClient();
export const getEnvironments = client.getEnvironments;
export const getSnowflakeChanges = client.getSnowflakeChanges;
export const getSnowflakeDemoScenarios = client.getSnowflakeDemoScenarios;
export const validateSnowflakeChange = client.validateSnowflakeChange;
export const getSnowflakeExecutionScenarios = client.getSnowflakeExecutionScenarios;
export const assureSnowflakeChangeExecution = client.assureSnowflakeChangeExecution;
export const assureSnowflakeUserExecution = client.assureSnowflakeUserExecution;
export const getAzureChanges = client.getAzureChanges;
export const getAzureDemoScenarios = client.getAzureDemoScenarios;
export const validateAzureChange = client.validateAzureChange;
export const validateAzureAccess = client.validateAzureAccess;
export const getAzureExecutionScenarios = client.getAzureExecutionScenarios;
export const assureAzureChangeExecution = client.assureAzureChangeExecution;
export const assureAzureUserExecution = client.assureAzureUserExecution;
export const getAwsChanges = client.getAwsChanges;
export const getAwsDemoScenarios = client.getAwsDemoScenarios;
export const validateAwsChange = client.validateAwsChange;
export const validateAwsAccess = client.validateAwsAccess;
export const getAwsExecutionScenarios = client.getAwsExecutionScenarios;
export const assureAwsChangeExecution = client.assureAwsChangeExecution;
export const assureAwsUserExecution = client.assureAwsUserExecution;
export const getRiskScenarios=client.getRiskScenarios;
export const investigateRisk=client.investigateRisk;
export const getAskArcaScenarios=client.getAskArcaScenarios;
export const getAskArcaCapabilities=client.getAskArcaCapabilities;
export const askArca=client.askArca;
export const improveChangeDraft=client.improveChangeDraft;
export const getStage1Scenarios=client.getStage1Scenarios;
export const validateStage1Draft=client.validateStage1Draft;
export const revalidateStage1Draft=client.revalidateStage1Draft;
export const improveStage1Draft=client.improveStage1Draft;
export const getStage2Scenarios=client.getStage2Scenarios;
export const getStage2ScenarioRecords=client.getStage2ScenarioRecords;
export const assessStage2=client.assessStage2;
export const getAnalyticsOverview=client.getAnalyticsOverview;
export const getAnalyticsRisks=client.getAnalyticsRisks;
export const getAnalyticsExecution=client.getAnalyticsExecution;
export const getAnalyticsAccess=client.getAnalyticsAccess;
export const getObservability=client.getObservability;
export const getLatestEvaluation=client.getLatestEvaluation;
export const getEvaluationHistory=client.getEvaluationHistory;
export const runEvaluation=client.runEvaluation;
export const getEvaluationRun=client.getEvaluationRun;
export const submitFeedback=client.submitFeedback;
export const getLatestFeedback=client.getLatestFeedback;
