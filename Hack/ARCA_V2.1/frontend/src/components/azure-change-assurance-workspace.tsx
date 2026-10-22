"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, ClipboardCheck, KeyRound, LoaderCircle, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AiAnalysisPanel, AssistanceModeSelector } from "@/components/llm-assistance";
import { ChangeQualityActions } from "@/components/improved-draft-panel";
import { AskArcaAction } from "@/components/ask-arca-action";
import { getAzureChanges, getAzureDemoScenarios, validateAzureAccess, validateAzureChange } from "@/lib/arca-api";
import type { AssistanceMode, AzureAccessValidationResponse, AzureChange, AzureChangeValidationResponse, AzureDemoScenario, AzureFinding, AzureValidationStage } from "@/types/api";

const selectClass = "h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-800 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-50";

function readable(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function timestamp(value?: string | null) {
  if (!value) return "Not provided";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : `${parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" })} UTC`;
}
function variant(value: string): "success" | "warning" | "destructive" | "default" | "neutral" {
  if (["VALID", "APPROVE_RECOMMENDED"].includes(value)) return "success";
  if (["INCOMPLETE", "MANUAL_REVIEW_REQUIRED", "OVERPRIVILEGED", "WARNING", "REVIEW"].includes(value)) return "warning";
  if (["INCONSISTENT", "INSUFFICIENT_ACCESS", "ERROR", "CRITICAL"].includes(value)) return "destructive";
  if (["NEED_MORE_INFO"].includes(value)) return "neutral";
  return "default";
}
function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not provided";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export function AzureChangeAssuranceWorkspace({ stage }: { stage: AzureValidationStage }) {
  const [changes, setChanges] = useState<AzureChange[]>([]);
  const [scenarios, setScenarios] = useState<AzureDemoScenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [changeId, setChangeId] = useState("");
  const [result, setResult] = useState<AzureChangeValidationResponse | AzureAccessValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [assistanceMode, setAssistanceMode] = useState<AssistanceMode>("deterministic");

  useEffect(() => {
    let active = true;
    Promise.all([getAzureChanges(), getAzureDemoScenarios()])
      .then(([changeData, scenarioData]) => { if (active) { setChanges(changeData.items); setScenarios(scenarioData.items); } })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Azure evidence could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const selectedChange = useMemo(() => changes.find((item) => item.change_id === changeId), [changes, changeId]);
  const stageScenarios = useMemo(() => scenarios.filter((item) => item.stage === stage), [scenarios, stage]);

  function chooseScenario(id: string) {
    setScenarioId(id); setResult(null); setError("");
    const scenario = scenarios.find((item) => item.scenario_id === id);
    if (scenario) setChangeId(scenario.change_id);
  }
  async function run() {
    if (!changeId || running) return;
    setRunning(true); setResult(null); setError("");
    try { setResult(stage === "change" ? await validateAzureChange(changeId, assistanceMode) : await validateAzureAccess(changeId, assistanceMode)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Azure validation could not be completed."); }
    finally { setRunning(false); }
  }

  if (loading) return <div className="space-y-5"><Skeleton className="h-28" /><Skeleton className="h-72" /></div>;

  return <div className="space-y-6">
    <section className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex flex-wrap items-center gap-2"><Badge>Azure</Badge><Badge variant="neutral">{stage === "change" ? "Agent 1" : "Agent 2"}</Badge></div><h2 className="mt-3 text-xl font-bold tracking-tight text-[#102a43]">{stage === "change" ? "Change Quality Validation" : "PIM/RBAC Least-Privilege Validation"}</h2><p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{stage === "change" ? "Assess ServiceNow change completeness and clarity using deterministic controls." : "Correlate approved intent with Azure PIM, RBAC, role-definition, scope, and resource evidence."}</p></section>

    <Card><CardHeader><div><CardTitle>Validation inputs</CardTitle><CardDescription>Select a verified example or an approved change record. Each stage runs independently.</CardDescription></div><Badge variant="neutral">{scenarios.length} verified examples</Badge></CardHeader><CardContent className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-2"><label className="space-y-2 text-sm font-semibold text-slate-700">Verified Demo Example<select className={selectClass} value={scenarioId} onChange={(event) => chooseScenario(event.target.value)} disabled={running}><option value="">Manual Entry</option>{stageScenarios.map((item) => <option key={item.scenario_id} value={item.scenario_id}>{item.scenario_name}</option>)}</select></label><label className="space-y-2 text-sm font-semibold text-slate-700">Approved Change Record<select className={selectClass} value={changeId} onChange={(event) => { setChangeId(event.target.value); setScenarioId(""); setResult(null); setError(""); }} disabled={running}><option value="">Select change</option>{changes.map((item) => <option key={item.change_id} value={item.change_id}>{item.change_id} - {item.description || readable(String(item.scenario || "Incomplete change"))}</option>)}</select></label></div>
      {selectedChange && <ChangeDetails change={selectedChange} />}
      <AssistanceModeSelector mode={assistanceMode} onChange={setAssistanceMode} disabled={running} />
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5"><Button onClick={run} disabled={!changeId || running}>{running ? <LoaderCircle className="size-4 animate-spin" /> : stage === "change" ? <ClipboardCheck className="size-4" /> : <KeyRound className="size-4" />}{stage === "change" ? "Run Change Validation" : "Run Access Validation"}</Button>{running && <span role="status" className="inline-flex items-center gap-2 text-sm font-medium text-blue-700"><LoaderCircle className="size-4 animate-spin" />{stage === "change" ? "Validating change quality..." : "Correlating PIM and RBAC evidence..."}</span>}</div>
    </CardContent></Card>
    {error && <div role="alert" className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><AlertCircle className="mt-0.5 size-5 shrink-0" /><div><p className="font-semibold">Validation was not completed</p><p className="mt-1">{error}</p></div></div>}
    {result && <AzureResults result={result} assistanceMode={assistanceMode} />}
  </div>;
}

function ChangeDetails({ change }: { change: AzureChange }) {
  const details = [
    ["Change ID", change.change_id], ["Approval", readable(change.state || "Unknown")],
    ["Implementer", change.implementer?.principal_name], ["Environment", readable(change.environment || "Unknown")],
    ["Start", timestamp(change.start)], ["End", timestamp(change.end)],
    ["Expected operations", change.expected.map((item) => item.operation).join(", ")],
    ["Target resources", change.expected.map((item) => item.resource_id).join(", ")],
  ];
  return <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4"><div className="mb-4 flex items-center justify-between"><h3 className="font-semibold text-[#102a43]">Change details</h3><Badge variant={change.state.toLowerCase() === "approved" ? "success" : "warning"}>{readable(change.state || "Unknown")}</Badge></div><dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{details.map(([label, value]) => <div key={label}><dt className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</dt><dd className="mt-1 break-words text-sm font-medium text-slate-800">{value || "Not provided"}</dd></div>)}</dl>{!change.description && <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">Description is not provided in the source change record.</div>}</div>;
}

function FindingCard({ finding }: { finding: AzureFinding }) {
  return <div className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap items-center gap-2"><Badge variant={variant(finding.severity)}>{readable(finding.category)}</Badge><span className="text-xs font-semibold uppercase tracking-wider text-slate-400">{finding.field}</span></div><p className="mt-2 text-sm leading-6 text-slate-700">{finding.message}</p><dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2"><div><dt className="font-semibold text-slate-500">Actual</dt><dd className="mt-1 break-words text-slate-700">{show(finding.actual)}</dd></div><div><dt className="font-semibold text-slate-500">Expected</dt><dd className="mt-1 break-words text-slate-700">{show(finding.expected)}</dd></div></dl></div>;
}

function AzureResults({ result, assistanceMode }: { result: AzureChangeValidationResponse | AzureAccessValidationResponse; assistanceMode: AssistanceMode }) {
  return <section className="space-y-5" aria-live="polite"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-600">{result.stage === "change" ? "Stage 1 complete" : "Stage 2 complete"}</p><h2 className="mt-1 text-2xl font-bold text-[#102a43]">Azure assessment result</h2></div><Badge variant={variant(result.overall_status)} className="px-3 py-1.5">{readable(result.overall_status)}</Badge></div>
    <div className="grid gap-5 xl:grid-cols-2"><div className="space-y-5"><Card><CardHeader><div><CardTitle>{result.stage === "change" ? "Change completeness findings" : "PIM and RBAC assessments"}</CardTitle><CardDescription>Independent controls retain actual, expected, and corrective context.</CardDescription></div><Badge variant="neutral">{result.findings.length}</Badge></CardHeader><CardContent className="space-y-3">{result.findings.length ? result.findings.map((item, index) => <FindingCard key={`${item.category}-${item.field}-${index}`} finding={item} />) : <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"><CheckCircle2 className="size-4" /> No validation exceptions were identified.</div>}</CardContent></Card>
      {result.stage === "access" && <Card><CardHeader><div><CardTitle>PIM assessments and permission coverage</CardTitle><CardDescription>Requests are evaluated independently before aggregate operation coverage is calculated.</CardDescription></div></CardHeader><CardContent className="space-y-5"><div className="grid gap-3 sm:grid-cols-2">{result.pim_assessments.map((assessment) => <div key={assessment.pim_request_id} className="rounded-lg border border-slate-200 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><code className="text-xs font-semibold text-blue-700">{assessment.pim_request_id}</code><Badge variant={variant(assessment.overall_status)}>{readable(assessment.overall_status)}</Badge></div><p className="mt-2 text-xs text-slate-500">{assessment.supported_operations.length} documented operation(s) supported · {assessment.findings.length} finding(s)</p></div>)}</div><div className="grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-2"><div><p className="text-sm font-semibold text-emerald-700">Covered ({result.covered_operations.length})</p>{result.covered_operations.map((item, index) => <p key={index} className="mt-2 break-words text-xs text-slate-600">{item.operation}<br />{item.resource_id}</p>)}</div><div><p className="text-sm font-semibold text-red-700">Missing ({result.missing_operations.length})</p>{result.missing_operations.map((item, index) => <p key={index} className="mt-2 break-words text-xs text-slate-600">{item.operation}<br />{item.resource_id}</p>)}</div></div></CardContent></Card>}
    </div><div className="space-y-5">{result.missing_information.length > 0 && <Card className="border-amber-200"><CardHeader><div><CardTitle>Missing information</CardTitle><CardDescription>Evidence required for a complete assessment.</CardDescription></div></CardHeader><CardContent><ul className="space-y-2 text-sm text-amber-900">{result.missing_information.map((item) => <li key={item}>• {readable(item)}</li>)}</ul></CardContent></Card>}
      <Card><CardHeader><div><CardTitle>Recommended corrections</CardTitle><CardDescription>Evidence-based actions; ARCA does not approve or activate access.</CardDescription></div></CardHeader><CardContent>{result.recommendations.length ? <ul className="space-y-2 text-sm leading-6 text-slate-600">{result.recommendations.map((item) => <li key={item} className="flex gap-2"><ShieldAlert className="mt-1 size-4 shrink-0 text-amber-600" />{item}</li>)}</ul> : <p className="text-sm text-slate-500">No corrective recommendation was returned.</p>}</CardContent></Card>
      <Card><CardHeader><div><CardTitle>Supporting evidence</CardTitle><CardDescription>Original synthetic evidence identifiers retained by the API.</CardDescription></div><Badge variant="neutral">{result.evidence.length}</Badge></CardHeader><CardContent className="flex flex-wrap gap-2">{result.evidence.map((item, index) => <code key={index} className="rounded-md border border-blue-100 bg-blue-50 px-2.5 py-1.5 text-xs font-semibold text-blue-800">{show(item.evidence_id)}</code>)}</CardContent></Card>
    </div></div><AiAnalysisPanel analysis={result.ai_analysis} />{result.stage === "change" ? <ChangeQualityActions provider="azure" changeId={result.change_id} findings={result.findings} missingInformation={result.missing_information} assistanceMode={assistanceMode} /> : <AskArcaAction sourceAgent="A2" provider="azure" changeId={result.change_id} evidenceReferences={result.evidence.map((item)=>String(item.evidence_id||""))} question={`Explain the access findings for Azure change ${result.change_id} and recommend evidence-backed next steps.`} />}</section>;
}
