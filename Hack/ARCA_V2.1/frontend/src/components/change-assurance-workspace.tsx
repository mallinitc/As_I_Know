"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Database,
  FileSearch,
  Info,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import { useEnvironment } from "@/components/app-shell";
import { AzureChangeAssuranceWorkspace } from "@/components/azure-change-assurance-workspace";
import { AwsChangeAssuranceWorkspace } from "@/components/aws-change-assurance-workspace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AiAnalysisPanel, AssistanceModeSelector } from "@/components/llm-assistance";
import { ChangeQualityActions } from "@/components/improved-draft-panel";
import { AskArcaAction } from "@/components/ask-arca-action";
import {
  ArcaApiError,
  getEnvironments,
  getSnowflakeChanges,
  getSnowflakeDemoScenarios,
  validateSnowflakeChange,
} from "@/lib/arca-api";
import { resolveChangeSelection, resolveScenarioSelection } from "@/lib/change-assurance-state";
import type {
  AssessmentSection,
  AssistanceMode,
  SnowflakeChange,
  SnowflakeDemoScenario,
  SnowflakeValidationResponse,
} from "@/types/api";

type BadgeVariant = "default" | "success" | "warning" | "destructive" | "neutral";

const selectClass = "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-800 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400";

function statusVariant(status: string): BadgeVariant {
  if (["PASS", "VALID", "ACTIVE", "APPROPRIATE"].includes(status)) return "success";
  if (["OVERPRIVILEGED", "MANUAL_REVIEW", "NEEDS_INFO", "NEED_MORE_INFO", "NOT_STARTED"].includes(status)) return "warning";
  if (["FAIL", "INSUFFICIENT_PRIVILEGES", "NOT_APPROVED", "EXPIRED"].includes(status)) return "destructive";
  return "default";
}

function readable(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatTimestamp(value?: string | null): string {
  if (!value) return "Not provided";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : `${date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" })} UTC`;
}

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "Not provided";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try { return JSON.stringify(value); } catch { return "Evidence available"; }
}

function findingText(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "object" && value !== null) {
    const item = value as Record<string, unknown>;
    return displayValue(item.reason ?? item.message ?? item.explanation ?? item);
  }
  return displayValue(value);
}

function AssessmentCard({ title, section, icon: Icon }: { title: string; section: AssessmentSection; icon: typeof ClipboardCheck }) {
  return (
    <Card className="shadow-none">
      <CardContent className="flex items-start justify-between gap-4 p-4">
        <div className="flex min-w-0 gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-700"><Icon className="size-4" /></div>
          <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</p><p className="mt-1 text-sm text-slate-600">{section.explanation ?? (section.findings.length ? findingText(section.findings[0]) : "No exceptions identified.")}</p></div>
        </div>
        <Badge variant={statusVariant(section.status)} className="shrink-0">{readable(section.status)}</Badge>
      </CardContent>
    </Card>
  );
}

function Detail({ label, value, wide = false }: { label: string; value: unknown; wide?: boolean }) {
  return <div className={wide ? "sm:col-span-2" : undefined}><dt className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</dt><dd className="mt-1 break-words text-sm font-medium text-slate-800">{displayValue(value)}</dd></div>;
}

function LoadingWorkspace() {
  return <div className="space-y-6" aria-label="Loading Snowflake assurance data"><Skeleton className="h-28 w-full" /><div className="grid gap-5 lg:grid-cols-2"><Skeleton className="h-64" /><Skeleton className="h-64" /></div></div>;
}

function ProviderComingSoon({ provider }: { provider: string }) {
  const label = provider === "all" ? "Select an environment" : `${provider.toUpperCase()} integration coming soon`;
  return <Card><CardContent className="flex min-h-[360px] flex-col items-center justify-center p-8 text-center"><div className="grid size-14 place-items-center rounded-2xl bg-blue-50 text-blue-700"><Database className="size-6" /></div><h2 className="mt-5 text-xl font-bold text-[#102a43]">{label}</h2><p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">{provider === "all" ? "Choose AWS, Azure, or Snowflake from the global Environment selector to run the native assessment." : `Native ${provider.toUpperCase()} validation is not connected in ARCA V2 yet. No simulated result will be shown.`}</p><Badge variant="neutral" className="mt-5">No validation request available</Badge></CardContent></Card>;
}

export function ChangeAssuranceWorkspace({ agent }: { agent: 1 | 2 }) {
  const { environment } = useEnvironment();
  const [changes, setChanges] = useState<SnowflakeChange[]>([]);
  const [scenarios, setScenarios] = useState<SnowflakeDemoScenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [selectedChangeId, setSelectedChangeId] = useState("");
  const [evaluationTimestamp, setEvaluationTimestamp] = useState<string | undefined>();
  const [result, setResult] = useState<SnowflakeValidationResponse | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [validating, setValidating] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [validationError, setValidationError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const [assistanceMode, setAssistanceMode] = useState<AssistanceMode>("deterministic");

  useEffect(() => {
    if (environment !== "snowflake") return;
    let active = true;
    Promise.all([getEnvironments(), getSnowflakeChanges(), getSnowflakeDemoScenarios()])
      .then(([environmentResponse, changeResponse, scenarioResponse]) => {
        if (!active) return;
        const registered = environmentResponse.environments.some((item) => item.provider === "snowflake" && item.capabilities.includes("change_access_validation"));
        if (!registered) throw new ArcaApiError("Snowflake Change Assurance is not registered by the ARCA API.", "schema");
        setChanges(changeResponse.items);
        setScenarios(scenarioResponse.items);
      })
      .catch((error: unknown) => {
        if (active) setLoadError(error instanceof Error ? error.message : "Unable to load Snowflake evidence.");
      })
      .finally(() => { if (active) setLoadingData(false); });
    return () => { active = false; };
  }, [environment, reloadToken]);

  const selectedChange = useMemo(() => resolveChangeSelection(changes, selectedChangeId), [changes, selectedChangeId]);
  const selectedScenario = useMemo(() => scenarios.find((item) => item.scenario_id === selectedScenarioId), [scenarios, selectedScenarioId]);

  function chooseScenario(scenarioId: string) {
    setSelectedScenarioId(scenarioId);
    setResult(null);
    setValidationError("");
    if (!scenarioId) {
      setEvaluationTimestamp(undefined);
      return;
    }
    const selection = resolveScenarioSelection(scenarios, scenarioId);
    if (!selection) {
      setSelectedChangeId("");
      setEvaluationTimestamp(undefined);
      setValidationError("The selected demo scenario is no longer available. Refresh the evidence and try again.");
      return;
    }
    setSelectedChangeId(selection.changeId);
    setEvaluationTimestamp(selection.evaluationTimestamp);
  }

  function chooseChange(changeId: string) {
    setSelectedChangeId(changeId);
    setSelectedScenarioId("");
    setEvaluationTimestamp(undefined);
    setResult(null);
    setValidationError("");
  }

  async function runValidation() {
    if (!selectedChangeId || validating) return;
    setValidating(true);
    setValidationError("");
    setResult(null);
    try {
      const response = await validateSnowflakeChange({
        change_id: selectedChangeId,
        ...(evaluationTimestamp ? { evaluation_timestamp: evaluationTimestamp } : {}),
        execution_mode: assistanceMode,
      });
      setResult(response);
    } catch (error) {
      setValidationError(error instanceof Error ? error.message : "Validation could not be completed.");
    } finally {
      setValidating(false);
    }
  }

  function retryLoading() {
    setLoadingData(true);
    setLoadError("");
    setReloadToken((value) => value + 1);
  }

  if (environment === "azure") return <AzureChangeAssuranceWorkspace stage={agent === 1 ? "change" : "access"} />;
  if (environment === "aws") return <AwsChangeAssuranceWorkspace stage={agent === 1 ? "change" : "access"} />;
  if (environment !== "snowflake") return <ProviderComingSoon provider={environment} />;
  if (loadingData) return <LoadingWorkspace />;

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 rounded-2xl border border-blue-100 bg-gradient-to-r from-blue-50 to-white p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
        <div><div className="flex flex-wrap items-center gap-2"><Badge>Snowflake</Badge><Badge variant="neutral">Shared Agent 1 + Agent 2 assessment</Badge></div><h2 className="mt-3 text-xl font-bold tracking-tight text-[#102a43]">Unified Change &amp; Access Validation</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-slate-600">Snowflake uses one existing backend validation call. This {agent === 1 ? "Change Quality" : "Access Intelligence"} view emphasizes the relevant controls without claiming a separate agent execution.</p></div>
        <div className="flex items-center gap-2 text-xs font-medium text-slate-500"><ShieldCheck className="size-4 text-emerald-600" /> Read-only assessment</div>
      </section>

      {loadError ? <Card className="border-red-200"><CardContent className="flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><AlertCircle className="mt-0.5 size-5 shrink-0 text-red-600" /><div><p className="font-semibold text-red-800">Snowflake evidence is unavailable</p><p className="mt-1 text-sm text-red-700">{loadError}</p></div></div><Button variant="outline" onClick={retryLoading}><RefreshCw className="size-4" /> Retry</Button></CardContent></Card> : (
        <>
          <Card>
            <CardHeader><div><CardTitle>Validation inputs</CardTitle><CardDescription>Select verified evidence or choose a change directly. No result is generated until validation runs.</CardDescription></div><span className="text-xs font-semibold text-slate-400">{scenarios.length} verified examples</span></CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-4 lg:grid-cols-2">
                <label className="space-y-2 text-sm font-semibold text-slate-700">Verified Demo Example<select className={selectClass} value={selectedScenarioId} onChange={(event) => chooseScenario(event.target.value)} disabled={validating}><option value="">Manual Entry</option>{scenarios.map((scenario) => <option key={scenario.scenario_id} value={scenario.scenario_id}>{scenario.scenario_id} — {scenario.scenario_name}</option>)}</select></label>
                <label className="space-y-2 text-sm font-semibold text-slate-700">Approved Change Record<select className={selectClass} value={selectedChangeId} onChange={(event) => chooseChange(event.target.value)} disabled={validating}><option value="">Select change</option>{changes.map((change) => <option key={change.change_id} value={change.change_id}>{change.change_id} — {change.short_description || "Untitled change"}</option>)}</select></label>
              </div>
              {selectedScenario && <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-blue-100 bg-blue-50/70 px-4 py-3 text-sm text-blue-900"><Info className="size-4 shrink-0 text-blue-600" /><span className="font-semibold">{selectedScenario.scenario_name}</span><span className="text-blue-700">Evaluation time: {formatTimestamp(selectedScenario.evaluation_timestamp)}</span></div>}
              {selectedChange ? <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4"><div className="mb-4 flex items-center justify-between gap-3"><h3 className="font-semibold text-[#102a43]">Change details</h3><Badge variant={selectedChange.state.toLowerCase() === "approved" ? "success" : "warning"}>{readable(selectedChange.state || "Unknown")}</Badge></div><dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4"><Detail label="Change ID" value={selectedChange.change_id} /><Detail label="Implementer" value={selectedChange.implementer} /><Detail label="Start" value={formatTimestamp(selectedChange.start)} /><Detail label="End" value={formatTimestamp(selectedChange.end)} /><Detail label="Description" value={selectedChange.description} wide /><Detail label="Requested Snowflake role" value={selectedChange.snowflake_context?.requested_role} /><Detail label="Environment" value={readable(selectedChange.environment)} />{selectedChange.expected.length ? selectedChange.expected.map((operation, index) => <div key={`${operation.operation}-${index}`} className="contents"><Detail label={index ? `Expected operation ${index + 1}` : "Expected operation"} value={operation.operation} /><Detail label={index ? `Target object ${index + 1}` : "Target object"} value={operation.resource_id} /></div>) : <Detail label="Expected operation" value="Not provided" wide />}</dl></div> : <div className="flex min-h-28 items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50/40 text-sm text-slate-500"><FileSearch className="mr-2 size-4" /> Select a change to review its documented intent.</div>}
              <AssistanceModeSelector mode={assistanceMode} onChange={setAssistanceMode} disabled={validating} sharedAgentDisclosure />
              <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5"><Button onClick={runValidation} disabled={!selectedChangeId || validating}>{validating ? <LoaderCircle className="size-4 animate-spin" /> : <ClipboardCheck className="size-4" />}Run Validation</Button>{validating && <span className="inline-flex items-center gap-2 text-sm font-medium text-blue-700" role="status"><LoaderCircle className="size-4 animate-spin" /> Validating change...</span>} {!selectedChangeId && <span className="text-sm text-slate-400">Choose a change before running validation.</span>}</div>
            </CardContent>
          </Card>

          {validationError && <div role="alert" className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><AlertCircle className="mt-0.5 size-5 shrink-0" /><div><p className="font-semibold">Validation was not completed</p><p className="mt-1">{validationError}</p></div></div>}

          {result && <ValidationResults result={result} agent={agent} assistanceMode={assistanceMode} />}
        </>
      )}
    </div>
  );
}

function ValidationResults({ result, agent, assistanceMode }: { result: SnowflakeValidationResponse; agent: 1 | 2; assistanceMode: AssistanceMode }) {
  const recommendations = [
    result.role_assessment.recommended_role ? `Use the narrower evidenced role: ${result.role_assessment.recommended_role}.` : null,
    result.role_assessment.status !== "APPROPRIATE" ? result.role_assessment.explanation : null,
    result.window_assessment.status !== "ACTIVE" ? result.window_assessment.explanation : null,
  ].filter((item): item is string => Boolean(item));

  return <section className="space-y-5" aria-live="polite"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-blue-600">Shared unified assessment complete</p><h2 className="mt-1 text-2xl font-bold text-[#102a43]">{agent === 1 ? "Change Quality result" : "Access Intelligence result"}</h2><p className="mt-1 text-xs text-slate-500">The overall status comes from the combined Snowflake Agent 1 + Agent 2 contract.</p></div><Badge variant={statusVariant(result.overall_status)} className="px-3 py-1.5 text-sm">Overall: {readable(result.overall_status)}</Badge></div><div className="grid gap-5 xl:grid-cols-2"><div className="space-y-4"><Card><CardHeader><div><CardTitle>{agent === 1 ? "Change quality controls" : "Access intelligence controls"}</CardTitle><CardDescription>Relevant controls from the single unified Snowflake validation response.</CardDescription></div></CardHeader><CardContent className="space-y-3">{agent === 1 ? <><AssessmentCard title="Change Quality" section={result.change_quality} icon={ClipboardCheck} /><AssessmentCard title="Change Window" section={result.window_assessment} icon={Clock3} /></> : <><AssessmentCard title="Requested Role Assessment" section={result.role_assessment} icon={ShieldCheck} /><AssessmentCard title="Change Window Context" section={result.window_assessment} icon={Clock3} /></>}</CardContent></Card>{result.missing_information.length > 0 && <Card className="border-amber-200"><CardHeader><div><CardTitle>Missing information</CardTitle><CardDescription>Evidence required for a complete deterministic decision.</CardDescription></div><Badge variant="warning">{result.missing_information.length}</Badge></CardHeader><CardContent><ul className="space-y-2">{result.missing_information.map((item) => <li key={item} className="flex items-start gap-2 text-sm text-amber-900"><AlertCircle className="mt-0.5 size-4 shrink-0" />{readable(item)}</li>)}</ul></CardContent></Card>}</div><div className="space-y-4"><Card><CardHeader><div><CardTitle>Findings and recommendations</CardTitle><CardDescription>Shared evidence-backed exceptions and corrective guidance from the unified assessment.</CardDescription></div></CardHeader><CardContent className="space-y-5"><div><h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900"><ShieldAlert className="size-4 text-amber-600" /> Access risk findings</h3>{result.findings.length ? <ul className="mt-3 space-y-2">{result.findings.map((finding, index) => <li key={`${findingText(finding)}-${index}`} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700">{findingText(finding)}</li>)}</ul> : <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"><CheckCircle2 className="size-4" /> No independent findings were returned.</div>}</div><div className="border-t border-slate-100 pt-4"><h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900"><ArrowRight className="size-4 text-blue-600" /> Recommendations</h3>{recommendations.length ? <ul className="mt-3 space-y-2">{recommendations.map((item) => <li key={item} className="text-sm leading-6 text-slate-600">• {item}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No corrective recommendation was returned by the assessment.</p>}</div></CardContent></Card><Card><CardHeader><div><CardTitle>Supporting evidence</CardTitle><CardDescription>Original evidence references returned by the validation service.</CardDescription></div><Badge variant="neutral">{result.evidence.length}</Badge></CardHeader><CardContent>{result.evidence.length ? <div className="flex flex-wrap gap-2">{result.evidence.map((item, index) => <code key={`${displayValue(item)}-${index}`} className="rounded-md border border-blue-100 bg-blue-50 px-2.5 py-1.5 text-xs font-semibold text-blue-800">{displayValue(item)}</code>)}</div> : <p className="text-sm text-slate-500">No supporting evidence reference was returned.</p>}<div className="mt-4 border-t border-slate-100 pt-4 text-xs text-slate-500"><p>Evaluated {formatTimestamp(result.evaluation_timestamp)}</p>{result.warning && <p className="mt-1">{result.warning}</p>}</div></CardContent></Card></div></div><AiAnalysisPanel analysis={result.ai_analysis} />{agent === 1 ? <ChangeQualityActions provider="snowflake" changeId={result.change_id} findings={result.findings} missingInformation={result.missing_information} assistanceMode={assistanceMode} /> : <AskArcaAction sourceAgent="A2" provider="snowflake" changeId={result.change_id} question={`Explain the Snowflake access findings for ${result.change_id} and recommend evidence-backed next steps.`} />}</section>;
}
