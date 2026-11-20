import type { LucideIcon } from "lucide-react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { Metric } from "@/types/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function MetricCard({ metric, icon: Icon, tone }: { metric: Metric; icon: LucideIcon; tone: "blue" | "emerald" | "amber" | "red" }) {
  const tones = { blue: "bg-blue-50 text-blue-700", emerald: "bg-emerald-50 text-emerald-700", amber: "bg-amber-50 text-amber-700", red: "bg-red-50 text-red-700" };
  const Trend = metric.trend === "up" ? ArrowUpRight : metric.trend === "down" ? ArrowDownRight : Minus;
  const favorable = (metric.label === "High-risk findings" && metric.trend === "down") || metric.trend === "up";
  return <Card className="group transition duration-200 hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-[0_12px_35px_rgba(15,23,42,0.08)]"><CardContent className="p-5"><div className="flex items-start justify-between"><div className={cn("grid size-10 place-items-center rounded-xl", tones[tone])}><Icon className="size-5" aria-hidden="true" /></div><span className={cn("flex items-center gap-1 text-xs font-semibold", metric.trend === "neutral" ? "text-slate-500" : favorable ? "text-emerald-600" : "text-red-600")}><Trend className="size-3.5" />{metric.change}</span></div><p className="mt-5 text-3xl font-bold tracking-tight text-[#102a43]">{metric.value}</p><p className="mt-1 text-sm font-semibold text-slate-700">{metric.label}</p><p className="mt-1 text-xs text-slate-500">{metric.detail}</p></CardContent></Card>;
}
