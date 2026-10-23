"use client";

import Link from "next/link";
import { ArrowRight, Database, MonitorCog } from "lucide-react";

import { useEnvironment } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { agentWorkspaces, getAgentWorkspace, isWorkspaceAvailable, type AgentNumber } from "@/data/agent-workspaces";
import { cn } from "@/lib/utils";
import { can, capabilityForPath } from "@/lib/persona";

const environmentNames = { all: "All environments", aws: "AWS", azure: "Azure", snowflake: "Snowflake" } as const;

export function AgentWorkspaceHeader({ agent, providerDetail }: { agent: AgentNumber; providerDetail?: string }) {
  const { environment,persona } = useEnvironment();
  const workspace = getAgentWorkspace(agent);
  const visibleWorkspaces=agentWorkspaces.filter(item=>{const capability=capabilityForPath(item.href);return (!capability||can(persona,capability))&&isWorkspaceAvailable(item.href,environment)});

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-blue-100 bg-gradient-to-r from-blue-50 to-white p-5 sm:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>A{workspace.number}</Badge>
          <Badge variant="neutral"><Database className="mr-1 size-3" />Synthetic Demo Dataset</Badge>
          <Badge variant="neutral"><MonitorCog className="mr-1 size-3" />{workspace.executionMode}</Badge>
        </div>
        <h1 className="mt-3 text-2xl font-bold tracking-tight text-[#102a43] sm:text-3xl">{workspace.name}</h1>
        <p className="mt-1 max-w-3xl text-sm font-medium leading-6 text-slate-700">{providerDetail ?? workspace.detail}</p>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-500">
          <span><strong className="text-slate-700">Environment:</strong> {environmentNames[environment]}</span>
          <span><strong className="text-slate-700">Execution mode:</strong> {workspace.executionMode}</span>
        </div>
      </section>
      <nav aria-label="Five-agent evaluation workflow" className="overflow-x-auto rounded-xl border border-slate-200 bg-white p-2 shadow-sm">
        <ol className="flex min-w-max items-center gap-1">
          {visibleWorkspaces.map((item, index) => {
            const active = item.number === agent;
            return (
              <li key={item.number} className="flex items-center gap-1">
                <Link href={item.href} aria-current={active ? "step" : undefined} className={cn("flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500", active ? "border-blue-600 bg-blue-600 text-white shadow-sm" : "border-transparent text-slate-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-800")}>
                  <span className={cn("grid size-5 place-items-center rounded-full text-[10px]", active ? "bg-white/20" : "bg-slate-100")}>{item.number}</span>
                  {item.name}
                </Link>
                {index < visibleWorkspaces.length - 1 && <ArrowRight className="size-3.5 text-slate-300" aria-hidden="true" />}
              </li>
            );
          })}
        </ol>
      </nav>
    </div>
  );
}
