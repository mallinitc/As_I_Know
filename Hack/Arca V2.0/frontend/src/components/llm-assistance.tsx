"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Sparkles } from "lucide-react";
import { getAskArcaCapabilities } from "@/lib/arca-api";
import type { AiAnalysis, AskLlmCapability, AssistanceMode } from "@/types/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function AssistanceModeSelector({ mode, onChange, disabled = false, sharedAgentDisclosure = false }: { mode: AssistanceMode; onChange: (mode: AssistanceMode) => void; disabled?: boolean; sharedAgentDisclosure?: boolean }) {
  const [capability, setCapability] = useState<AskLlmCapability | null>(null);
  useEffect(() => { getAskArcaCapabilities().then((value) => setCapability(value.llm)).catch(() => setCapability({ enabled: false, available: false, provider: null, model_identifier: null, status: "unavailable" })); }, []);
  const available = capability?.available === true;
  return <fieldset className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><legend className="text-sm font-semibold text-slate-700">Analysis mode</legend><div className="flex gap-2"><Badge variant={available ? "success" : "neutral"}>{available ? "LLM available" : `LLM ${capability?.status ?? "checking"}`}</Badge>{capability?.model_identifier && <Badge variant="neutral">{capability.model_identifier}</Badge>}</div></div>
    <div className="mt-3 inline-flex rounded-lg border border-slate-200 bg-white p-1"><button type="button" aria-pressed={mode === "deterministic"} onClick={() => onChange("deterministic")} disabled={disabled} className={`rounded-md px-3 py-2 text-sm font-semibold ${mode === "deterministic" ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-blue-50"}`}>Deterministic</button><button type="button" aria-pressed={mode === "llm_assisted"} onClick={() => onChange("llm_assisted")} disabled={disabled || !available} className={`rounded-md px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${mode === "llm_assisted" ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-blue-50"}`}>LLM Assisted</button></div>
    <p className="mt-2 text-xs text-slate-500">Deterministic validation remains authoritative. LLM Assisted adds a separate evidence-grounded explanation.</p>
    {sharedAgentDisclosure && <p className="mt-1 text-xs font-medium text-blue-700">Snowflake uses a shared Agent 1 / Agent 2 assessment and one advisory model call.</p>}
  </fieldset>;
}

export function AiAnalysisPanel({ analysis }: { analysis?: AiAnalysis | null }) {
  if (!analysis || analysis.execution_mode === "deterministic") return null;
  const complete = analysis.llm_invoked && analysis.llm_status === "completed";
  return <Card className={complete ? "border-blue-200" : "border-amber-200"}><CardHeader><div><p className="text-xs font-semibold uppercase tracking-wider text-blue-700">AI Analysis</p><CardTitle className="mt-1">Advisory interpretation</CardTitle></div><div className="flex flex-wrap gap-2"><Badge variant={complete ? "success" : "warning"}>{analysis.llm_status.replaceAll("_", " ")}</Badge>{analysis.model_identifier&&<Badge variant="neutral">{analysis.model_identifier}</Badge>}{analysis.token_usage&&<Badge variant="neutral">{analysis.token_usage.total_tokens??0} tokens</Badge>}</div></CardHeader><CardContent className="space-y-4">{complete ? <><p className="text-sm leading-6 text-slate-700">{analysis.ai_summary}</p>{analysis.ai_observations.length > 0 && <div><h3 className="text-sm font-semibold text-slate-800">Observations</h3><ul className="mt-2 space-y-2 text-sm text-slate-600">{analysis.ai_observations.map((item) => <li key={item} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-blue-600" />{item}</li>)}</ul></div>}{analysis.ai_recommendations.length > 0 && <div><h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800"><Sparkles className="size-4 text-blue-600" />Recommended actions</h3><ul className="mt-2 space-y-2 text-sm text-slate-600">{analysis.ai_recommendations.map((item) => <li key={item}>• {item}</li>)}</ul></div>}{analysis.evidence_references.length > 0 && <div className="flex flex-wrap gap-2">{analysis.evidence_references.map((id) => <code key={id} className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-800">{id}</code>)}</div>}</> : <p className="flex gap-2 text-sm text-amber-800"><AlertTriangle className="size-4 shrink-0" />LLM assistance was unavailable. The deterministic assessment above is complete and unchanged.</p>}{analysis.limitations.length > 0 && <div className="border-t pt-3 text-xs text-slate-500">{analysis.limitations.map((item) => <p key={item}>{item}</p>)}</div>}</CardContent></Card>;
}
