from __future__ import annotations
import json,re,time
from datetime import datetime,timedelta,timezone
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
from backend.services.llm_metrics import execution_metrics
from backend.services.ask_arca_tools import AzureInvestigationTools

TOOLS=[
 {"name":"get_change_details","description":"Retrieve a provider change record."},{"name":"validate_change_and_access","description":"Run provider-native deterministic validation."},
 {"name":"verify_change_execution","description":"Correlate a change with provider audit evidence."},{"name":"investigate_user_activity","description":"Investigate a resolved user or principal."},
 {"name":"find_potentially_unapproved_activity","description":"Run Agent 4 discovery without a known change."},{"name":"investigate_role_or_privilege_changes","description":"Filter Agent 4 evidence by role."},
 {"name":"retrieve_supporting_evidence","description":"Preserve evidence IDs returned by deterministic tools."},{"name":"run_cross_environment_risk_investigation","description":"Run Agent 4 across all providers."},
 {"name":"find_resources","description":"Locate Azure resources by exact name, identifier, group, type, or environment."},
 {"name":"get_resource_details","description":"Retrieve one resolved Azure resource."},
 {"name":"get_activity_logs","description":"Retrieve read-only Azure Activity Log evidence."},
 {"name":"get_role_assignments","description":"Retrieve Azure RBAC assignment evidence."},
 {"name":"get_pim_requests","description":"Retrieve Azure PIM request evidence."},
 {"name":"get_change_records","description":"Retrieve approved change records for an Azure resource or identity."},
 {"name":"correlate_approved_changes","description":"Correlate Azure activity with exact approved-change evidence."},
 {"name":"find_undocumented_changes","description":"Find successful Azure modifications without an exact approved-change match."},
]
PROVIDERS=("aws","azure","snowflake")
class AgentConfigurationError(RuntimeError): pass

class AskArcaService:
 def __init__(self,gateway:LlmGateway|None=None)->None:
  self.risk=RiskInvestigationService(); self.repos={"aws":AwsRepository(),"azure":AzureRepository(),"snowflake":SnowflakeRepository()}
  self.validation={"aws":AwsValidationService(),"azure":AzureValidationService(),"snowflake":SnowflakeValidationService()}
  self.execution={"aws":AwsExecutionService(),"azure":AzureExecutionService(),"snowflake":SnowflakeExecutionService()}
  self.azure_tools=AzureInvestigationTools(self.repos["azure"])
  self.tool_registry={item["name"]:item for item in TOOLS}
  self.gateway=gateway or LlmGateway()
 def scenarios(self)->list[dict[str,Any]]:
  sources=["ask_arca_scenarios.json","ask_arca_v1_scenarios.json"]
  return [item for filename in sources for item in json.loads(Path(PROJECT_ROOT,"data","investigations",filename).read_text(encoding="utf-8"))]
 def capabilities(self)->dict[str,Any]: return {"default_mode":"deterministic","modes":["deterministic","llm_assisted"],"providers":list(PROVIDERS)+["all"],"tools":TOOLS,"supported_periods":["today","yesterday","last 24 hours","last 2 days","last 7 days","last 10 days","last 15 days","last 30 days"],"llm":self.gateway.capability()}
 def parse(self,question:str,context:dict[str,Any]|None=None)->dict[str,Any]:
  q=question.strip(); low=q.casefold(); providers=[p for p in PROVIDERS if p in low]
  context=context or {}
  if not q:
   return {"investigation_type":"malformed","provider":None,"change_id":None,"user_identifier":None,"role":None,"resource":None,"time_period_days":7,"severity":"all","clarification":"Enter a non-empty investigation question.","parser":"deterministic_mock"}
  normalized=re.sub(r"[^a-z0-9 ]","",low).strip()
  if normalized in {"hi","hello","hey","good morning","good afternoon","good evening","thanks","thank you"}:
   return {"investigation_type":"greeting","provider":None,"change_id":None,"user_identifier":None,"role":None,"resource":None,"time_period_days":7,"severity":"all","clarification":None,"parser":"deterministic_mock"}
  if any(phrase in low for phrase in ("what can arca do","how can arca help","arca capabilities","help me use arca")):
   return {"investigation_type":"capabilities","provider":None,"change_id":None,"user_identifier":None,"role":None,"resource":None,"time_period_days":7,"severity":"all","clarification":None,"parser":"deterministic_mock"}
  if re.search(r"\b(who (performed|made) (those|the) changes|who changed it)\b",low):
   return {"investigation_type":"actors_followup","provider":context.get("provider") or "azure","change_id":None,"user_identifier":None,"role":None,"resource":context.get("selected_resource"),"time_period_days":7,"severity":"all","clarification":None,"parser":"deterministic_mock"}
  if re.search(r"\b(were (they|those) approved|was (it|that) approved|valid change)\b",low):
   return {"investigation_type":"approval_followup","provider":context.get("provider") or "azure","change_id":None,"user_identifier":None,"role":None,"resource":context.get("selected_resource"),"time_period_days":7,"severity":"all","clarification":None,"parser":"deterministic_mock"}
  if "weather" in low or "write a poem" in low or "capital of france" in low:
   return {"investigation_type":"unsupported","provider":None,"change_id":None,"user_identifier":None,"role":None,"resource":None,"time_period_days":7,"severity":"all","clarification":None,"parser":"deterministic_mock"}
  all_requested="all environment" in low or (len(providers)>1) or "across aws, azure, and snowflake" in low
  change_match=re.search(r"\b(CHG-SF-\d+|CHG-AZ-\d+|CHG\d+)\b",q,re.I); change_id=change_match.group(1).upper() if change_match else None
  if change_id:
   inferred="snowflake" if change_id.startswith("CHG-SF-") else "azure" if change_id.startswith("CHG-AZ-") else "aws"
   providers=[inferred]
  period=10
  match=re.search(r"last\s+(?:the\s+)?(1|2|7|10|15|30)\s+days?",low)
  if match: period=int(match.group(1))
  elif "last 24 hour" in low or "today" in low: period=1
  elif "last 48 hour" in low or "two days ago" in low: period=2
  elif "yesterday" in low: period=1
  email=re.search(r"[\w.+-]+@[\w.-]+",q); principal=re.search(r"\b(?:AIDA|AROA)-[\w:-]+\b|arn:aws:(?:iam|sts)::\d{12}:[^\s,?]+",q,re.I)
  identity=(email or principal).group(0) if email or principal else None
  if not identity:
   by=re.search(r"(?:performed\s+by|activities\s+by)\s+([A-Za-z0-9_.:-]+)",q,re.I); identity=by.group(1) if by else None
  role=None
  for candidate in ["ACCOUNTADMIN","SECURITYADMIN","OperationsRole","Contributor","Owner"]:
   if candidate.casefold() in low: role=candidate; break
  resource_match=re.search(r"arn:(?:aws|azure):[^\s,?]+|/subscriptions/[^\s,?]+",q,re.I); resource=resource_match.group(0).rstrip(".;:)") if resource_match else None
  if not resource:
   named_resource=re.search(r"\b(?:resource|on)\s+([A-Za-z0-9][A-Za-z0-9_.-]{2,})\b",q,re.I)
   if named_resource and named_resource.group(1).casefold() not in {"this","that","the","a","an"}: resource=named_resource.group(1)
  resource_name=next((str(item.get("name")) for item in self.repos["azure"].resources() if str(item.get("name") or "").casefold() in low),None)
  resource_hint=resource or resource_name or context.get("selected_resource")
  if context.get("pending_clarification")=="identity" and identity: intent="access_troubleshooting"; environment="azure"
  elif "undocumented" in low or "without approved" in low: intent="undocumented_changes"; environment="azure"
  elif ("pim" in low or "requested" in low) and any(x in low for x in ["access","contributor","role"]): intent="pim_requests"; environment="azure"
  elif re.search(r"could access|cannot access|can't access|access loss|lost access",low): intent="access_troubleshooting"; environment="azure"
  elif resource_hint or any(x in low for x in ["what changed","who modified","modified this","changes on"]): intent="resource_changes"; environment="azure"
  elif change_id: intent="change_execution" if any(x in low for x in ["implemented correctly","execution","executed correctly"]) else "change_investigation"
  elif role: intent="role_investigation"
  elif identity or " user " in f" {low} " or "principal" in low: intent="user_investigation"
  elif all_requested or "across" in low or "all environments" in low: intent="cross_environment_summary"
  elif any(x in low for x in ["unauthorized","unapproved","suspicious","privilege escalation"]): intent="unauthorized_activity"
  else: intent="historical_activity"
  if intent in {"access_troubleshooting","undocumented_changes","resource_changes","pim_requests"} and not match and not any(value in low for value in ("last 24 hour","today","yesterday","last 48 hour","two days ago")): period=7
  severity="high" if "high-risk" in low or "high severity" in low else "all"
  environment=locals().get("environment") or ("all" if all_requested else providers[0] if len(providers)==1 else None)
  clarification=None
  if intent.startswith("change") and not change_id: clarification="Which change ID should ARCA investigate?"
  elif intent=="user_investigation" and not identity: clarification="Which user, principal ID, ARN, or explicitly mapped email should ARCA investigate?"
  elif not environment: clarification="Which environment should ARCA investigate: AWS, Azure, Snowflake, or all environments?"
  return {"investigation_type":intent,"provider":environment,"change_id":change_id,"user_identifier":identity,"role":role,"resource":resource_hint,"time_period_days":period,"severity":severity,"clarification":clarification,"parser":"deterministic_mock"}
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

 @staticmethod
 def _azure_signal(event:dict[str,Any])->str|None:
  operation=str((event.get("operation_name") or {}).get("value") or "").casefold(); properties=event.get("properties") or {}
  if operation=="microsoft.authorization/roleassignments/delete": return "a role-assignment removal possibly related to storage access"
  if operation=="microsoft.storage/storageaccounts/write" and any(str(item).casefold()=="networkacls" for item in properties.get("changed_settings") or []): return "a storage firewall/network ACL modification possibly related to access"
  return None

 @staticmethod
 def _azure_refs(results:dict[str,Any])->list[dict[str,Any]]:
  refs=[]; seen=set()
  keys=("event_data_id","event_id","pim_request_id","assignment_id","change_id","resource_id")
  for value in results.values():
   for item in value.get("items",[]) if isinstance(value,dict) else []:
    evidence_id=next((item.get(key) for key in keys if item.get(key)),None)
    if not evidence_id or str(evidence_id) in seen: continue
    seen.add(str(evidence_id)); refs.append({"provider":"azure","evidence_id":str(evidence_id),"source":value.get("tool"),"timestamp":item.get("event_timestamp") or (item.get("schedule") or {}).get("start"),"actor":item.get("caller") or item.get("principal_name"),"operation":(item.get("operation_name") or {}).get("value") if isinstance(item.get("operation_name"),dict) else item.get("operation"),"resource_id":item.get("resource_id") or item.get("scope")})
  return refs

 def _resolve_azure_resource(self,question:str,context:dict[str,Any],intent:dict[str,Any],traces:list)->tuple[dict[str,Any]|None,list[dict[str,Any]],dict[str,Any]]:
  low=question.casefold(); explicit=str(intent.get("resource") or "")
  if explicit.startswith("/subscriptions/"):
   details=self._trace(traces,"03","get_resource_details",lambda:self.azure_tools.get_resource_details(explicit),"Retrieved the explicitly selected Azure resource.")
   return (details["items"][0] if details["count"]==1 else None,details["items"],{"resource":details})
  named=[item for item in self.repos["azure"].resources() if str(item.get("name") or "").casefold() in low]
  if len(named)==1: query=str(named[0]["name"])
  elif explicit: query=explicit
  elif context.get("selected_resource"):
   query=str(context["selected_resource"])
  else:
   query=""
   for token in ("storage account","storage","virtual machine","web","key vault","sql","network security"):
    if token in low: query=token.split()[0]; break
  search=self._trace(traces,"03","find_resources",lambda:self.azure_tools.find_resources(query=query,resource_type=query if query in {"storage","virtual","web","key","sql","network"} and not named else None),"Resolved resource candidates from synthetic Azure inventory.")
  matches=named if named else search["items"]
  return (matches[0] if len(matches)==1 else None,matches,{"resource_search":search})

 def _ask_azure_v1(self,question:str,intent:dict[str,Any],evaluated:datetime,traces:list,base:dict[str,Any],context:dict[str,Any])->dict[str,Any]:
  kind=intent["investigation_type"]; context={**context,"provider":"azure"}; results={}; findings=[]; timeline=[]; limitations=[]; actions=[]
  end=evaluated.astimezone(timezone.utc); start=end-timedelta(days=int(intent.get("time_period_days") or 7)); start_text=utc_text(start); end_text=utc_text(end)
  if kind in {"greeting","capabilities","unsupported","malformed"}:
   if kind=="greeting": summary="Hello! I'm ARCA, your Cloud Risk & Change Assurance Assistant. I can investigate infrastructure changes, privileged access, undocumented modifications, and cloud access issues. What would you like to investigate?"; limitation="No evidence tools were needed for this greeting."
   elif kind=="capabilities": summary="ARCA can locate Azure resources, investigate users and access changes, retrieve recent configuration activity, correlate operations with approved changes, and preserve technical evidence using read-only tools."; limitation="No evidence tools were needed for this capability explanation."
   elif kind=="malformed": summary="Enter a non-empty investigation question under 2,000 characters."; limitation="No evidence tools were executed because the question was malformed."
   else: summary="ARCA focuses on cloud security, privileged access, and change governance. Ask about infrastructure changes, access issues, PIM activity, or approved-change evidence."; limitation="No evidence tools were executed for an unsupported question."
   return {**base,"providers_investigated":[],"overall_status":"INSUFFICIENT_EVIDENCE","investigation_summary":summary,"findings":[],"evidence_references":[],"activity_timeline":[],"confidence":"none","evidence_limitations":[limitation],"recommended_actions":[],"clarification_request":None,"conversation_context":context,"tool_execution_trace":traces}
  if kind in {"actors_followup","approval_followup"}:
   previous=context.get("previous_findings") or []
   if not previous:
    return {**base,"overall_status":"INSUFFICIENT_EVIDENCE","investigation_summary":"I do not have prior modification evidence in this investigation. Select a resource and investigation window first.","findings":[],"evidence_references":[],"activity_timeline":[],"confidence":"none","evidence_limitations":["No prior activity is available in the active conversation context."],"recommended_actions":[],"clarification_request":None,"conversation_context":context,"tool_execution_trace":traces}
   if kind=="actors_followup":
    actors=sorted({str(item.get("caller")) for item in previous if item.get("caller")}); results["previous_activity"]={"tool":"conversation_context","count":len(previous),"items":previous,"query":{}}
    summary="Actors recorded on the previous evidence: "+(", ".join(actors) if actors else "none available in the evidence.")
   else:
    correlation=self._trace(traces,"03","correlate_approved_changes",lambda:self.azure_tools.correlate_approved_changes(previous),"Correlated prior activity with exact approved-change evidence."); results["approval_correlation"]=correlation
    approved=sum(1 for item in correlation["items"] if item["classification"]=="MATCHED_APPROVED_CHANGE"); summary=f"{approved} prior event(s) have an exact matching approved synthetic change; {correlation['count']-approved} do not. Unmatched does not mean unauthorized."
   refs=self._azure_refs(results); context.update({"last_intent":kind,"pending_clarification":None})
   return {**base,"overall_status":"POTENTIAL_RISK" if findings else "COMPLIANT","investigation_summary":summary,"findings":findings,"evidence_references":refs,"activity_timeline":previous,"confidence":"limited","evidence_limitations":["Activity correlation does not prove final resource state or malicious intent."],"recommended_actions":[],"clarification_request":None,"conversation_context":context,"tool_execution_trace":traces}
  if kind=="undocumented_changes":
   undocumented=self._trace(traces,"03","find_undocumented_changes",lambda:self.azure_tools.find_undocumented_changes(start=start_text,end=end_text,environment="production"),"Correlated successful Azure modifications with exact approved-change evidence."); results["undocumented_changes"]=undocumented; timeline=undocumented["items"]
   findings=[{"finding_id":f"ASK-AZ-{item['event_id']}","category":"UNMATCHED_IN_AVAILABLE_RECORDS","severity":"MEDIUM","confidence":"possible","summary":"Successful modification has no exact matching approved change in the available evidence.","evidence_ids":[item["event_id"]]} for item in timeline]
   summary=f"Found {undocumented['count']} successful modification event(s) without an exact matching approved change in the available synthetic evidence. These are unmatched records, not confirmed unauthorized changes."
  elif kind=="pim_requests":
   role="Contributor" if "contributor" in question.casefold() else intent.get("role"); scope="/subscriptions/" if "subscription" in question.casefold() else None
   requests=self._trace(traces,"03","get_pim_requests",lambda:self.azure_tools.get_pim_requests(role=role,scope=scope,start=start_text,end=end_text),"Retrieved Azure PIM request evidence using validated role, scope, and time filters."); results["pim_requests"]=requests
   findings=[{"finding_id":f"ASK-AZ-{item['pim_request_id']}","category":"PIM_REQUEST_EVIDENCE","severity":"INFO","confidence":"confirmed","summary":f"{item.get('principal_name')} requested {item.get('role_name')} at {item.get('scope')}.","evidence_ids":[item["pim_request_id"]]} for item in requests["items"]]
   summary=f"Found {requests['count']} matching synthetic PIM request(s). Request or approval records do not independently prove active access."
  else:
   resource,matches,resource_results=self._resolve_azure_resource(question,context,intent,traces); results.update(resource_results)
   if not resource:
    if matches: choices=", ".join(f"{item['name']} ({item['resource_group']})" for item in matches[:8]); clarification=f"I found multiple matching synthetic resources: {choices}. Which resource should I investigate? Provide the exact name, resource group, or full resource ID."
    else: clarification="I could not uniquely identify a resource in the synthetic Azure dataset. Provide its exact resource name, resource group, or full resource ID."
    context.update({"pending_clarification":"resource","pending_intent":kind,"candidate_resources":[item.get("resource_id") for item in matches]})
    return {**base,"overall_status":"INSUFFICIENT_EVIDENCE","investigation_summary":"More information is required before resource evidence can be correlated.","findings":[],"evidence_references":self._azure_refs(results),"activity_timeline":[],"confidence":"none","evidence_limitations":["No activity conclusion was produced because the resource is ambiguous or unavailable."],"recommended_actions":[],"clarification_request":clarification,"conversation_context":context,"tool_execution_trace":traces}
   resource_id=resource["resource_id"]; context.update({"selected_resource":resource_id,"subscription":resource.get("subscription_id"),"resource_group":resource.get("resource_group")})
   if kind=="access_troubleshooting" and not intent.get("user_identifier"):
    context.update({"pending_clarification":"identity","pending_intent":kind})
    context["investigation_window"]={"start":start_text,"end":end_text}
    return {**base,"overall_status":"INSUFFICIENT_EVIDENCE","investigation_summary":f"I identified {resource['name']} in {resource['resource_group']}, but the affected identity is required.","findings":[],"evidence_references":self._azure_refs(results),"activity_timeline":[],"confidence":"none","evidence_limitations":["No access root cause can be assessed without an affected identity."],"recommended_actions":[],"clarification_request":"Which user or service-principal name/object ID is experiencing the access failure?","conversation_context":context,"tool_execution_trace":traces}
   activity=self._trace(traces,"04","get_activity_logs",lambda:self.azure_tools.get_activity_logs(resource_id=resource_id,start=start_text,end=end_text,modifications_only=True),"Retrieved recent successful Azure resource modifications."); changes=self._trace(traces,"05","get_change_records",lambda:self.azure_tools.get_change_records(resource_id=resource_id,start=start_text,end=end_text),"Retrieved overlapping approved change records.")
   results.update({"activity_logs":activity,"change_records":changes}); timeline=activity["items"]
   correlation=self._trace(traces,"06","correlate_approved_changes",lambda:self.azure_tools.correlate_approved_changes(timeline),"Compared activity actor, operation, resource, and timestamp with approved changes."); results["approval_correlation"]=correlation
   if kind=="access_troubleshooting":
    identity=intent["user_identifier"]; assignments=self._trace(traces,"07","get_role_assignments",lambda:self.azure_tools.get_role_assignments(resource_id=resource_id,identity=identity,active_at=end_text),"Retrieved scoped RBAC evidence for the affected identity."); pim=self._trace(traces,"08","get_pim_requests",lambda:self.azure_tools.get_pim_requests(resource_id=resource_id,identity=identity,start=start_text,end=end_text),"Retrieved relevant PIM request evidence."); results.update({"role_assignments":assignments,"pim_requests":pim}); signals=sorted({signal for event in timeline if (signal:=self._azure_signal(event))})
    cause=" Relevant evidence includes "+"; ".join(signals)+"." if signals else " The available evidence does not establish a root cause for this identity's access failure."
    summary=f"Reviewed {activity['count']} modification event(s), {assignments['count']} role assignment(s), {pim['count']} PIM request(s), and {changes['count']} approved change record(s) for {resource['name']}.{cause} Potential causes are not confirmed root causes without resource-state and sign-in evidence."
    context["selected_identity"]=identity
   else:
    actors=sorted({str(item.get("caller")) for item in timeline if item.get("caller")}); summary=f"Found {activity['count']} successful modification event(s) for {resource['name']} in the selected window. Actors in the evidence: {', '.join(actors) if actors else 'none'}."
   findings=[{"finding_id":f"ASK-AZ-{item['event_id']}","category":item["classification"],"severity":"MEDIUM" if item["classification"]!="MATCHED_APPROVED_CHANGE" else "INFO","confidence":"possible" if item["classification"]!="MATCHED_APPROVED_CHANGE" else "confirmed","summary":"Activity correlation result for the selected resource.","evidence_ids":[item["event_id"]],"change_ids":item["change_ids"]} for item in correlation["items"]]
  refs=self._trace(traces,"09","retrieve_supporting_evidence",lambda:self._azure_refs(results),"Preserved original Azure evidence identifiers and timestamps.")
  context.update({"investigation_window":{"start":start_text,"end":end_text},"previous_findings":timeline,"last_intent":kind,"pending_clarification":None,"pending_intent":None})
  limitations=["Synthetic Activity Logs show control-plane requests, not verified final resource state.","Missing or unmatched change evidence does not prove unauthorized activity."]
  actions=["Review the cited Activity Log, RBAC, PIM, and change records before confirming root cause or authorization."]
  return {**base,"overall_status":"POTENTIAL_RISK" if any(item.get("confidence")=="possible" for item in findings) else "COMPLIANT" if timeline or findings else "INSUFFICIENT_EVIDENCE","investigation_summary":summary,"findings":findings,"evidence_references":refs,"activity_timeline":timeline,"confidence":"limited" if findings else "none","evidence_limitations":limitations,"recommended_actions":actions,"clarification_request":None,"conversation_context":context,"tool_execution_trace":traces}

 def _ask_deterministic(self,question:str,evaluation_timestamp:datetime|str|None=None,scenario_id:str|None=None,intent_override:dict[str,Any]|None=None,execution_mode:str="mock",conversation_context:dict[str,Any]|None=None)->dict[str,Any]:
  scenario=next((x for x in self.scenarios() if x["scenario_id"]==scenario_id),None) if scenario_id else None
  if scenario_id and not scenario: raise ValueError("Unknown Ask ARCA scenario")
  if scenario: question=scenario["question"]; evaluation_timestamp=scenario["evaluation_timestamp"]
  evaluated=parse_utc(evaluation_timestamp) if isinstance(evaluation_timestamp,str) else (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
  context=dict(conversation_context or {})
  traces=[]; intent=self._trace(traces,"01","understand_request",lambda:intent_override or self.parse(question,context),"Used the validated LLM intent plan." if intent_override else "Parsed the question deterministically; no LLM was invoked.")
  providers=self._trace(traces,"02","resolve_environment",lambda:list(PROVIDERS) if intent["provider"]=="all" else [intent["provider"]] if intent["provider"] else [],"Resolved explicit provider routing.")
  base={"investigation_id":f"ASK-{uuid4().hex[:12].upper()}","original_question":question,"resolved_intent":intent,"providers_investigated":providers,"execution_mode":execution_mode,"tool_execution_trace":traces,"llm_provider":None,"llm_status":"not_invoked","model_identifier":None,"token_usage":None,"model_generated_explanation":None,"llm_evidence_citations":[],"llm_error":None,"conversation_context":context}
  if intent["investigation_type"] in {"access_troubleshooting","undocumented_changes","resource_changes","pim_requests","actors_followup","approval_followup","greeting","capabilities","unsupported","malformed"}:
   return self._ask_azure_v1(question,intent,evaluated,traces,base,context)
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
  if len(summary.split())>100:
   raise LlmGatewayError("invalid_response","The LLM explanation exceeded the concise answer limit.")
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

 def ask(self,question:str,mode:str="mock",evaluation_timestamp:datetime|str|None=None,scenario_id:str|None=None,conversation_context:dict[str,Any]|None=None)->dict[str,Any]:
  started=time.perf_counter()
  normalized={"mock":"mock","deterministic":"deterministic","ai":"llm_assisted","llm_assisted":"llm_assisted"}[mode]
  if normalized!="llm_assisted":
   result=self._ask_deterministic(question,evaluation_timestamp,scenario_id,execution_mode=normalized,conversation_context=conversation_context)
   result["execution_metrics"]=execution_metrics(agent_id="A5",execution_mode=normalized,provider=None,model=None,status="not_invoked",usage=TokenUsage(),started_at=started,environment=result.get("conversation_context",{}).get("provider"))
   return result
  scenario=next((x for x in self.scenarios() if x["scenario_id"]==scenario_id),None) if scenario_id else None
  if scenario_id and not scenario: raise ValueError("Unknown Ask ARCA scenario")
  if scenario: question=scenario["question"]; evaluation_timestamp=scenario["evaluation_timestamp"]
  capability=self.gateway.capability()
  if not capability["available"]:
   raise AgentConfigurationError("LLM Assisted mode is unavailable because the approved provider is disabled or incompletely configured. Retry in Deterministic mode.")
  usage=TokenUsage(); model=str(capability.get("model_identifier") or ""); result=None
  try:
   preparsed=self.parse(question,conversation_context)
   v1_intents={"access_troubleshooting","undocumented_changes","resource_changes","pim_requests","actors_followup","approval_followup","greeting","capabilities","unsupported","malformed"}
   if preparsed["investigation_type"] in v1_intents:
    intent=preparsed
   else:
    plan,model,plan_usage=self.gateway.plan(question,TOOLS); usage=usage.plus(plan_usage)
    intent=self._validate_plan(plan,question)
   result=self._ask_deterministic(question,evaluation_timestamp,None,intent_override=intent,execution_mode="llm_assisted",conversation_context=conversation_context)
   evidence_ids=self._evidence_ids(result)
   synthesis,model,synthesis_usage=self.gateway.synthesize(question,result,evidence_ids); usage=usage.plus(synthesis_usage)
   self._validate_synthesis_claims(synthesis.summary,result)
   valid_citations=list(dict.fromkeys(item for item in synthesis.evidence_citations if item in set(evidence_ids)))
   invalid_citations=[item for item in synthesis.evidence_citations if item not in set(evidence_ids)]
   advisory=f"Advisory AI explanation: {synthesis.summary}"
   result.update({"investigation_summary":advisory,"model_generated_explanation":advisory,"llm_evidence_citations":valid_citations,"llm_provider":capability.get("provider"),"llm_status":"completed","model_identifier":model,"token_usage":usage.model_dump(),"llm_error":None})
   result["execution_metrics"]=execution_metrics(agent_id="A5",execution_mode="llm_assisted",provider=capability.get("provider"),model=model,status="completed",usage=usage,started_at=started,environment=result.get("conversation_context",{}).get("provider"))
   if invalid_citations: result["evidence_limitations"].append("Some model-supplied citations were omitted because they did not match deterministic evidence references.")
   if synthesis.limitation and synthesis.limitation not in result["evidence_limitations"]: result["evidence_limitations"].append(synthesis.limitation)
   return result
  except LlmGatewayError as exc:
   usage=usage.plus(exc.usage)
   fallback=result or self._ask_deterministic(question,evaluation_timestamp,None,execution_mode="deterministic_fallback",conversation_context=conversation_context)
   fallback["execution_mode"]="deterministic_fallback"; fallback["model_generated_explanation"]=None; fallback["llm_evidence_citations"]=[]
   fallback.update({"llm_provider":capability.get("provider"),"llm_status":exc.status,"model_identifier":model or capability.get("model_identifier"),"token_usage":usage.model_dump(),"llm_error":str(exc)})
   fallback["execution_metrics"]=execution_metrics(agent_id="A5",execution_mode="deterministic_fallback",provider=capability.get("provider"),model=model or capability.get("model_identifier"),status=exc.status,usage=usage,started_at=started,environment=fallback.get("conversation_context",{}).get("provider"))
   fallback["evidence_limitations"].append("LLM Assisted mode did not complete; this response was produced by deterministic ARCA tools.")
   return fallback
