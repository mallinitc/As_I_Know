import assert from "node:assert/strict";
import test from "node:test";
import { directInvestigation, initialInvestigationState, investigationReducer, scopeFollowUp } from "./ask-investigation-state.ts";
import type { AskResponse } from "@/types/api";

function response(id:string, changeId:string):AskResponse {
  return { investigation_id:id, original_question:"question", resolved_intent:{change_id:changeId}, providers_investigated:["azure"], execution_mode:"deterministic", overall_status:"POTENTIAL_RISK", investigation_summary:changeId, findings:[{change_id:changeId}], evidence_references:[], activity_timeline:[], tool_execution_trace:[], confidence:"limited", evidence_limitations:[], recommended_actions:[], clarification_request:null, llm_provider:null, llm_status:"not_invoked", model_identifier:null, token_usage:null, execution_metrics:{agent_id:"A5",execution_mode:"deterministic",provider:null,model_identifier:null,llm_invocation_status:"not_invoked",model_call_count:0,input_tokens:0,output_tokens:0,total_tokens:0,model_execution_time_ms:0,total_analysis_time_ms:1,estimated_cost_usd:0,pricing_catalog_version:"test",cost_status:"not_applicable",call_details:[]}, model_generated_explanation:null, llm_evidence_citations:[], llm_error:null, conversation_context:{provider:"azure",selected_resource:`/resources/${changeId}`} };
}

test("new contextual investigation clears unrelated conversation and results",()=>{
  const old=initialInvestigationState({investigationId:"old",provider:"azure",changeId:"CHG-AZ-2011",sourceAgent:"A2"});
  const running=investigationReducer(old,{type:"request_started",investigationId:"old",requestId:1});
  const completed=investigationReducer(running,{type:"request_succeeded",investigationId:"old",requestId:1,question:"old",response:response("R1","CHG-AZ-2011")});
  const next=investigationReducer(completed,{type:"begin",context:{investigationId:"new",provider:"azure",changeId:"CHG-AZ-2022",sourceAgent:"A2"}});
  assert.equal(next.turns.length,0); assert.equal(next.active,null); assert.equal(next.context.changeId,"CHG-AZ-2022");
  assert.ok(!JSON.stringify(next).includes("CHG-AZ-2011"));
});

test("slow response from an old investigation cannot overwrite the active investigation",()=>{
  let state=initialInvestigationState({investigationId:"old",provider:"azure",changeId:"CHG-AZ-2011",sourceAgent:"A2"});
  state=investigationReducer(state,{type:"request_started",investigationId:"old",requestId:1});
  state=investigationReducer(state,{type:"begin",context:{investigationId:"new",provider:"azure",changeId:"CHG-AZ-2022",sourceAgent:"A2"}});
  const unchanged=investigationReducer(state,{type:"request_succeeded",investigationId:"old",requestId:1,question:"old",response:response("OLD","CHG-AZ-2011")});
  assert.equal(unchanged.context.changeId,"CHG-AZ-2022"); assert.equal(unchanged.active,null); assert.equal(unchanged.turns.length,0);
});

test("follow-ups remain in one session and failures never restore stale findings",()=>{
  let state=initialInvestigationState({investigationId:"session",provider:"azure",changeId:"CHG-AZ-2022",sourceAgent:"A2"});
  state=investigationReducer(state,{type:"request_started",investigationId:"session",requestId:1});
  state=investigationReducer(state,{type:"request_succeeded",investigationId:"session",requestId:1,question:"first",response:response("R1","CHG-AZ-2022")});
  state=investigationReducer(state,{type:"request_started",investigationId:"session",requestId:2});
  assert.equal(state.active,null);
  state=investigationReducer(state,{type:"request_failed",investigationId:"session",requestId:2,error:"Actionable failure"});
  assert.equal(state.active,null); assert.equal(state.turns.length,1); assert.equal(state.error,"Actionable failure");
  assert.match(scopeFollowUp("Who approved it?",state.context,true),/CHG-AZ-2022/);
  assert.match(scopeFollowUp("Explain this",state.context,false),/Contextual question/);
});

test("direct and new investigations start clean",()=>{
  const state=initialInvestigationState(directInvestigation("direct-1"));
  assert.equal(state.turns.length,0); assert.equal(state.active,null); assert.equal(state.running,false);
  assert.equal(scopeFollowUp("Fresh question",state.context,false),"Fresh question");
});
