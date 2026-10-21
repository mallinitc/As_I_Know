from __future__ import annotations
import json,re,time
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Callable
from uuid import uuid4
from backend.config import PROJECT_ROOT
from backend.llm.gateway import LlmGateway
from backend.llm.providers import LlmGatewayError
from backend.llm.schemas import LlmIntent, LlmPlan, TokenUsage
from backend.repositories.aws import AwsRepository
from backend.repositories.azure import AzureRepository
from backend.repositories.snowflake import SnowflakeRepository
from backend.services.aws_execution import AwsExecutionService
from backend.services.aws_validation import AwsValidationService
from backend.services.azure_execution import AzureExecutionService
from backend.services.azure_validation import AzureValidationService
from backend.services.risk_investigation import RiskInvestigationService
from backend.services.snowflake import SnowflakeValidationService
from backend.services.snowflake_execution import SnowflakeExecutionService
from backend.services.timestamps import parse_utc,utc_text

TOOLS=[
 {"name":"get_change_details","description":"Retrieve a provider change record."},{"name":"validate_change_and_access","description":"Run provider-native deterministic validation."},
 {"name":"verify_change_execution","description":"Correlate a change with provider audit evidence."},{"name":"investigate_user_activity","description":"Investigate a resolved user or principal."},
 {"name":"find_potentially_unapproved_activity","description":"Run Agent 4 discovery without a known change."},{"name":"investigate_role_or_privilege_changes","description":"Filter Agent 4 evidence by role."},
 {"name":"retrieve_supporting_evidence","description":"Preserve evidence IDs returned by deterministic tools."},{"name":"run_cross_environment_risk_investigation","description":"Run Agent 4 across all providers."},
]
PROVIDERS=("aws","azure","snowflake")
class AgentConfigurationError(RuntimeError): pass

class AskArcaService:
 def __init__(self,gateway:LlmGateway|None=None)->None:
  self.risk=RiskInvestigationService(); self.repos={"aws":AwsRepository(),"azure":AzureRepository(),"snowflake":SnowflakeRepository()}
  self.validation={"aws":AwsValidationService(),"azure":AzureValidationService(),"snowflake":SnowflakeValidationService()}
  self.execution={"aws":AwsExecutionService(),"azure":AzureExecutionService(),"snowflake":SnowflakeExecutionService()}
  self.tool_registry={item["name"]:item for item in TOOLS}
  self.gateway=gateway or LlmGateway()
 def scenarios(self)->list[dict[str,Any]]: return json.loads(Path(PROJECT_ROOT,"data","investigations","ask_arca_scenarios.json").read_text(encoding="utf-8"))
 def capabilities(self)->dict[str,Any]: return {"default_mode":"deterministic","modes":["deterministic","llm_assisted"],"providers":list(PROVIDERS)+["all"],"tools":TOOLS,"supported_periods":["today","yesterday","last 24 hours","last 7 days","last 10 days","last 15 days","last 30 days"],"llm":self.gateway.capability()}
 def parse(self,question:str)->dict[str,Any]:
  q=question.strip(); low=q.casefold(); providers=[p for p in PROVIDERS if p in low]
  all_requested="all environment" in low or (len(providers)>1) or "across aws, azure, and snowflake" in low
  change_match=re.search(r"\b(CHG-SF-\d+|CHG-AZ-\d+|CHG\d+)\b",q,re.I); change_id=change_match.group(1).upper() if change_match else None
  if change_id:
   inferred="snowflake" if change_id.startswith("CHG-SF-") else "azure" if change_id.startswith("CHG-AZ-") else "aws"
   providers=[inferred]
  period=10
  match=re.search(r"last\s+(?:the\s+)?(1|7|10|15|30)\s+days?",low)
  if match: period=int(match.group(1))
  elif "last 24 hour" in low or "today" in low: period=1
  elif "yesterday" in low: period=1
  email=re.search(r"[\w.+-]+@[\w.-]+",q); principal=re.search(r"\b(?:AIDA|AROA)-[\w:-]+\b|arn:aws:(?:iam|sts)::\d{12}:[^\s,?]+",q,re.I)
  identity=(email or principal).group(0) if email or principal else None
  if not identity:
   by=re.search(r"(?:performed\s+by|activities\s+by)\s+([A-Za-z0-9_.:-]+)",q,re.I); identity=by.group(1) if by else None
  role=None
  for candidate in ["ACCOUNTADMIN","SECURITYADMIN","OperationsRole","Contributor","Owner"]:
   if candidate.casefold() in low: role=candidate; break
  resource_match=re.search(r"arn:(?:aws|azure):[^\s,?]+|/subscriptions/[^\s,?]+",q,re.I); resource=resource_match.group(0) if resource_match else None
  if change_id: intent="change_execution" if any(x in low for x in ["implemented correctly","execution","executed correctly"]) else "change_investigation"
  elif role: intent="role_investigation"
  elif identity or " user " in f" {low} " or "principal" in low: intent="user_investigation"
  elif all_requested or "across" in low or "all environments" in low: intent="cross_environment_summary"
  elif any(x in low for x in ["unauthorized","unapproved","suspicious","privilege escalation"]): intent="unauthorized_activity"
  else: intent="historical_activity"
  severity="high" if "high-risk" in low or "high severity" in low else "all"
  environment="all" if all_requested else providers[0] if len(providers)==1 else None
  clarification=None
  if intent.startswith("change") and not change_id: clarification="Which change ID should ARCA investigate?"
  elif intent=="user_investigation" and not identity: clarification="Which user, principal ID, ARN, or explicitly mapped email should ARCA investigate?"
  elif not environment: clarification="Which environment should ARCA investigate: AWS, Azure, Snowflake, or all environments?"
  return {"investigation_type":intent,"provider":environment,"change_id":change_id,"user_identifier":identity,"role":role,"resource":resource,"time_period_days":period,"severity":severity,"clarification":clarification,"parser":"deterministic_mock"}
 def _trace(self,traces:list,step_id:str,name:str,fn:Callable[[],Any],summary:str)->Any:
  if name not in self.tool_registry and name not in {"understand_request","resolve_environment","generate_summary"}: raise ValueError("Tool is not allowlisted")
  start=datetime.now(timezone.utc); tick=time.perf_counter()
  try:
   result=fn(); status="completed"; return result
  except Exception: status="failed"; raise
  finally:
   end=datetime.now(timezone.utc); traces.append({"step_id":step_id,"tool_name":name,"status":status,"start_time":utc_text(start),"end_time":utc_text(end),"duration":round(time.perf_counter()-tick,6),"summary":summary})
 def _change(self,p:str,cid:str)->dict[str,Any]:
  items=self.repos[p].changes(); item=next((x for x in items if x.get("change_id")==cid),None)
  if not item: raise ValueError(f"Change {cid} was not found in {p} evidence")
  return item
 def _validate(self,p:str,cid:str,evaluated:datetime)->dict[str,Any]:
  if p=="snowflake": return self.validation[p].validate(cid,evaluated)
  if p=="azure": return {"change":self.validation[p].validate_change(cid),"access":self.validation[p].validate_access(cid)}
  return {"change":self.validation[p].validate_change(cid),"access":self.validation[p].validate_access(cid)}
 def _execute(self,p:str,cid:str,evaluated:datetime)->dict[str,Any]: return self.execution[p].assess_change(cid,evaluated)
 def _risk(self,intent:dict[str,Any],evaluated:datetime)->dict[str,Any]:
  return self.risk.investigate(environment=intent["provider"] or "all",identity=intent.get("user_identifier"),role=intent.get("role"),resource=intent.get("resource"),window_days=intent["time_period_days"],severity=intent["severity"],evaluation_timestamp=evaluated)
 def _ask_deterministic(self,question:str,evaluation_timestamp:datetime|str|None=None,scenario_id:str|None=None,intent_override:dict[str,Any]|None=None,execution_mode:str="mock")->dict[str,Any]:
  scenario=next((x for x in self.scenarios() if x["scenario_id"]==scenario_id),None) if scenario_id else None
  if scenario_id and not scenario: raise ValueError("Unknown Ask ARCA scenario")
  if scenario: question=scenario["question"]; evaluation_timestamp=scenario["evaluation_timestamp"]
  evaluated=parse_utc(evaluation_timestamp) if isinstance(evaluation_timestamp,str) else (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
  traces=[]; intent=self._trace(traces,"01","understand_request",lambda:intent_override or self.parse(question),"Used the validated LLM intent plan." if intent_override else "Parsed the question deterministically; no LLM was invoked.")
  providers=self._trace(traces,"02","resolve_environment",lambda:list(PROVIDERS) if intent["provider"]=="all" else [intent["provider"]] if intent["provider"] else [],"Resolved explicit provider routing.")
  base={"investigation_id":f"ASK-{uuid4().hex[:12].upper()}","original_question":question,"resolved_intent":intent,"providers_investigated":providers,"execution_mode":execution_mode,"tool_execution_trace":traces,"llm_provider":None,"llm_status":"not_invoked","model_identifier":None,"token_usage":None,"model_generated_explanation":None,"llm_evidence_citations":[],"llm_error":None}
  if intent["clarification"]:
   return {**base,"overall_status":"INSUFFICIENT_EVIDENCE","investigation_summary":"More information is required before evidence tools can run.","findings":[],"evidence_references":[],"activity_timeline":[],"confidence":"none","evidence_limitations":["No investigation tool was executed because a critical identifier is ambiguous or missing."],"recommended_actions":[],"clarification_request":intent["clarification"]}
  findings=[]; evidence=[]; timeline=[]; limitations=[]; actions=[]
  if intent["investigation_type"] in {"change_investigation","change_execution"}:
   p=providers[0]; cid=intent["change_id"]
   detail=self._trace(traces,"03","get_change_details",lambda:self._change(p,cid),f"Retrieved {cid} from {p} evidence."); evidence.append({"provider":p,"evidence_id":cid,"type":"change"})
   if intent["investigation_type"]=="change_investigation":
    validation=self._trace(traces,"04","validate_change_and_access",lambda:self._validate(p,cid,evaluated),f"Ran provider-native change and access validation for {cid}.")
    for section in validation.values() if isinstance(validation,dict) and "change" in validation else [validation]: findings.extend(section.get("findings") or [])
   execution=self._trace(traces,"05","verify_change_execution",lambda:self._execute(p,cid,evaluated),f"Correlated {cid} with provider audit evidence."); findings.extend(execution.get("findings") or []); evidence.extend(execution.get("evidence") or []); timeline.extend(execution.get("timeline") or []); limitations.extend(execution.get("limitations") or []); actions.extend(execution.get("recommendations") or [])
  else:
   tool="run_cross_environment_risk_investigation" if intent["provider"]=="all" else "investigate_user_activity" if intent["investigation_type"]=="user_investigation" else "investigate_role_or_privilege_changes" if intent["investigation_type"]=="role_investigation" else "find_potentially_unapproved_activity"
   risk=self._trace(traces,"03",tool,lambda:self._risk(intent,evaluated),"Executed Agent 4 evidence correlation with validated filters."); findings=risk["findings"]; evidence=risk["evidence_references"]; timeline=risk["activity_timeline"]; limitations=risk["evidence_limitations"]; actions=list(dict.fromkeys(x.get("recommendation") for x in findings if x.get("recommendation")))
  evidence=self._trace(traces,"06","retrieve_supporting_evidence",lambda:list({json.dumps(x,sort_keys=True,default=str):x for x in evidence}.values())[:500],"Preserved unique evidence references returned by deterministic tools.")
  confirmed=any(str(x.get("confidence")).casefold()=="confirmed" and str(x.get("severity")).casefold() in {"high","critical"} for x in findings); possible=bool(findings); status="CONFIRMED_DEVIATION" if confirmed else "POTENTIAL_RISK" if possible else "COMPLIANT" if timeline else "INSUFFICIENT_EVIDENCE"
  summary=self._trace(traces,"07","generate_summary",lambda:f"ARCA investigated {len(providers)} environment(s), reviewed {len(timeline)} activity record(s), and returned {len(findings)} evidence-backed finding(s).","Generated a deterministic summary from tool results.")
  return {**base,"tool_execution_trace":traces,"overall_status":status,"investigation_summary":summary,"findings":findings,"evidence_references":evidence,"activity_timeline":timeline,"confidence":"high" if confirmed else "limited" if possible else "high" if timeline else "none","evidence_limitations":list(dict.fromkeys(limitations)),"recommended_actions":actions,"clarification_request":None}

 def _expected_tools(self,intent:dict[str,Any])->set[str]:
  kind=intent["investigation_type"]
  if kind=="change_investigation": return {"get_change_details","validate_change_and_access","verify_change_execution","retrieve_supporting_evidence"}
  if kind=="change_execution": return {"get_change_details","verify_change_execution","retrieve_supporting_evidence"}
  selected="run_cross_environment_risk_investigation" if intent.get("provider")=="all" else "investigate_user_activity" if kind=="user_investigation" else "investigate_role_or_privilege_changes" if kind=="role_investigation" else "find_potentially_unapproved_activity"
  return {selected,"retrieve_supporting_evidence"}

 def _validate_plan(self,plan:LlmPlan,question:str)->dict[str,Any]:
  intent={**plan.intent.model_dump(),"parser":"llm_assisted"}
  question_folded=question.casefold()
  for key in ("change_id","user_identifier","role","resource"):
   value=intent.get(key)
   if value and str(value).casefold() not in question_folded:
    raise LlmGatewayError("invalid_response",f"The LLM returned a {key} that was not explicitly present in the question.")
  if plan.intent.clarification:
   if plan.tool_calls: raise LlmGatewayError("unsupported_tool_plan","A clarification plan cannot execute tools.")
   return intent
  names=[call.tool_name for call in plan.tool_calls]
  if len(names)>5 or any(name not in self.tool_registry for name in names):
   raise LlmGatewayError("unsupported_tool_plan","The LLM requested a tool outside the allowlist or tool-call limit.")
  if len(names)!=len(set(names)) or set(names)!=self._expected_tools(intent):
   raise LlmGatewayError("unsupported_tool_plan","The LLM tool plan was incomplete, redundant, or incompatible with the resolved intent.")
  for call in plan.tool_calls:
   params=call.parameters
   for key in ("provider","change_id","user_identifier","role","resource","time_period_days","severity"):
    supplied=getattr(params,key)
    if supplied is not None and supplied!=intent.get(key):
     raise LlmGatewayError("unsupported_tool_plan",f"The LLM supplied inconsistent {key} parameters.")
  return intent

 @staticmethod
 def _evidence_ids(result:dict[str,Any])->list[str]:
  values=[]
  for item in result.get("evidence_references",[]):
   if isinstance(item,dict):
    value=next((item.get(key) for key in ("evidence_id","eventID","event_data_id","query_id") if item.get(key)),None)
    if value is not None: values.append(str(value))
   elif item is not None: values.append(str(item))
  return list(dict.fromkeys(values))

 @staticmethod
 def _validate_synthesis_claims(summary:str,result:dict[str,Any])->None:
  text=summary.casefold(); status=str(result.get("overall_status") or "").upper()
  compliance_claim=re.search(r"\b(?:is|was|are|were|remains)\s+(?:fully\s+)?(?:compliant|approved|authorized|safe)\b",text)
  confirmed_claim=re.search(r"\b(?:confirmed|proven|definitive|definitively)\s+(?:malicious|unauthorized|breach|violation|deviation|risk)\b",text)
  if compliance_claim and status!="COMPLIANT":
   raise LlmGatewayError("invalid_response","The LLM explanation introduced an unsupported compliance or authorization claim.")
  if confirmed_claim and status!="CONFIRMED_DEVIATION":
   raise LlmGatewayError("invalid_response","The LLM explanation introduced an unsupported confirmed finding.")
  severities={str(item.get("severity") or "").casefold() for item in result.get("findings",[]) if isinstance(item,dict)}
  for severity in ("critical","high","medium","low"):
   if re.search(rf"\b{severity}(?:-severity|\s+(?:severity|finding|risk))\b",text) and severity not in severities:
    raise LlmGatewayError("invalid_response","The LLM explanation introduced an unsupported severity classification.")

 def ask(self,question:str,mode:str="mock",evaluation_timestamp:datetime|str|None=None,scenario_id:str|None=None)->dict[str,Any]:
  normalized={"mock":"mock","deterministic":"deterministic","ai":"llm_assisted","llm_assisted":"llm_assisted"}[mode]
  if normalized!="llm_assisted": return self._ask_deterministic(question,evaluation_timestamp,scenario_id,execution_mode=normalized)
  scenario=next((x for x in self.scenarios() if x["scenario_id"]==scenario_id),None) if scenario_id else None
  if scenario_id and not scenario: raise ValueError("Unknown Ask ARCA scenario")
  if scenario: question=scenario["question"]; evaluation_timestamp=scenario["evaluation_timestamp"]
  capability=self.gateway.capability()
  if not capability["available"]:
   raise AgentConfigurationError("LLM Assisted mode is unavailable because the approved provider is disabled or incompletely configured. Retry in Deterministic mode.")
  usage=TokenUsage(); model=str(capability.get("model_identifier") or ""); result=None
  try:
   plan,model,plan_usage=self.gateway.plan(question,TOOLS); usage=usage.plus(plan_usage)
   intent=self._validate_plan(plan,question)
   result=self._ask_deterministic(question,evaluation_timestamp,None,intent_override=intent,execution_mode="llm_assisted")
   evidence_ids=self._evidence_ids(result)
   synthesis,model,synthesis_usage=self.gateway.synthesize(question,result,evidence_ids); usage=usage.plus(synthesis_usage)
   self._validate_synthesis_claims(synthesis.summary,result)
   valid_citations=list(dict.fromkeys(item for item in synthesis.evidence_citations if item in set(evidence_ids)))
   invalid_citations=[item for item in synthesis.evidence_citations if item not in set(evidence_ids)]
   advisory=f"Advisory AI explanation: {synthesis.summary}"
   result.update({"investigation_summary":advisory,"model_generated_explanation":advisory,"llm_evidence_citations":valid_citations,"llm_provider":capability.get("provider"),"llm_status":"completed","model_identifier":model,"token_usage":usage.model_dump(),"llm_error":None})
   if invalid_citations: result["evidence_limitations"].append("Some model-supplied citations were omitted because they did not match deterministic evidence references.")
   if synthesis.limitation and synthesis.limitation not in result["evidence_limitations"]: result["evidence_limitations"].append(synthesis.limitation)
   return result
  except LlmGatewayError as exc:
   fallback=result or self._ask_deterministic(question,evaluation_timestamp,None,execution_mode="deterministic_fallback")
   fallback["execution_mode"]="deterministic_fallback"; fallback["model_generated_explanation"]=None; fallback["llm_evidence_citations"]=[]
   fallback.update({"llm_provider":capability.get("provider"),"llm_status":exc.status,"model_identifier":model or capability.get("model_identifier"),"token_usage":usage.model_dump(),"llm_error":str(exc)})
   fallback["evidence_limitations"].append("LLM Assisted mode did not complete; this response was produced by deterministic ARCA tools.")
   return fallback
