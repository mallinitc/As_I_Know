"use client";

import { useState } from "react";
import { AnalyticsWorkspace } from "@/components/analytics-workspace";
import { EvaluationWorkspace } from "@/components/evaluation-workspace";

export function AnalyticsPageWorkspace(){
  const[tab,setTab]=useState<"overview"|"evaluation">("overview");
  return <div className="space-y-6">
    <div role="tablist" aria-label="Analytics sections" className="inline-flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
      <button role="tab" aria-selected={tab==="overview"} onClick={()=>setTab("overview")} className={`rounded-lg px-4 py-2 text-sm font-bold transition ${tab==="overview"?"bg-blue-600 text-white":"text-[#102a43] hover:bg-blue-50"}`}>Overview</button>
      <button role="tab" aria-selected={tab==="evaluation"} onClick={()=>setTab("evaluation")} className={`rounded-lg px-4 py-2 text-sm font-bold transition ${tab==="evaluation"?"bg-blue-600 text-white":"text-[#102a43] hover:bg-blue-50"}`}>Evaluation &amp; Testing</button>
    </div>
    <div role="tabpanel">{tab==="overview"?<AnalyticsWorkspace/>:<EvaluationWorkspace/>}</div>
  </div>;
}
