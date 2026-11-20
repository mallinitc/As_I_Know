"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, AlertCircle, CheckCircle2, Clock3, LoaderCircle, Search, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AiAnalysisPanel, AssistanceModeSelector } from "@/components/llm-assistance";
import { AssessmentFeedback } from "@/components/assessment-feedback";
import { AskArcaAction } from "@/components/ask-arca-action";
import { assureAzureChangeExecution, assureAzureUserExecution, getAzureChanges, getAzureExecutionScenarios } from "@/lib/arca-api";
import type { AssistanceMode, AzureChange, AzureExecutionResponse, AzureExecutionScenario, ExecutionMode, ExecutionWindowDays } from "@/types/api";

const selectClass = "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-800 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-50";
const ranges: ExecutionWindowDays[] = [1, 7, 10, 15, 30];
function readable(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function timestamp(value?: string | null) { if (!value) return "Not provided"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : `${date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" })} UTC`; }
function variant(value: string): "success" | "warning" | "destructive" | "default" | "neutral" {
  if (["COMPLIANT", "MATCHED", "SUCCEEDED", "INFO"].includes(value)) return "success";
  if (["MIXED", "REVIEW_REQUIRED", "POSSIBLE_MATCH", "POTENTIAL_MATCH", "EVIDENCE_INCOMPLETE", "POSSIBLE", "INSUFFICIENT", "MEDIUM"].includes(value)) return "warning";
  if (["NON_COMPLIANT", "DEVIATION_DETECTED", "DEVIATION", "FAILED", "HIGH", "CRITICAL"].includes(value)) return "destructive";
  if (["UNMATCHED", "NO_RELEVANT_ACTIVITY"].includes(value)) return "neutral";
  return "default";
}

export function AzureExecutionAssuranceWorkspace() {
  const [mode, setMode] = useState<ExecutionMode>("change");
  const [changes, setChanges] = useState<AzureChange[]>([]);
  const [scenarios, setScenarios] = useState<AzureExecutionScenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [changeId, setChangeId] = useState("");
  const [identity, setIdentity] = useState("");
  const [windowDays, setWindowDays] = useState<ExecutionWindowDays>(10);
  const [evaluationTimestamp, setEvaluationTimestamp] = useState<string>();
  const [result, setResult] = useState<AzureExecutionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [assistanceMode, setAssistanceMode] = useState<AssistanceMode>("deterministic");

  useEffect(() => {
    let active = true;
    Promise.all([getAzureChanges(), getAzureExecutionScenarios()])
      .then(([changeData, scenarioData]) => { if (active) { setChanges(changeData.items); setScenarios(scenarioData.items); } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Azure execution evidence could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const selectedChange = useMemo(() => changes.find((item) => item.change_id === changeId), [changes, changeId]);
  const visibleScenarios = useMemo(() => scenarios.filter((item) => item.mode === mode), [scenarios, mode]);
  const v1Scenarios = visibleScenarios.filter((item) => item.source === "v1");
  const extendedScenarios = visibleScenarios.filter((item) => item.source !== "v1");
  function chooseMode(next: ExecutionMode) { setMode(next); setScenarioId(""); setEvaluationTimestamp(undefined); setResult(null); setError(""); if (next === "change") setIdentity(""); else setChangeId(""); }
  function chooseScenario(id: string) {
    setScenarioId(id); setResult(null); setError("");
    const scenario = scenarios.find((item) => item.scenario_id === id);
    if (!scenario) { setEvaluationTimestamp(undefined); return; }
    setMode(scenario.mode); setEvaluationTimestamp(scenario.evaluation_timestamp);
    if (scenario.change_id) { setChangeId(scenario.change_id); setIdentity(""); }
    if (scenario.user_identity && scenario.mode === "user") { setIdentity(scenario.user_identity); setChangeId(""); }
    setWindowDays(ranges.includes(scenario.window_days as ExecutionWindowDays) ? scenario.window_days as ExecutionWindowDays : 10);
  }
  async function run() {
    if (running || (mode === "change" ? !changeId : !identity.trim())) return;
    setRunning(true); setResult(null); setError("");
    try {
      const response = mode === "change"
        ? await assureAzureChangeExecution({ change_id: changeId, execution_mode: assistanceMode, ...(scenarioId ? { scenario_id: scenarioId } : {}), ...(evaluationTimestamp ? { evaluation_timestamp: evaluationTimestamp } : {}) })
        : await assureAzureUserExecution({ user_identity: identity.trim(), window_days: windowDays, execution_mode: assistanceMode, ...(scenarioId ? { scenario_id: scenarioId } : {}), ...(evaluationTimestamp ? { evaluation_timestamp: evaluationTimestamp } : {}) });
      setResult(response);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Azure execution assurance could not be completed."); }
    finally { setRunning(false); }
  }
  if (loading) return <div className="space-y-5"><Skeleton className="h-28" /><Skeleton className="h-72" /></div>;

  return <div className="space-y-6">
    <section className="rounded-2xl border border-blue-100 bg-gradient-to-r from-blue-50 to-white p-5 sm:p-6"><div className="flex flex-wrap items-center gap-2"><Badge>Azure</Badge><Badge variant="neutral">Synthetic evidence</Badge></div><h2 className="mt-3 text-2xl font-bold tracking-tight text-[#102a43]">Post-Implementation Validation</h2><p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">Correlate approved changes with Azure Activity Logs and supporting PIM/RBAC evidence using explicit UTC investigation windows.</p></section>
    <Card><CardHeader><div><CardTitle>Investigation inputs</CardTitle><CardDescription>Search by approved change or resolved Azure principal without treating unmatched events as automatically unauthorized.</CardDescription></div><Badge variant="neutral">{scenarios.filter((item) => item.source === "v1").length} V1 examples · {scenarios.filter((item) => item.source !== "v1").length} extended</Badge></CardHeader><CardContent className="space-y-5">
      <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1" role="tablist"><button role="tab" aria-selected={mode === "change"} onClick={() => chooseMode("change")} className={`rounded-md px-4 py-2 text-sm font-semibold ${mode === "change" ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:bg-white"}`}>By Change Number</button><button role="tab" aria-selected={mode === "user"} onClick={() => chooseMode("user")} className={`rounded-md px-4 py-2 text-sm font-semibold ${mode === "user" ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:bg-white"}`}>By User ID / Email</button></div>
      <div className="grid gap-4 lg:grid-cols-2"><label className="space-y-2 text-sm font-semibold text-slate-700">Verified Demo Example<select className={selectClass} value={scenarioId} onChange={(event) => chooseScenario(event.target.value)} disabled={running}><option value="">Manual Entry</option>{v1Scenarios.length > 0 && <optgroup label="Original V1 examples">{v1Scenarios.map((item) => <option key={item.scenario_id} value={item.scenario_id}>{item.scenario_name}</option>)}</optgroup>}{extendedScenarios.length > 0 && <optgroup label="Extended V2 examples">{extendedScenarios.map((item) => <option key={item.scenario_id} value={item.scenario_id}>{item.scenario_name}</option>)}</optgroup>}</select></label>
      {mode === "change" ? <label className="space-y-2 text-sm font-semibold text-slate-700">Approved Change Record<select className={selectClass} value={changeId} onChange={(event) => { setChangeId(event.target.value); setScenarioId(""); setEvaluationTimestamp(undefined); setResult(null); }} disabled={running}><option value="">Select change</option>{changes.map((item) => <option key={item.change_id} value={item.change_id}>{item.change_id} - {item.description || "Incomplete change"}</option>)}</select></label> : <><label className="space-y-2 text-sm font-semibold text-slate-700">Principal ID or email<input className={selectClass} value={identity} onChange={(event) => { setIdentity(event.target.value); setScenarioId(""); setEvaluationTimestamp(undefined); setResult(null); }} placeholder="principal ID or engineer@example.invalid" disabled={running} /></label><label className="space-y-2 text-sm font-semibold text-slate-700">Investigation period<select className={selectClass} value={windowDays} onChange={(event) => { setWindowDays(Number(event.target.value) as ExecutionWindowDays); setScenarioId(""); setEvaluationTimestamp(undefined); setResult(null); }} disabled={running}>{ranges.map((days) => <option key={days} value={days}>Last {days} {days === 1 ? "day" : "days"}</option>)}</select></label></>}
      </div>
      {evaluationTimestamp && <div className="flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"><Clock3 className="size-4" /> Demo evaluation timestamp: {timestamp(evaluationTimestamp)}</div>}
      {mode === "change" && selectedChange && <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4"><div className="mb-3 flex items-center justify-between"><h3 className="font-semibold text-[#102a43]">Approved execution intent</h3><Badge variant={selectedChange.state.toLowerCase() === "approved" ? "success" : "warning"}>{readable(selectedChange.state)}</Badge></div><div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4"><p><span className="block text-xs font-semibold uppercase text-slate-400">Implementer</span>{selectedChange.implementer?.principal_name || "Not provided"}</p><p><span className="block text-xs font-semibold uppercase text-slate-400">Window</span>{timestamp(selectedChange.start)} - {timestamp(selectedChange.end)}</p><p><span className="block text-xs font-semibold uppercase text-slate-400">Operations</span>{selectedChange.expected.map((item) => item.operation).join(", ")}</p><p><span className="block text-xs font-semibold uppercase text-slate-400">Targets</span>{selectedChange.expected.map((item) => item.resource_id).join(", ")}</p></div></div>}
      <AssistanceModeSelector mode={assistanceMode} onChange={setAssistanceMode} disabled={running} />
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5"><Button onClick={run} disabled={running || (mode === "change" ? !changeId : !identity.trim())}>{running ? <LoaderCircle className="size-4 animate-spin" /> : mode === "change" ? <Activity className="size-4" /> : <Search className="size-4" />}{mode === "change" ? "Run Execution Validation" : "Investigate User Activity"}</Button>{running && <span role="status" className="text-sm font-medium text-blue-700">Correlating Azure Activity Log and access evidence...</span>}</div>
    </CardContent></Card>
    {error && <div role="alert" className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><AlertCircle className="mt-0.5 size-5 shrink-0" /><div><p className="font-semibold">Investigation was not completed</p><p className="mt-1">{error}</p></div></div>}
    {result && <><AzureExecutionResults result={result} /><AskArcaAction sourceAgent="A3" provider="azure" changeId={result.change_id||undefined} evidenceReferences={result.event_ids} question={`Explain the Azure execution deviations in ${result.investigation_id} and distinguish confirmed findings from potential risks.`}/></>}
  </div>;
}

function AzureExecutionResults({ result }: { result: AzureExecutionResponse }) {
  return <section className="space-y-5" aria-live="polite"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-600">Investigation {result.investigation_id}</p><h2 className="mt-1 text-2xl font-bold text-[#102a43]">Execution assurance result</h2></div><Badge variant={variant(result.overall_status)} className="px-3 py-1.5">{readable(result.overall_status)}</Badge></div>
    {result.v1_assessment && <Card><CardHeader><div><CardTitle>Original V1 execution assessment</CardTitle><CardDescription>Authoritative V1 correlation status, deviation reasons, and missing execution evidence.</CardDescription></div><Badge variant={variant(result.v1_assessment.status)}>{readable(result.v1_assessment.status)}</Badge></CardHeader><CardContent className="space-y-4">{result.v1_assessment.events.map((item) => <div key={item.event_id} className="rounded-lg border border-slate-200 p-3 text-sm"><div className="flex flex-wrap items-center justify-between gap-2"><strong>{item.operation}</strong><Badge variant={variant(item.status)}>{readable(item.status)}</Badge></div><p className="mt-1 break-words text-xs text-slate-500">{item.resource_id}</p><p className="mt-2 text-xs text-slate-600">{item.event_id} · {timestamp(item.timestamp)}{item.reasons.length ? ` · ${item.reasons.map(readable).join(", ")}` : ""}</p></div>)}{result.v1_assessment.events.length === 0 && <p className="text-sm text-slate-600">No relevant successful Activity Log event was found.</p>}{result.v1_assessment.missing_expected.length > 0 && <div><h3 className="text-sm font-semibold text-slate-900">Missing expected execution evidence</h3>{result.v1_assessment.missing_expected.map((item) => <p key={`${item.operation}-${item.resource_id}`} className="mt-2 break-words text-xs text-slate-600">{item.operation} · {item.resource_id}</p>)}</div>}<p className="border-t border-slate-100 pt-3 text-xs text-slate-500">{result.v1_assessment.warning}</p></CardContent></Card>}
    <div className="grid gap-5 xl:grid-cols-2"><Card><CardHeader><div><CardTitle>Execution summary</CardTitle><CardDescription>Expected intent compared with observed Azure administrative activity.</CardDescription></div></CardHeader><CardContent className="space-y-5"><div><h3 className="text-sm font-semibold">Expected operations</h3>{result.expected_operations.length ? result.expected_operations.map((item, index) => <div key={index} className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm"><strong>{item.operation}</strong><p className="mt-1 break-words text-xs text-slate-500">{item.resource_id}</p></div>) : <p className="mt-2 text-sm text-slate-500">Not applicable to this user investigation.</p>}</div><div><h3 className="text-sm font-semibold">Observed operations</h3>{result.observed_operations.length ? result.observed_operations.map((item) => <div key={item.event_data_id} className="mt-2 rounded-lg border border-slate-200 p-3 text-sm"><div className="flex flex-wrap items-center justify-between gap-2"><strong>{item.operation}</strong><Badge variant={variant(item.change_match)}>{readable(item.change_match)}</Badge></div><p className="mt-1 break-words text-xs text-slate-500">{item.resource_id}</p><p className="mt-2 text-xs text-slate-600">{item.caller} · {timestamp(item.event_timestamp)} · {item.status}</p><code className="mt-1 block text-xs text-blue-700">{item.event_data_id}</code></div>) : <p className="mt-2 text-sm text-slate-500">No relevant activity was found.</p>}</div></CardContent></Card>
      <Card><CardHeader><div><CardTitle>Deviation findings</CardTitle><CardDescription>Confirmed, possible, and evidence-insufficient conclusions remain distinct.</CardDescription></div><Badge variant="neutral">{result.findings.length}</Badge></CardHeader><CardContent className="space-y-3">{result.findings.length ? result.findings.map((item, index) => <div key={`${item.category}-${index}`} className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap gap-2"><Badge variant={variant(item.severity)}>{readable(item.category)}</Badge><Badge variant="neutral">{readable(item.confidence)}</Badge></div><p className="mt-2 text-sm leading-6 text-slate-700">{item.message}</p>{item.event_ids.length > 0 && <code className="mt-2 block text-xs text-blue-700">{item.event_ids.join(", ")}</code>}</div>) : <div className="flex items-center gap-2 text-sm text-emerald-700"><CheckCircle2 className="size-4" /> No deviations identified.</div>}<div className="border-t border-slate-100 pt-4"><h3 className="flex items-center gap-2 text-sm font-semibold"><ShieldAlert className="size-4 text-amber-600" /> Recommended actions</h3><ul className="mt-2 space-y-2 text-sm text-slate-600">{result.recommendations.map((item) => <li key={item}>• {item}</li>)}</ul></div></CardContent></Card></div>
    <Card><CardHeader><div><CardTitle>Azure activity timeline</CardTitle><CardDescription>Chronological Activity Log evidence with provider-native identifiers and correlation context.</CardDescription></div></CardHeader><CardContent><div className="overflow-x-auto"><table className="w-full min-w-[1000px] text-left text-xs"><thead className="border-b border-slate-200 text-slate-500"><tr>{["Timestamp (UTC)","Caller","Operation","Resource","Correlation ID","Status","Change match","Deviation"].map((item) => <th key={item} className="px-3 py-2 font-semibold">{item}</th>)}</tr></thead><tbody>{result.timeline.map((item) => <tr key={item.event_data_id} className="border-b border-slate-100 align-top"><td className="px-3 py-3">{timestamp(item.event_timestamp)}</td><td className="px-3 py-3">{item.caller}</td><td className="px-3 py-3 font-medium">{item.operation}</td><td className="max-w-[260px] break-words px-3 py-3">{item.resource_id}</td><td className="px-3 py-3"><code>{item.correlation_id}</code></td><td className="px-3 py-3">{item.status}</td><td className="px-3 py-3"><Badge variant={variant(item.change_match)}>{readable(item.change_match)}</Badge>{item.change_id && <p className="mt-1">{item.change_id}</p>}</td><td className="px-3 py-3">{item.deviations.length ? item.deviations.map(readable).join(", ") : "None"}</td></tr>)}</tbody></table></div>{result.limitations.length > 0 && <div className="mt-4 border-t border-slate-100 pt-4"><p className="text-xs font-semibold uppercase text-slate-400">Evidence limitations</p>{result.limitations.map((item) => <p key={item} className="mt-1 text-xs text-slate-500">• {item}</p>)}</div>}</CardContent></Card>
    <AiAnalysisPanel analysis={result.ai_analysis} />
    <AssessmentFeedback assessmentId={`stage3:azure:${result.investigation_id}`} stage="A3" provider="azure" originalDecision={result.overall_status} resultReference={result.investigation_id} findingReference={result.event_ids[0]}/>
  </section>;
}
