import assert from "node:assert/strict";
import test from "node:test";

import { ArcaApiError, createArcaApiClient } from "./arca-api.ts";

const scenarios=Array.from({length:15},(_,index)=>({scenario_id:`S2-${index+1}`,name:`Scenario ${index+1}`,mode:index<5?"change":index<10?"user":"paste",change_id:`CHG-AZ-${2021+index%5}`,pim_request_ids:[`pim-${index+1}`],user_identity:"engineer@example.invalid",expected_outcome:"APPROVE_RECOMMENDED",explanation:"Verified V1 scenario",access_state:"All"}));
const metrics={agent_id:"A2",execution_mode:"deterministic",provider:null,model_identifier:null,llm_invocation_status:"not_invoked",model_call_count:0,input_tokens:0,output_tokens:0,total_tokens:0,model_execution_time_ms:0,total_analysis_time_ms:1,estimated_cost_usd:0,pricing_catalog_version:"test",cost_status:"not_applicable",call_details:[]};
const assessment={provider:"azure",mode:"change",evaluation_timestamp:"2026-10-22T00:00:00Z",overall_assessment:"APPROVE_RECOMMENDED",risk_classification:"LOW",records:[],assessments:[],findings:[],missing_information:[],recommendations:[],evidence:[],disclaimer:"Recommendation only",ai_analysis:{execution_mode:"deterministic",llm_invoked:false,llm_status:"not_invoked",model_identifier:null,ai_summary:null,ai_observations:[],ai_recommendations:[],evidence_references:[],limitations:[],execution_metrics:metrics}};
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});

test("Stage 2 loads all V1 scenarios and routes Azure assessment without Snowflake leakage",async()=>{
  const calls:string[]=[];
  const client=createArcaApiClient({baseUrl:"http://arca.test",fetchImpl:(async(input:string|URL|Request)=>{const url=String(input);calls.push(url);return url.includes("demo-scenarios")?response({provider:"azure",synthetic:true,count:15,items:scenarios}):response(assessment)}) as typeof fetch});
  assert.equal((await client.getStage2Scenarios()).items.length,15);
  assert.equal((await client.assessStage2({mode:"change",change_id:"CHG-AZ-2021"})).overall_assessment,"APPROVE_RECOMMENDED");
  assert.ok(calls.every(url=>!url.includes("snowflake")));
  assert.ok(calls[1].includes("/agents/access-intelligence/stage2/assess"));
});

test("Stage 2 404 is Azure-specific and identifies a stale API route",async()=>{
  const client=createArcaApiClient({fetchImpl:(async()=>response({detail:"not found"},404)) as typeof fetch});
  await assert.rejects(client.getStage2Scenarios(),(error:unknown)=>error instanceof ArcaApiError&&error.message.includes("Azure demo scenarios endpoint")&&!error.message.includes("Snowflake"));
});
