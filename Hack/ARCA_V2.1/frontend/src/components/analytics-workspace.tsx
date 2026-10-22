"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useEnvironment } from "@/components/app-shell";
import { AnalyticsFilterBar } from "@/components/analytics-filter-bar";
import { DistributionBars, DistributionDonut, RiskTrendChart } from "@/components/dashboard-charts";
import { DashboardSkeleton } from "@/components/dashboard-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getAnalyticsAccess, getAnalyticsExecution, getAnalyticsRisks } from "@/lib/arca-api";
import type { AnalyticsAccessResponse, AnalyticsExecutionResponse, AnalyticsFilters, AnalyticsRisksResponse } from "@/types/api";

export function AnalyticsWorkspace() {
  const { environment } = useEnvironment(); const [filters, setFilters] = useState<AnalyticsFilters>({ provider: "all", days: null, severity: "all" });
  const [data, setData] = useState<{ risks: AnalyticsRisksResponse; execution: AnalyticsExecutionResponse; access: AnalyticsAccessResponse } | null>(null); const [error, setError] = useState(""); const [reload, setReload] = useState(0);
  const effectiveFilters = useMemo(() => ({ ...filters, provider: environment }), [environment, filters]);
  useEffect(() => { let active = true; Promise.all([getAnalyticsRisks(effectiveFilters), getAnalyticsExecution(effectiveFilters), getAnalyticsAccess(effectiveFilters)]).then(([risks, execution, access]) => { if (active) { setData({ risks, execution, access }); setError(""); } }).catch((reason: Error) => { if (active) setError(reason.message); }); return () => { active = false; }; }, [effectiveFilters, reload]);
  if (!data && !error) return <DashboardSkeleton />;
  if (error) return <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center"><h2 className="font-bold text-red-900">Analytics could not be loaded</h2><p className="mt-2 text-sm text-red-700">{error}</p><Button className="mt-4" onClick={() => { setError(""); setReload((value) => value + 1); }}><RefreshCw className="size-4" /> Retry</Button></div>;
  if (!data) return null;
  const compliance = [{ name: "compliant", value: data.execution.summary.compliant }, { name: "noncompliant", value: data.execution.summary.noncompliant }, { name: "review_or_unknown", value: data.execution.summary.review_or_unknown }];
  return <div className="space-y-6">
    <section className="flex flex-col justify-between gap-5 xl:flex-row xl:items-end"><div><div className="flex flex-wrap gap-2"><Badge>Assurance analytics</Badge><Badge variant="neutral">{data.risks.metadata.dataset_label}</Badge></div><h2 className="mt-4 text-3xl font-bold tracking-[-0.03em] text-[#102a43] sm:text-4xl">Risk and control intelligence</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 sm:text-base">Explore reconciled findings from native V2 validation and execution evidence. Unknown outcomes remain separate from compliance.</p></div><AnalyticsFilterBar filters={effectiveFilters} onChange={(next) => { setError(""); setFilters(next); }} /></section>
    <p className="text-xs text-slate-400">Snapshot reference {new Date(data.risks.metadata.reference_timestamp).toLocaleString()} · Synthetic Demo Dataset · {data.risks.total_findings} distinct findings</p>
    <section className="grid gap-6 xl:grid-cols-2"><DistributionDonut title="Risk severity distribution" description="Distinct findings by normalized severity" data={data.risks.findings_by_severity} /><DistributionDonut title="Findings by cloud provider" description="Provider-aware findings after deduplication" data={data.risks.findings_by_provider} /></section>
    <section className="grid gap-6 xl:grid-cols-2"><DistributionDonut title="Execution compliance breakdown" description="Compliant, adverse, and evidence-limited scenario outcomes" data={compliance} /><DistributionBars title="Access risk categories" description={`${data.access.access_risk_findings} access and role findings`} data={data.access.categories} /></section>
    <section className="grid gap-6 xl:grid-cols-2"><DistributionBars title="Execution deviation categories" description={`${data.execution.deviations} distinct execution deviations`} data={data.execution.categories} /><RiskTrendChart data={data.risks.findings_over_time} /></section>
    <Card><CardHeader><div><CardTitle>Evidence coverage summary</CardTitle><CardDescription>Approved changes linked to observed execution evidence</CardDescription></div></CardHeader><CardContent><div className="flex flex-col gap-4 sm:flex-row sm:items-center"><div className="grid size-24 shrink-0 place-items-center rounded-full bg-blue-50 text-2xl font-bold text-blue-700">{data.execution.evidence_coverage.percentage === null ? "N/A" : `${data.execution.evidence_coverage.percentage}%`}</div><div><p className="font-semibold text-slate-900">{data.execution.evidence_coverage.covered} of {data.execution.evidence_coverage.eligible} eligible changes have linked evidence</p><p className="mt-1 text-sm text-slate-500">{data.execution.evidence_coverage.unavailable_reason ?? "Coverage indicates evidence availability, not proof that every approved operation completed successfully."}</p><p className="mt-3 text-xs text-amber-700">{Object.values(data.access.unavailable_metrics)[0]}</p></div></div></CardContent></Card>
  </div>;
}
