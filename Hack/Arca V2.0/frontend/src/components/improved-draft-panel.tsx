"use client";

import { useMemo, useState } from "react";
import { AlertCircle, Check, Clipboard, LoaderCircle, Sparkles } from "lucide-react";
import { AskArcaAction } from "@/components/ask-arca-action";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { improveChangeDraft } from "@/lib/arca-api";
import type { AssistanceMode, ChangeDraftResponse, ImprovedChangeDraft } from "@/types/api";

type Finding = {field?:unknown;category?:unknown;message?:unknown;explanation?:unknown;reason?:unknown;recommendation?:unknown};
const WHY:Record<string,string> = {
  change_id:"Links approval, access, and execution evidence.", description:"Explains the intended business and technical change.",
  environment:"Determines the applicable risk and control context.", implementer:"Establishes who is authorized to perform the change.",
  start:"Defines when implementation may begin.", end:"Defines when approved activity must stop.", change_window:"Prevents work outside the approved maintenance period.",
  expected:"Defines the operations and targets ARCA should validate.", rollback_plan:"Provides a controlled recovery path if validation fails.",
};
const labels:Record<keyof ImprovedChangeDraft,string> = {change_title:"Change title",change_number:"Change number",business_justification:"Business justification",environment:"Environment",subscription:"Subscription",resource_group:"Resource group",resource_name_or_id:"Resource name / ID",implementer:"Implementer",change_start:"Change start",change_end:"Change end",timezone:"Timezone",required_role:"Required role",required_access_scope:"Required access scope",implementation_steps:"Implementation steps",validation_plan:"Validation plan",rollback_plan:"Rollback plan",expected_outcome:"Expected outcome",risk_and_impact:"Risk and impact"};
const multiline = new Set<keyof ImprovedChangeDraft>(["business_justification","resource_name_or_id","implementation_steps","validation_plan","rollback_plan","expected_outcome","risk_and_impact"]);

function text(value:unknown):string { return typeof value === "string" ? value : value == null ? "" : JSON.stringify(value); }
function serviceNowText(draft:ImprovedChangeDraft):string { return (Object.keys(labels) as (keyof ImprovedChangeDraft)[]).map((key) => `${labels[key].toUpperCase()}\n${Array.isArray(draft[key]) ? (draft[key] as string[]).map((item,index)=>`${index+1}. ${item}`).join("\n") : draft[key]}`).join("\n\n"); }

export function ChangeQualityActions({ provider, changeId, findings, missingInformation, assistanceMode }: {provider:"aws"|"azure"|"snowflake";changeId:string;findings:Finding[];missingInformation:string[];assistanceMode:AssistanceMode}) {
  const [response,setResponse]=useState<ChangeDraftResponse|null>(null),[draft,setDraft]=useState<ImprovedChangeDraft|null>(null),[running,setRunning]=useState(false),[error,setError]=useState(""),[copied,setCopied]=useState(false);
  const guidance=useMemo(()=>{
    const items=findings.map((finding)=>({field:text(finding.field||finding.category||"change information"),message:text(finding.message||finding.explanation||finding.reason||"Additional information is required."),recommendation:text(finding.recommendation)}));
    for(const field of missingInformation) if(!items.some((item)=>item.field===field)) items.push({field,message:`${field.replaceAll("_"," ")} is missing.`,recommendation:"Add the source-supported value before implementation."});
    return items;
  },[findings,missingInformation]);
  async function improve(){if(running)return;setRunning(true);setError("");setCopied(false);try{const value=await improveChangeDraft(provider,changeId,assistanceMode);setResponse(value);setDraft(value.draft);}catch(reason){setError(reason instanceof Error?reason.message:"The draft could not be prepared.");}finally{setRunning(false)}}
  async function copy(){if(!draft)return;try{await navigator.clipboard.writeText(serviceNowText(draft));setCopied(true);}catch{setError("Clipboard access was unavailable. Select and copy the editable fields manually.");}}
  function update(key:keyof ImprovedChangeDraft,value:string){if(!draft)return;setDraft({...draft,[key]:Array.isArray(draft[key])?value.split("\n").map(x=>x.trim()).filter(Boolean):value});setCopied(false);}
  return <div className="space-y-5">
    {guidance.length>0&&<Card className="border-amber-200"><CardHeader><div><CardTitle>Missing-field guidance</CardTitle><CardDescription>Why each incomplete or inconsistent field matters before execution.</CardDescription></div><Badge variant="warning">{guidance.length}</Badge></CardHeader><CardContent className="space-y-3">{guidance.map((item,index)=><div key={`${item.field}-${index}`} className="rounded-lg border border-amber-100 bg-amber-50/60 p-3"><p className="text-sm font-semibold text-amber-950">{item.field.replaceAll("_"," ")}</p><p className="mt-1 text-sm text-amber-900">{item.message}</p><p className="mt-1 text-xs text-amber-800"><b>Why it matters:</b> {WHY[item.field]||"It supports a complete, reviewable, and evidence-backed change request."}</p>{item.recommendation&&<p className="mt-1 text-xs text-slate-600"><b>Correction:</b> {item.recommendation}</p>}<div className="mt-3"><AskArcaAction sourceAgent="A1" provider={provider} changeId={changeId} finding={item.field} question={`Help me clarify ${item.field.replaceAll("_"," ")} for ${changeId} in ${provider}. Use only the selected change context and do not require execution logs.`}/></div></div>)}</CardContent></Card>}
    <Card><CardHeader><div><CardTitle>Improved Draft</CardTitle><CardDescription>Creates an editable ServiceNow-style draft from known evidence. Unknown values stay empty.</CardDescription></div>{response&&<Badge variant={response.llm_invoked?"success":"neutral"}>{response.llm_invoked?"AI refined":"Source template"}</Badge>}</CardHeader><CardContent className="space-y-4"><div className="flex flex-wrap items-center gap-3"><Button onClick={improve} disabled={running}>{running?<LoaderCircle className="size-4 animate-spin"/>:<Sparkles className="size-4"/>}{assistanceMode==="llm_assisted"?"Improve Draft with AI":"Prepare Editable Draft"}</Button>{running&&<span role="status" className="inline-flex items-center gap-2 text-sm font-medium text-blue-700"><LoaderCircle className="size-4 animate-spin"/>Improving the change draft...</span>}</div>{error&&<p role="alert" className="flex gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"><AlertCircle className="size-4 shrink-0"/>{error}</p>}{response&&<p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{response.disclosure}</p>}
      {draft&&<><div className="grid gap-4 lg:grid-cols-2">{(Object.keys(labels) as (keyof ImprovedChangeDraft)[]).map((key)=>{const value=draft[key];const empty=Array.isArray(value)?value.length===0:!value;const shared=`w-full rounded-lg border px-3 py-2 text-sm outline-none focus:ring-2 ${empty?"border-amber-300 bg-amber-50/40 focus:border-amber-500 focus:ring-amber-200":"border-slate-200 bg-white focus:border-blue-500 focus:ring-blue-200"}`;return <label key={key} className="space-y-1 text-sm font-semibold text-slate-700">{labels[key]}{multiline.has(key)?<textarea className={`${shared} min-h-24`} value={Array.isArray(value)?value.join("\n"):value} placeholder={`[Required: ${labels[key]}]`} onChange={e=>update(key,e.target.value)}/>:<input className={shared} value={String(value)} placeholder={`[Required: ${labels[key]}]`} onChange={e=>update(key,e.target.value)}/>} {empty&&<span className="block text-xs font-normal text-amber-700">Not present in the source change; enter a verified value.</span>}</label>})}</div><div className="flex flex-wrap items-center gap-3 border-t pt-4"><Button variant="outline" onClick={copy}>{copied?<Check className="size-4"/>:<Clipboard className="size-4"/>}{copied?"Copied":"Copy Improved Draft"}</Button><span className="text-xs text-slate-500">Edits remain local and do not modify authoritative change records.</span></div></>}
    </CardContent></Card>
  </div>;
}
