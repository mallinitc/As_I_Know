import assert from "node:assert/strict";
import test from "node:test";
import { createArcaApiClient } from "./arca-api.ts";

const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});
const completed={run_id:"eval-123",status:"completed",timestamp:"2026-10-23T00:00:00Z",evaluation_mode:"deterministic_and_mocked_llm",live_llm_calls:0,scorecard:{total_evaluation_cases:29,executed_cases:29,passed_cases:29,failed_cases:0,skipped_cases:0,test_pass_rate:100,decision_accuracy:100,high_risk_recall:null,false_positive_rate:null,groundedness:100,agent_task_success_rate:100,security_guardrail_pass_rate:100},cases:[]};

test("evaluation client runs only the allowlisted offline mode and polls results",async()=>{
  const calls:Array<{url:string;init?:RequestInit}>=[];
  const fetchImpl=(async(input:string|URL|Request,init?:RequestInit)=>{calls.push({url:String(input),init});if(String(input).endsWith("/history"))return response({items:[completed]});return response(completed)}) as typeof fetch;
  const client=createArcaApiClient({baseUrl:"http://arca.test",fetchImpl});
  assert.equal((await client.getLatestEvaluation()).status,"completed");
  assert.equal((await client.runEvaluation()).live_llm_calls,0);
  assert.equal((await client.getEvaluationRun("eval-123")).scorecard?.decision_accuracy,100);
  assert.equal((await client.getEvaluationHistory()).items.length,1);
  const post=calls.find(call=>call.init?.method==="POST");
  assert.deepEqual(JSON.parse(String(post?.init?.body)),{mode:"deterministic_and_mocked_llm"});
});
