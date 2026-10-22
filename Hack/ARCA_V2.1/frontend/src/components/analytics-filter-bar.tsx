"use client";

import { SlidersHorizontal } from "lucide-react";
import type { AnalyticsFilters, AnalyticsSeverity } from "@/types/api";

export function AnalyticsFilterBar({ filters, onChange, showProvider = false }: { filters: AnalyticsFilters; onChange: (next: AnalyticsFilters) => void; showProvider?: boolean }) {
  const input = "mt-1 block h-10 min-w-36 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20";
  return <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
    <div className="hidden size-9 place-items-center rounded-lg bg-blue-50 text-blue-700 sm:grid"><SlidersHorizontal className="size-4" /></div>
    {showProvider && <label className="text-xs font-semibold text-slate-500">Provider<select value={filters.provider} onChange={(event) => onChange({ ...filters, provider: event.target.value as AnalyticsFilters["provider"] })} className={input}><option value="all">All providers</option><option value="aws">AWS</option><option value="azure">Azure</option><option value="snowflake">Snowflake</option></select></label>}
    <label className="text-xs font-semibold text-slate-500">Time period<select value={filters.days ?? "all"} onChange={(event) => onChange({ ...filters, days: event.target.value === "all" ? null : Number(event.target.value) as 7 | 15 | 30 })} className={input}><option value="7">Last 7 days</option><option value="15">Last 15 days</option><option value="30">Last 30 days</option><option value="all">All available</option></select></label>
    <label className="text-xs font-semibold text-slate-500">Severity<select value={filters.severity} onChange={(event) => onChange({ ...filters, severity: event.target.value as AnalyticsSeverity })} className={input}><option value="all">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
  </div>;
}
