"use client";

import { createContext, useContext, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Activity, BarChart3, Bot, ChevronLeft, ChevronRight, CircleUserRound, ClipboardCheck, KeyRound, LayoutDashboard, Menu, SearchCheck, ShieldCheck, X } from "lucide-react";
import { isWorkspaceAvailable } from "@/data/agent-workspaces";
import { environmentOptions } from "@/data/environment-options";
import type { EnvironmentId } from "@/types/dashboard";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { can, capabilityForPath, landingFor, setPersona, usePersona, type PersonaRole } from "@/lib/persona";

const navGroups = [
  { label: "Overview", items: [{ label: "Executive Dashboard", href: "/", icon: LayoutDashboard }] },
  { label: "Agent Workspace", items: [
    { label: "A1 — Change Quality", href: "/agents/change-quality", icon: ClipboardCheck },
    { label: "A2 — Access Intelligence", href: "/agents/access-intelligence", icon: KeyRound },
    { label: "A3 — Execution Assurance", href: "/execution-assurance", icon: Activity },
    { label: "A4 — Undocumented Changes", href: "/risk-investigations", icon: SearchCheck },
    { label: "A5 — Ask ARCA", href: "/ask-arca", icon: Bot },
  ] },
  { label: "Insights", items: [{ label: "Analytics", href: "/analytics", icon: BarChart3 }] },
];

const navItems = navGroups.flatMap((group) => group.items);
const pageTitles: Record<string, string> = { ...Object.fromEntries(navItems.map((item) => [item.href, item.label])), "/change-assurance": "A1 — Change Quality" };
const EnvironmentContext = createContext<{ environment: EnvironmentId; setEnvironment: (value: EnvironmentId) => void; persona:PersonaRole } | null>(null);

export function useEnvironment() {
  const context = useContext(EnvironmentContext);
  if (!context) throw new Error("useEnvironment must be used inside AppShell");
  return context;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router=useRouter();const persona=usePersona();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [environment, setEnvironment] = useState<EnvironmentId>("all");

  const visibleGroups=navGroups.map(group=>({...group,items:group.items.filter(item=>{const capability=capabilityForPath(item.href);return (!capability||can(persona,capability))&&isWorkspaceAvailable(item.href,environment)})})).filter(group=>group.items.length);
  // Leave a workspace the newly selected environment does not offer (A3 and A4 for Snowflake).
  const changeEnvironment=(value:EnvironmentId)=>{setEnvironment(value);if(!isWorkspaceAvailable(pathname,value))router.replace("/agents/access-intelligence")};
  const required=capabilityForPath(pathname);const authorized=!required||can(persona,required);
  const sidebar = (
    <aside className="flex h-full flex-col bg-[#081b33] text-white">
      <div className={cn("flex h-20 items-center border-b border-white/10 px-5", collapsed && "justify-center px-3")}>
        <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-blue-500 font-black shadow-lg shadow-blue-950/30">A</div>
        {!collapsed && <div className="ml-3"><div className="flex items-center gap-2 text-lg font-bold tracking-tight">ARCA <span className="text-[10px] font-bold tracking-widest text-blue-300">V2</span></div><div className="text-[10px] uppercase tracking-[0.16em] text-slate-400">Risk &amp; Change Assurance</div></div>}
      </div>
      <nav aria-label="Primary navigation" className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
        {visibleGroups.map((group) => <div key={group.label}>{!collapsed && <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">{group.label}</p>}<div className="space-y-1.5">{group.items.map((item) => {
          const active = pathname === item.href || (pathname === "/change-assurance" && item.href === "/agents/change-quality");
          const Icon = item.icon;
          return <Link key={item.href} href={item.href} onClick={() => setMobileOpen(false)} title={collapsed ? item.label : undefined} aria-current={active ? "page" : undefined} className={cn("group flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium text-slate-300 transition-all hover:bg-white/8 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400", active && "bg-blue-600 text-white shadow-lg shadow-blue-950/20", collapsed && "justify-center")}><Icon className="size-[18px] shrink-0" aria-hidden="true" />{!collapsed && <span>{item.label}</span>}</Link>;
        })}</div></div>)}
      </nav>
      <div className="border-t border-white/10 p-3">
        <button type="button" onClick={() => setCollapsed((value) => !value)} className="hidden h-10 w-full items-center justify-center gap-2 rounded-lg text-xs font-semibold text-slate-400 transition-colors hover:bg-white/8 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 lg:flex" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>{collapsed ? <ChevronRight className="size-4" /> : <><ChevronLeft className="size-4" /> Collapse</>}</button>
      </div>
    </aside>
  );

  return (
    <EnvironmentContext.Provider value={{ environment, setEnvironment, persona }}>
      <div className="min-h-screen bg-[#f4f7fb] text-slate-950">
        <div className={cn("fixed inset-y-0 left-0 z-40 hidden transition-[width] duration-200 lg:block", collapsed ? "w-[76px]" : "w-[248px]")}>{sidebar}</div>
        {mobileOpen && <><button aria-label="Close navigation overlay" className="fixed inset-0 z-40 bg-slate-950/45 backdrop-blur-sm lg:hidden" onClick={() => setMobileOpen(false)} /><div className="fixed inset-y-0 left-0 z-50 w-[280px] lg:hidden"><Button variant="ghost" size="icon" className="absolute right-3 top-3 z-10 text-slate-300 hover:bg-white/10 hover:text-white" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X className="size-5" /></Button>{sidebar}</div></>}
        <div className={cn("transition-[padding] duration-200", collapsed ? "lg:pl-[76px]" : "lg:pl-[248px]")}>
          <header className="sticky top-0 z-30 flex h-20 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu className="size-5" /></Button>
              <div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-blue-600">Enterprise assurance</p><h1 className="truncate text-lg font-bold tracking-tight text-[#102a43]">{pageTitles[pathname] ?? "ARCA"}</h1></div>
            </div>
            <div className="flex items-center gap-3 sm:gap-5">
              <label className="hidden text-xs font-semibold text-slate-500 sm:block" htmlFor="global-environment">Environment</label>
              <select id="global-environment" value={environment} onChange={(event) => changeEnvironment(event.target.value as EnvironmentId)} className="h-10 max-w-[180px] rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20" aria-label="Select evidence environment">{environmentOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
              <div className="hidden h-8 w-px bg-slate-200 md:block" />
              <div className="flex items-center gap-2.5" aria-label="Demo persona"><label className="hidden text-right md:block"><span className="block text-[10px] font-bold uppercase tracking-wide text-amber-700">Demo Persona Mode</span><select aria-label="Select demo persona" value={persona} onChange={event=>{const role=event.target.value as PersonaRole;setPersona(role);router.replace(landingFor(role))}} className="bg-transparent text-sm font-semibold text-slate-800 outline-none"><option value="arca_analyst">ARCA Analyst</option><option value="arca_manager">ARCA Manager</option></select></label><CircleUserRound className="size-8 text-slate-500" aria-hidden="true" /></div>
            </div>
          </header>
          <main className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{authorized?children:<section className="mx-auto max-w-2xl rounded-2xl border border-amber-200 bg-white p-8 text-center shadow-sm"><ShieldCheck className="mx-auto size-10 text-amber-600"/><h2 className="mt-4 text-2xl font-bold text-[#102a43]">Access restricted</h2><p className="mt-2 text-sm text-slate-600">The selected demo persona is not authorized for this workspace.</p><button type="button" onClick={()=>router.replace(landingFor(persona))} className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white">Return to authorized workspace</button></section>}</main>
        </div>
        <div className="fixed bottom-4 right-4 z-20 hidden sm:block"><Badge variant="neutral"><ShieldCheck className="mr-1.5 size-3.5" /> Demo evidence only</Badge></div>
      </div>
    </EnvironmentContext.Provider>
  );
}
