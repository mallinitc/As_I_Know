"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, LoaderCircle, MessageSquareText } from "lucide-react";
import { getLatestFeedback, submitFeedback } from "@/lib/arca-api";
import type { FeedbackDecision, FeedbackRecord } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const choices:FeedbackDecision[]=["Correct","Incorrect","Needs Review"];

type FeedbackProps={assessmentId:string;stage:"A1"|"A2"|"A3"|"A4"|"A5";provider:"azure"|"aws"|"snowflake"|"all";originalDecision:string;resultReference?:string;findingReference?:string};

export function AssessmentFeedback(props:FeedbackProps){
  return <FeedbackPanel key={props.assessmentId} {...props}/>;
}

function FeedbackPanel({assessmentId,stage,provider,originalDecision,resultReference,findingReference}:FeedbackProps){
  const[decision,setDecision]=useState<FeedbackDecision|"">("");const[reason,setReason]=useState("");const[saved,setSaved]=useState<FeedbackRecord|null>(null);const[busy,setBusy]=useState(false);const[error,setError]=useState("");
  useEffect(()=>{let active=true;getLatestFeedback(assessmentId,stage).then(x=>{if(active&&x.item){setSaved(x.item);setDecision(x.item.feedback_decision);setReason(x.item.feedback_reason)}}).catch(()=>{});return()=>{active=false}},[assessmentId,stage]);
  async function submit(){if(!decision||busy)return;setBusy(true);setError("");try{const submissionId=typeof crypto!=="undefined"&&crypto.randomUUID?crypto.randomUUID():`feedback-${Date.now()}`;setSaved(await submitFeedback({submission_id:submissionId,assessment_id:assessmentId,stage,provider,result_reference:resultReference,finding_reference:findingReference,original_decision:originalDecision,feedback_decision:decision,feedback_reason:reason}))}catch(e){setError(e instanceof Error?e.message:"Feedback could not be saved.")}finally{setBusy(false)}}
  return <Card className="border-blue-100"><CardHeader><div><CardTitle className="flex items-center gap-2"><MessageSquareText className="size-5 text-blue-600"/>Assessment feedback</CardTitle><CardDescription>Was ARCA&apos;s assessment correct? Feedback is recorded separately and never changes the deterministic result.</CardDescription></div>{saved&&<span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700"><CheckCircle2 className="size-4"/>Saved</span>}</CardHeader><CardContent className="space-y-4"><fieldset><legend className="sr-only">Feedback decision</legend><div className="flex flex-wrap gap-2">{choices.map(choice=><button key={choice} type="button" aria-pressed={decision===choice} onClick={()=>setDecision(choice)} className={`rounded-lg border px-3 py-2 text-sm font-semibold ${decision===choice?"border-blue-600 bg-blue-600 text-white":"border-slate-200 bg-white text-slate-700 hover:bg-blue-50"}`}>{choice}</button>)}</div></fieldset><label className="block text-sm font-semibold text-slate-700">Feedback reason (optional)<textarea value={reason} maxLength={2000} onChange={e=>setReason(e.target.value)} className="mt-2 min-h-20 w-full rounded-lg border border-slate-200 p-3 text-sm font-normal outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200"/></label><div className="flex flex-wrap items-center gap-3"><Button onClick={submit} disabled={!decision||busy}>{busy&&<LoaderCircle className="size-4 animate-spin"/>}Submit Feedback</Button>{saved&&<span className="text-xs text-slate-500">Latest response: {saved.feedback_decision} · {new Date(saved.timestamp_utc).toLocaleString()}</span>}</div>{error&&<p role="alert" className="text-sm text-red-700">{error}</p>}</CardContent></Card>;
}
