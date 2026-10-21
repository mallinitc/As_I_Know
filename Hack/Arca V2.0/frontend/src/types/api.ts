export interface EnvironmentCapability {
  provider: string;
  display_name: string;
  capabilities: string[];
}

export interface EnvironmentsResponse {
  environments: EnvironmentCapability[];
}
export type AssistanceMode = "deterministic" | "llm_assisted";
export interface ImprovedChangeDraft {
  change_title:string; change_number:string; business_justification:string; environment:string;
  subscription:string; resource_group:string; resource_name_or_id:string; implementer:string;
  change_start:string; change_end:string; timezone:string; required_role:string; required_access_scope:string;
  implementation_steps:string[]; validation_plan:string[]; rollback_plan:string; expected_outcome:string; risk_and_impact:string;
}
export interface ChangeDraftResponse { provider:"aws"|"azure"|"snowflake"; change_id:string; draft:ImprovedChangeDraft; missing_fields:string[]; source_evidence_ids:string[]; llm_invoked:boolean; llm_status:string; model_identifier:string|null; token_usage:Record<string,number>|null; disclosure:string }
export interface AiAnalysis { execution_mode: AssistanceMode; llm_invoked: boolean; llm_status: string; model_identifier: string | null; ai_summary: string | null; ai_observations: string[]; ai_recommendations: string[]; evidence_references: string[]; limitations: string[]; token_usage?:Record<string,number>|null }
export type RiskEnvironment="all"|"aws"|"azure"|"snowflake";
export type RiskSeverity="all"|"critical"|"high"|"medium"|"low";
export interface RiskScenario { scenario_id:string; scenario_name:string; environment:RiskEnvironment; evaluation_timestamp:string; window_days:number; identity?:string|null; role?:string|null; resource?:string|null; severity:RiskSeverity; expected_providers:string[]; expected_findings:string[] }
export interface RiskScenariosResponse { synthetic:true; count:number; items:RiskScenario[] }
export interface RiskRequest { environment:RiskEnvironment; identity?:string; role?:string; resource?:string; window_days:ExecutionWindowDays; severity:RiskSeverity; evaluation_timestamp?:string; scenario_id?:string; execution_mode?:AssistanceMode }
export interface RiskFinding { finding_id:string; provider:string; category:string; severity:string; confidence:string; summary:string; actor?:string|null; role?:string|null; resource?:string|null; timestamp?:string|null; change_id?:string|null; evidence_ids:string[]; recommendation:string }
export interface RiskResponse { investigation_id:string; providers_investigated:string[]; period_start:string; period_end:string; summary:string; risk_counts:Record<string,number>; findings:RiskFinding[]; evidence_references:Record<string,unknown>[]; activity_timeline:Record<string,unknown>[]; confidence:string; evidence_limitations:string[]; ai_analysis?:AiAnalysis|null }
export interface AskScenario { scenario_id:string; scenario_name:string; question:string; evaluation_timestamp:string; expected_intent:string; expected_providers:string[] }
export interface AskScenariosResponse { synthetic:true; count:number; items:AskScenario[] }
export interface AskLlmCapability { enabled:boolean; available:boolean; provider:string|null; model_identifier:string|null; status:string }
export interface AskCapabilities { default_mode:string; modes:string[]; providers:string[]; tools:{name:string;description:string}[]; supported_periods:string[]; llm:AskLlmCapability }
export interface AskRequest { question:string; mode?:"mock"|"ai"|"deterministic"|"llm_assisted"; evaluation_timestamp?:string; scenario_id?:string }
export interface AskTrace { step_id:string; tool_name:string; status:string; start_time:string; end_time:string; duration:number; summary:string }
export interface AskResponse { investigation_id:string; original_question:string; resolved_intent:Record<string,unknown>; providers_investigated:string[]; execution_mode:string; overall_status:string; investigation_summary:string; findings:Record<string,unknown>[]; evidence_references:Record<string,unknown>[]; activity_timeline:Record<string,unknown>[]; tool_execution_trace:AskTrace[]; confidence:string; evidence_limitations:string[]; recommended_actions:string[]; clarification_request?:string|null; llm_provider:string|null; llm_status:string; model_identifier:string|null; token_usage:Record<string,number>|null; model_generated_explanation:string|null; llm_evidence_citations:string[]; llm_error:string|null }

export interface AwsExpectedOperation { eventName?: string; resource?: string; [key: string]: unknown }
export interface AwsChange { change_id: string; environment: string; actor: string; state?: string | null; start?: string | null; end?: string | null; description: string; expected: AwsExpectedOperation[]; [key: string]: unknown }
export interface AwsChangesResponse { provider: "aws"; evidence_source: string; synthetic: true; count: number; items: AwsChange[] }
export interface AwsDemoScenario { scenario_id: string; scenario_name: string; stage: "change" | "access"; change_id: string; expected_status?: string | null; expected_findings: string[] }
export interface AwsDemoScenariosResponse { provider: "aws"; synthetic: true; count: number; items: AwsDemoScenario[] }
export interface AwsFinding { category: string; field: string; severity: string; explanation: string; actual: unknown; expected: unknown; recommendation: string; evidence_ids: string[] }
export interface AwsChangeValidationResponse { schema_version: number; provider: "aws"; stage: "change"; change_id: string; overall_status: string; findings: AwsFinding[]; missing_information: string[]; recommendations: string[]; evidence: Record<string, unknown>[]; change: AwsChange; ai_analysis?:AiAnalysis|null }
export interface AwsPermissionEvaluation { event_name: string; iam_action?: string | null; resource?: string | null; decision: string; allow_evidence: string[]; deny_evidence: string[] }
export interface AwsAccessValidationResponse { schema_version: number; provider: "aws"; stage: "access"; change_id: string; overall_status: string; permission_evaluations: AwsPermissionEvaluation[]; findings: AwsFinding[]; missing_information: string[]; recommendations: string[]; evidence: Record<string, unknown>[]; limitations: string[]; change: AwsChange; access_request?: Record<string, unknown> | null; ai_analysis?:AiAnalysis|null }
export interface AwsExecutionScenario { scenario_id: string; scenario_name: string; mode: ExecutionMode; change_id: string | null; user_identity: string | null; evaluation_timestamp: string; window_days: number; event_ids: string[]; expected_findings: string[] }
export interface AwsExecutionScenariosResponse { provider: "aws"; synthetic: true; count: number; items: AwsExecutionScenario[] }
export interface AwsExecutionRequest { change_id: string; evaluation_timestamp?: string; scenario_id?: string; execution_mode?:AssistanceMode }
export interface AwsUserExecutionRequest { user_identity: string; window_days: ExecutionWindowDays; evaluation_timestamp?: string; scenario_id?: string; execution_mode?:AssistanceMode }
export interface AwsExecutionFinding { category: string; severity: string; confidence: "confirmed" | "possible" | "insufficient"; message: string; event_ids: string[]; change_id: string | null; recommendation: string }
export interface AwsObservedActivity { event_id: string; event_time: string; event_source?: string; operation: string; actor: string; principal_arn?: string | null; resources: string[]; aws_region?: string; account_id?: string; status: string; change_id?: string | null; change_match: "MATCHED" | "POSSIBLE_MATCH" | "UNMATCHED"; deviations: string[] }
export interface AwsExecutionResponse { schema_version: number; investigation_id: string; provider: "aws"; mode: ExecutionMode; change_id: string | null; user: Record<string, unknown> | null; evaluation_timestamp: string; period_start: string | null; period_end: string; overall_status: string; findings: AwsExecutionFinding[]; event_ids: string[]; confidence: string; timeline: AwsObservedActivity[]; expected_operations: AwsExpectedOperation[]; observed_operations: AwsObservedActivity[]; evidence: Record<string, unknown>[]; recommendations: string[]; limitations: string[]; ai_analysis?:AiAnalysis|null }

export interface SnowflakeExpectedOperation {
  operation?: string;
  resource_id?: string;
  [key: string]: unknown;
}

export interface SnowflakeContext {
  account?: string | null;
  database?: string | null;
  schema?: string | null;
  object_type?: string | null;
  object_name?: string | null;
  requested_role?: string | null;
  [key: string]: unknown;
}

export interface SnowflakeChange {
  change_id: string;
  provider: string;
  short_description: string;
  description: string;
  state: string;
  environment: string;
  start: string | null;
  end: string | null;
  implementer?: string;
  expected: SnowflakeExpectedOperation[];
  snowflake_context?: SnowflakeContext;
  [key: string]: unknown;
}

export interface SnowflakeChangesResponse {
  provider: "snowflake";
  evidence_source: string;
  synthetic: true;
  count: number;
  items: SnowflakeChange[];
}

export interface SnowflakeDemoScenario {
  scenario_id: string;
  scenario_name: string;
  description: string;
  change_id: string;
  evaluation_timestamp: string;
  expected_check_outcomes: Record<string, string>;
  [key: string]: unknown;
}

export interface SnowflakeDemoScenariosResponse {
  provider: "snowflake";
  synthetic: true;
  count: number;
  items: SnowflakeDemoScenario[];
}

export interface AssessmentSection {
  status: string;
  evidence: unknown[];
  findings: unknown[];
  explanation?: string;
  recommended_role?: string | null;
  requested_role?: string;
  required_privileges?: unknown[];
  effective_privileges?: unknown[];
  missing_privileges?: unknown[];
  approved_start?: string | null;
  approved_end?: string | null;
  evaluation_timestamp?: string;
  [key: string]: unknown;
}

export interface SnowflakeValidationRequest {
  change_id: string;
  evaluation_timestamp?: string;
  execution_mode?: AssistanceMode;
}

export interface SnowflakeValidationResponse {
  schema_version: number;
  change_id: string;
  provider: "snowflake";
  status: string;
  overall_status: string;
  change_quality: AssessmentSection;
  window_assessment: AssessmentSection;
  role_assessment: AssessmentSection;
  missing_information: string[];
  findings: Record<string, unknown>[];
  evidence: unknown[];
  evaluation_timestamp: string;
  warning?: string | null;
  ai_analysis?: AiAnalysis | null;
  [key: string]: unknown;
}

export type ExecutionMode = "change" | "user";
export type ExecutionWindowDays = 1 | 7 | 10 | 15 | 30;

export interface SnowflakeExecutionScenario {
  scenario_id: string;
  scenario_name: string;
  change_id: string | null;
  user_identity: string | null;
  evaluation_timestamp: string;
  investigation_mode: ExecutionMode;
  evidence_query_ids: string[];
  window_days: number;
  expected_findings: string[];
}

export interface SnowflakeExecutionScenariosResponse {
  provider: "snowflake";
  synthetic: true;
  count: number;
  items: SnowflakeExecutionScenario[];
}

export interface SnowflakeChangeExecutionRequest {
  change_id: string;
  evaluation_timestamp?: string;
  scenario_id?: string;
  execution_mode?: AssistanceMode;
}

export interface SnowflakeUserExecutionRequest {
  user_identity: string;
  window_days: ExecutionWindowDays;
  evaluation_timestamp?: string;
  scenario_id?: string;
  execution_mode?: AssistanceMode;
}

export interface SnowflakeExecutionFinding {
  category: string;
  severity: string;
  confidence: "confirmed" | "possible" | "insufficient";
  message: string;
  query_ids: string[];
  change_id: string | null;
}

export interface SnowflakeObservedOperation {
  query_id: string;
  operation?: string | null;
  target?: string | null;
  actor?: string | null;
  role?: string | null;
  timestamp?: string | null;
  status?: string | null;
  change_id?: string | null;
}

export interface SnowflakeExecutionResponse {
  schema_version: number;
  investigation_id: string;
  provider: "snowflake";
  mode: ExecutionMode;
  change_id: string | null;
  user: Record<string, unknown> | null;
  evaluation_timestamp: string;
  period_start: string | null;
  period_end: string;
  overall_status: string;
  findings: SnowflakeExecutionFinding[];
  query_ids: string[];
  confidence: string;
  timeline: SnowflakeObservedOperation[];
  expected_operations: SnowflakeExpectedOperation[];
  observed_operations: SnowflakeObservedOperation[];
  evidence: Record<string, unknown>[];
  recommendations: string[];
  limitations: string[];
  ai_analysis?: AiAnalysis | null;
}

export type AzureValidationStage = "change" | "access";

export interface AzureChange {
  change_id: string;
  provider: "azure";
  environment: string;
  description: string;
  state: string;
  implementer: { principal_id?: string; principal_name?: string; principal_type?: string } | null;
  start: string | null;
  end: string | null;
  expected: SnowflakeExpectedOperation[];
  scenario?: string;
  [key: string]: unknown;
}

export interface AzureChangesResponse {
  provider: "azure";
  evidence_source: string;
  synthetic: true;
  count: number;
  items: AzureChange[];
}

export interface AzureDemoScenario {
  scenario_id: string;
  scenario_name: string;
  stage: AzureValidationStage;
  change_id: string;
  description: string;
  source_scenario: string;
}

export interface AzureDemoScenariosResponse {
  provider: "azure";
  synthetic: true;
  count: number;
  items: AzureDemoScenario[];
}

export interface AzureFinding {
  category: string;
  field: string;
  severity: string;
  message: string;
  actual: unknown;
  expected: unknown;
  recommendation: string;
  evidence_ids: string[];
}

export interface AzureChangeValidationResponse {
  schema_version: number;
  provider: "azure";
  stage: "change";
  change_id: string;
  overall_status: string;
  findings: AzureFinding[];
  missing_information: string[];
  evidence: Record<string, unknown>[];
  recommendations: string[];
  change: AzureChange;
  ai_analysis?: AiAnalysis | null;
}

export interface AzurePimAssessment {
  pim_request_id: string;
  overall_status: string;
  supported_operations: SnowflakeExpectedOperation[];
  findings: AzureFinding[];
  evidence_ids: string[];
}

export interface AzureAccessValidationResponse {
  schema_version: number;
  provider: "azure";
  stage: "access";
  change_id: string;
  overall_status: string;
  pim_assessments: AzurePimAssessment[];
  covered_operations: SnowflakeExpectedOperation[];
  missing_operations: SnowflakeExpectedOperation[];
  findings: AzureFinding[];
  missing_information: string[];
  recommendations: string[];
  evidence: Record<string, unknown>[];
  change: AzureChange;
  ai_analysis?: AiAnalysis | null;
}

export interface AzureExecutionScenario {
  scenario_id: string;
  scenario_name: string;
  mode: ExecutionMode;
  change_id: string | null;
  user_identity: string | null;
  evaluation_timestamp: string;
  window_days: number;
  event_data_ids: string[];
  expected_findings: string[];
}

export interface AzureExecutionScenariosResponse {
  provider: "azure";
  synthetic: true;
  count: number;
  items: AzureExecutionScenario[];
}

export interface AzureChangeExecutionRequest {
  change_id: string;
  evaluation_timestamp?: string;
  scenario_id?: string;
  execution_mode?: AssistanceMode;
}

export interface AzureUserExecutionRequest {
  user_identity: string;
  window_days: ExecutionWindowDays;
  evaluation_timestamp?: string;
  scenario_id?: string;
  execution_mode?: AssistanceMode;
}

export interface AzureExecutionFinding {
  category: string;
  severity: string;
  confidence: "confirmed" | "possible" | "insufficient";
  message: string;
  event_ids: string[];
  change_id: string | null;
  recommendation: string;
}

export interface AzureObservedActivity {
  event_data_id: string;
  event_timestamp: string;
  caller: string;
  caller_principal_id: string;
  operation: string;
  resource_id: string;
  correlation_id: string;
  status: string;
  sub_status?: string | null;
  change_id?: string | null;
  change_match: "MATCHED" | "POSSIBLE_MATCH" | "UNMATCHED";
  deviations: string[];
}

export interface AzureExecutionResponse {
  schema_version: number;
  investigation_id: string;
  provider: "azure";
  mode: ExecutionMode;
  change_id: string | null;
  user: Record<string, unknown> | null;
  evaluation_timestamp: string;
  period_start: string | null;
  period_end: string;
  overall_status: string;
  findings: AzureExecutionFinding[];
  event_ids: string[];
  confidence: string;
  timeline: AzureObservedActivity[];
  expected_operations: SnowflakeExpectedOperation[];
  observed_operations: AzureObservedActivity[];
  evidence: Record<string, unknown>[];
  recommendations: string[];
  limitations: string[];
  ai_analysis?: AiAnalysis | null;
}

export type AnalyticsProvider = "all" | "aws" | "azure" | "snowflake";
export type AnalyticsSeverity = "all" | "critical" | "high" | "medium" | "low";
export interface AnalyticsFilters { provider: AnalyticsProvider; days: 7 | 15 | 30 | null; severity: AnalyticsSeverity }
export interface AnalyticsMetadata { synthetic: true; dataset_label: string; reference_timestamp: string; provider: AnalyticsProvider; days: number | null; severity: AnalyticsSeverity; metric_definitions: Record<string, string>; limitations: string[] }
export interface AnalyticsDistribution { name: string; value: number }
export interface AnalyticsTrend { date: string; findings: number; assessments: number }
export interface AnalyticsSummary { compliant: number; noncompliant: number; review_or_unknown: number; denominator: number }
export interface AnalyticsFinding { finding_id: string; provider: "aws" | "azure" | "snowflake"; domain: "change" | "access" | "execution"; category: string; severity: Exclude<AnalyticsSeverity, "all">; summary: string; timestamp: string | null; change_id: string | null; evidence_ids: string[]; resource: string | null; route: string | null }
export interface AnalyticsOverviewResponse { metadata: AnalyticsMetadata; total_unique_changes: number; approved_changes: number; noncompliant_changes: number; changes_requiring_review: number; compliance_rate: number | null; compliance_denominator: number; high_risk_findings: number; execution_deviations: number; potentially_unapproved_activities: number; provider_risk_counts: AnalyticsDistribution[]; findings_by_severity: AnalyticsDistribution[]; findings_over_time: AnalyticsTrend[]; change_assurance: AnalyticsSummary; execution_assurance: AnalyticsSummary; recent_significant_findings: AnalyticsFinding[] }
export interface AnalyticsRisksResponse { metadata: AnalyticsMetadata; total_findings: number; unique_high_risk_findings: number; findings_by_severity: AnalyticsDistribution[]; findings_by_provider: AnalyticsDistribution[]; findings_by_category: AnalyticsDistribution[]; findings_over_time: AnalyticsTrend[]; findings: AnalyticsFinding[] }
export interface AnalyticsExecutionResponse { metadata: AnalyticsMetadata; summary: AnalyticsSummary; deviations: number; potentially_unapproved_activities: number; categories: AnalyticsDistribution[]; evidence_coverage: { covered: number; eligible: number; percentage: number | null; unavailable_reason: string | null } }
export interface AnalyticsAccessResponse { metadata: AnalyticsMetadata; access_risk_findings: number; categories: AnalyticsDistribution[]; provider_counts: AnalyticsDistribution[]; unavailable_metrics: Record<string, string> }
