"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, AlertCircle, CheckCircle2, Clock3, Database, FileSearch, LoaderCircle, Search, ShieldAlert } from "lucide-react";

import { useEnvironment } from "@/components/app-shell";
import { AzureExecutionAssuranceWorkspace } from "@/components/azure-execution-assurance-workspace";
import { AwsExecutionAssuranceWorkspace } from "@/components/aws-execution-assurance-workspace";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AiAnalysisPanel, AssistanceModeSelector } from "@/components/llm-assistance";
import { AssessmentFeedback } from "@/components/assessment-feedback";
import { AskArcaAction } from "@/components/ask-arca-action";
import { assureSnowflakeChangeExecution, assureSnowflakeUserExecution, getSnowflakeChanges, getSnowflakeExecutionScenarios } from "@/lib/arca-api";
import type { AssistanceMode, ExecutionMode, ExecutionWindowDays, SnowflakeChange, SnowflakeExecutionResponse, SnowflakeExecutionScenario } from "@/types/api";

const selectClass = "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-800 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-50";
const inputClass = `${selectClass} placeholder:font-normal placeholder:text-slate-400`;
const ranges: ExecutionWindowDays[] = [1, 7, 10, 15, 30];

function readable(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function timestamp(value?: string | null) {
  if (!value) return "Not provided";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : `${date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" })} UTC`;
}
function statusVariant(value: string): "success" | "warning" | "destructive" | "default" {
  if (["COMPLIANT", "SUCCESS", "CONFIRMED"].includes(value)) return "success";
  if (["REVIEW_REQUIRED", "MIXED", "POSSIBLE", "INSUFFICIENT", "NO_RELEVANT_ACTIVITY"].includes(value)) return "warning";
  if (["NON_COMPLIANT", "FAILED", "HIGH", "CRITICAL"].includes(value)) return "destructive";
  return "default";
}
function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><dt className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</dt><dd className="mt-1 break-words text-sm font-medium text-slate-800">{children || "Not provided"}</dd></div>;
}
function ComingSoon({ provider }: { provider: string }) {
  return <Card><CardContent className="flex min-h-[360px] flex-col items-center justify-center p-8 text-center"><div className="grid size-14 place-items-center rounded-2xl bg-blue-50 text-blue-700"><Database className="size-6" /></div><h2 className="mt-5 text-xl font-bold text-[#102a43]">{provider === "all" ? "Select an environment" : `${provider.toUpperCase()} integration coming soon`}</h2><p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">Choose Snowflake to run native post-implementation assurance. ARCA V2 does not simulate execution results for unconnected providers.</p></CardContent></Card>;
}

export function ExecutionAssuranceWorkspace() {
  const { environment } = useEnvironment();
  const [mode, setMode] = useState<ExecutionMode>("change");
  const [changes, setChanges] = useState<SnowflakeChange[]>([]);
  const [scenarios, setScenarios] = useState<SnowflakeExecutionScenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [changeId, setChangeId] = useState("");
  const [identity, setIdentity] = useState("");
  const [windowDays, setWindowDays] = useState<ExecutionWindowDays>(10);
  const [evaluationTimestamp, setEvaluationTimestamp] = useState<string>();
  const [result, setResult] = useState<SnowflakeExecutionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [assistanceMode, setAssistanceMode] = useState<AssistanceMode>("deterministic");

  useEffect(() => {
    if (environment !== "snowflake") return;
    let active = true;
    Promise.all([getSnowflakeChanges(), getSnowflakeExecutionScenarios()])
      .then(([changeData, scenarioData]) => { if (active) { setChanges(changeData.items); setScenarios(scenarioData.items); } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Execution evidence could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [environment]);

  const selectedChange = useMemo(() => changes.find((item) => item.change_id === changeId), [changes, changeId]);
  const visibleScenarios = useMemo(() => scenarios.filter((item) => item.investigation_mode === mode), [scenarios, mode]);

  function changeMode(next: ExecutionMode) {
    setMode(next); setScenarioId(""); setResult(null); setError(""); setEvaluationTimestamp(undefined);
  }
  function selectScenario(id: string) {
    setScenarioId(id); setResult(null); setError("");
    const scenario = scenarios.find((item) => item.scenario_id === id);
    if (!scenario) { setEvaluationTimestamp(undefined); return; }
    setMode(scenario.investigation_mode);
    setEvaluationTimestamp(scenario.evaluation_timestamp);
    if (scenario.change_id) setChangeId(scenario.change_id);
    if (scenario.user_identity) setIdentity(scenario.user_identity);
    setWindowDays(ranges.includes(scenario.window_days as ExecutionWindowDays) ? scenario.window_days as ExecutionWindowDays : 30);
  }
  async function run() {
    if (running || (mode === "change" ? !changeId : !identity.trim())) return;
    setRunning(true); setResult(null); setError("");
    try {
      const response = mode === "change"
        ? await assureSnowflakeChangeExecution({ change_id: changeId, execution_mode: assistanceMode, ...(evaluationTimestamp ? { evaluation_timestamp: evaluationTimestamp } : {}), ...(scenarioId ? { scenario_id: scenarioId } : {}) })
        : await assureSnowflakeUserExecution({ user_identity: identity.trim(), window_days: windowDays, execution_mode: assistanceMode, ...(evaluationTimestamp ? { evaluation_timestamp: evaluationTimestamp } : {}), ...(scenarioId ? { scenario_id: scenarioId } : {}) });
      setResult(response);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Execution assurance could not be completed."); }
    finally { setRunning(false); }
  }

  if (environment === "azure") return <AzureExecutionAssuranceWorkspace />;
  if (environment === "aws") return <AwsExecutionAssuranceWorkspace />;
  if (environment !== "snowflake") return <ComingSoon provider={environment} />;
  if (loading) return <div className="space-y-5"><Skeleton className="h-28" /><Skeleton className="h-72" /></div>;

  return <div className="space-y-6">
    <section className="rounded-2xl border border-blue-100 bg-gradient-to-r from-blue-50 to-white p-5 sm:p-6"><div className="flex flex-wrap items-center gap-2"><Badge>Snowflake</Badge><Badge variant="neutral">Synthetic evidence</Badge></div><h2 className="mt-3 text-2xl font-bold tracking-tight text-[#102a43]">Post-Implementation Validation</h2><p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">Compare approved change intent with query and access-history evidence, or investigate a resolved Snowflake user over an explicit UTC window.</p></section>

    <Card><CardHeader><div><CardTitle>Investigation inputs</CardTitle><CardDescription>Choose a verified scenario or enter evidence criteria manually.</CardDescription></div><Badge variant="neutral">{scenarios.length} verified examples</Badge></CardHeader><CardContent className="space-y-5">
      <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1" role="tablist" aria-label="Investigation mode"><button role="tab" aria-selected={mode === "change"} onClick={() => changeMode("change")} className={`rounded-md px-4 py-2 text-sm font-semibold transition ${mode === "change" ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:bg-white"}`}>By change</button><button role="tab" aria-selected={mode === "user"} onClick={() => changeMode("user")} className={`rounded-md px-4 py-2 text-sm font-semibold transition ${mode === "user" ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:bg-white"}`}>By user</button></div>
      <div className="grid gap-4 lg:grid-cols-2"><label className="space-y-2 text-sm font-semibold text-slate-700">Verified Demo Example<select className={selectClass} value={scenarioId} onChange={(event) => selectScenario(event.target.value)} disabled={running}><option value="">Manual Entry</option>{visibleScenarios.map((item) => <option value={item.scenario_id} key={item.scenario_id}>{item.scenario_name}</option>)}</select></label>
      {mode === "change" ? <label className="space-y-2 text-sm font-semibold text-slate-700">Approved Change Record<select className={selectClass} value={changeId} onChange={(event) => { setChangeId(event.target.value); setScenarioId(""); setEvaluationTimestamp(undefined); setResult(null); }} disabled={running}><option value="">Select change</option>{changes.map((item) => <option key={item.change_id} value={item.change_id}>{item.change_id} - {item.short_description}</option>)}</select></label> : <><label className="space-y-2 text-sm font-semibold text-slate-700">User ID, username, or email<input className={inputClass} value={identity} onChange={(event) => { setIdentity(event.target.value); setScenarioId(""); setEvaluationTimestamp(undefined); setResult(null); }} placeholder="SF-USER-001 or user@example.invalid" disabled={running} /></label><label className="space-y-2 text-sm font-semibold text-slate-700">Investigation period<select className={selectClass} value={windowDays} onChange={(event) => { setWindowDays(Number(event.target.value) as ExecutionWindowDays); setScenarioId(""); setEvaluationTimestamp(undefined); setResult(null); }} disabled={running}>{ranges.map((days) => <option key={days} value={days}>Last {days} {days === 1 ? "day" : "days"}</option>)}</select></label></>}
      </div>
      {evaluationTimestamp && <div className="flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"><Clock3 className="size-4" /> Demo evaluation timestamp: {timestamp(evaluationTimestamp)}</div>}
      {mode === "change" && (selectedChange ? <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4"><div className="mb-4 flex items-center justify-between"><h3 className="font-semibold text-[#102a43]">Approved change details</h3><Badge variant={selectedChange.state.toLowerCase() === "approved" ? "success" : "warning"}>{readable(selectedChange.state)}</Badge></div><dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><Detail label="Change ID">{selectedChange.change_id}</Detail><Detail label="Implementer">{selectedChange.implementer}</Detail><Detail label="Start">{timestamp(selectedChange.start)}</Detail><Detail label="End">{timestamp(selectedChange.end)}</Detail><Detail label="Requested role">{selectedChange.snowflake_context?.requested_role}</Detail><Detail label="Expected operation">{selectedChange.expected.map((item) => item.operation).join(", ")}</Detail><Detail label="Target object">{selectedChange.expected.map((item) => item.resource_id).join(", ")}</Detail></dl></div> : <div className="flex min-h-24 items-center justify-center rounded-xl border border-dashed border-slate-300 text-sm text-slate-500"><FileSearch className="mr-2 size-4" /> Select a change to inspect approved intent.</div>)}
      <AssistanceModeSelector mode={assistanceMode} onChange={setAssistanceMode} disabled={running} />
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5"><Button onClick={run} disabled={running || (mode === "change" ? !changeId : !identity.trim())}>{running ? <LoaderCircle className="size-4 animate-spin" /> : mode === "change" ? <Activity className="size-4" /> : <Search className="size-4" />} {mode === "change" ? "Run Execution Validation" : "Investigate User Activity"}</Button>{running && <span role="status" className="text-sm font-medium text-blue-700">Analyzing Snowflake evidence...</span>}</div>
    </CardContent></Card>
    {error && <div role="alert" className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><AlertCircle className="mt-0.5 size-5 shrink-0" /><div><p className="font-semibold">Investigation was not completed</p><p className="mt-1">{error}</p></div></div>}
    {result && <><ExecutionResults result={result} /><AskArcaAction sourceAgent="A3" provider="snowflake" changeId={result.change_id||undefined} evidenceReferences={result.query_ids} question={`Explain the Snowflake execution deviations in ${result.investigation_id} and distinguish confirmed findings from potential risks.`}/></>}
  </div>;
}

function ExecutionResults({ result }: { result: SnowflakeExecutionResponse }) {
  return <section className="space-y-5" aria-live="polite"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-600">Investigation {result.investigation_id}</p><h2 className="mt-1 text-2xl font-bold text-[#102a43]">Execution assurance result</h2></div><Badge variant={statusVariant(result.overall_status)} className="px-3 py-1.5">{readable(result.overall_status)}</Badge></div>
    <div className="grid gap-5 xl:grid-cols-2"><div className="space-y-5"><Card><CardHeader><div><CardTitle>Approved vs observed</CardTitle><CardDescription>Correlated using change reference, actor, operation, target, role, and UTC timestamp.</CardDescription></div></CardHeader><CardContent className="space-y-5"><div><h3 className="text-sm font-semibold text-slate-900">Expected operations</h3>{result.expected_operations.length ? result.expected_operations.map((item, index) => <div key={index} className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm"><span className="font-semibold">{item.operation}</span><span className="ml-2 text-slate-500">{item.resource_id}</span></div>) : <p className="mt-2 text-sm text-slate-500">Not applicable to this user investigation.</p>}</div><div><h3 className="text-sm font-semibold text-slate-900">Observed operations</h3>{result.observed_operations.length ? result.observed_operations.map((item) => <div key={item.query_id} className="mt-2 grid gap-2 rounded-lg border border-slate-200 p-3 text-sm sm:grid-cols-2"><span className="font-semibold text-slate-900">{item.operation} - {item.target}</span><Badge variant={statusVariant(item.status || "")}>{item.status}</Badge><span className="text-slate-600">{item.actor} using {item.role}</span><span className="text-slate-500">{timestamp(item.timestamp)}</span><code className="text-xs text-blue-700">{item.query_id}</code></div>) : <p className="mt-2 text-sm text-slate-500">No matching activity in the selected period.</p>}</div></CardContent></Card>
      <Card><CardHeader><div><CardTitle>Evidence timeline</CardTitle><CardDescription>Original query IDs and explicit UTC timestamps.</CardDescription></div></CardHeader><CardContent>{result.timeline.length ? <ol className="space-y-3 border-l border-blue-200 pl-4">{result.timeline.map((item) => <li key={item.query_id}><p className="text-sm font-semibold text-slate-800">{item.operation} - {item.target}</p><p className="text-xs text-slate-500">{timestamp(item.timestamp)} · {item.query_id}</p></li>)}</ol> : <p className="text-sm text-slate-500">No timeline evidence found.</p>}</CardContent></Card></div>
      <div className="space-y-5"><Card><CardHeader><div><CardTitle>Findings</CardTitle><CardDescription>Confirmed, possible, and evidence-insufficient conclusions remain distinct.</CardDescription></div><Badge variant="neutral">{result.findings.length}</Badge></CardHeader><CardContent className="space-y-3">{result.findings.length ? result.findings.map((item, index) => <div key={`${item.category}-${index}`} className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap items-center gap-2"><Badge variant={statusVariant(item.severity)}>{readable(item.category)}</Badge><Badge variant="neutral">{readable(item.confidence)}</Badge></div><p className="mt-2 text-sm leading-6 text-slate-700">{item.message}</p>{item.query_ids.length > 0 && <code className="mt-2 block text-xs text-blue-700">{item.query_ids.join(", ")}</code>}</div>) : <div className="flex items-center gap-2 text-sm text-emerald-700"><CheckCircle2 className="size-4" /> No exceptions were identified.</div>}</CardContent></Card>
      <Card><CardHeader><div><CardTitle>Recommendations and limitations</CardTitle><CardDescription>Audit evidence supports review; it does not assert final Snowflake state.</CardDescription></div></CardHeader><CardContent className="space-y-4">{result.recommendations.length > 0 && <div><h3 className="flex items-center gap-2 text-sm font-semibold"><ShieldAlert className="size-4 text-amber-600" /> Recommended actions</h3><ul className="mt-2 space-y-2 text-sm text-slate-600">{result.recommendations.map((item) => <li key={item}>• {item}</li>)}</ul></div>}<div><h3 className="text-sm font-semibold">Evidence limitations</h3><ul className="mt-2 space-y-2 text-sm text-slate-500">{result.limitations.map((item) => <li key={item}>• {item}</li>)}</ul></div></CardContent></Card></div></div>
    <AiAnalysisPanel analysis={result.ai_analysis} />
    <AssessmentFeedback assessmentId={`stage3:snowflake:${result.investigation_id}`} stage="A3" provider="snowflake" originalDecision={result.overall_status} resultReference={result.investigation_id} findingReference={result.query_ids[0]}/>
  </section>;
}
