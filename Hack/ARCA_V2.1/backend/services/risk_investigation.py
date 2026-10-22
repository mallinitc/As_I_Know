from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.config import PROJECT_ROOT
from backend.repositories.aws import AwsRepository
from backend.repositories.azure import AzureRepository
from backend.repositories.snowflake import SnowflakeRepository
from backend.services.aws_execution import AwsExecutionService, _actor as aws_actor, _aliases as aws_aliases, _explicit_change as aws_change, _resources as aws_resources
from backend.services.azure_execution import AzureExecutionService, _event_score as azure_score, _operation as azure_operation
from backend.services.snowflake_execution import SnowflakeExecutionService, READ_ONLY_TYPES, _change_from_tag
from backend.services.timestamps import parse_utc, utc_text

SEVERITY_RANK={"critical":4,"high":3,"medium":2,"low":1,"info":0}
CATEGORY_MAP={"FAILED_EXECUTION":"FAILED_ADMINISTRATIVE_OPERATION","ROLE_MISMATCH":"ROLE_OR_SCOPE_MISMATCH","ROLE_OR_SCOPE_MISMATCH":"ROLE_OR_SCOPE_MISMATCH","WRONG_TARGET_OBJECT":"WRONG_TARGET_RESOURCE"}

class RiskInvestigationService:
    def __init__(self)->None:
        self.aws_repo=AwsRepository(); self.azure_repo=AzureRepository(); self.sf_repo=SnowflakeRepository()
        self.aws=AwsExecutionService(self.aws_repo); self.azure=AzureExecutionService(self.azure_repo); self.sf=SnowflakeExecutionService(self.sf_repo)
    def scenarios(self)->list[dict[str,Any]]:
        source=Path(PROJECT_ROOT,"data","investigations","risk_scenarios.json"); value=json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(value,list): raise ValueError("Risk scenario catalog must be an array")
        return value
    def _native(self,provider:str,item:dict[str,Any],finding:dict[str,Any],timeline:dict[str,Any])->dict[str,Any]:
        category=CATEGORY_MAP.get(str(finding.get("category")),str(finding.get("category")))
        ids=finding.get("event_ids") or finding.get("query_ids") or []
        return {"finding_id":f"RISK-{provider.upper()}-{len(ids) and ids[0] or uuid4().hex[:8]}-{category}","provider":provider,"category":category,"severity":str(finding.get("severity") or "MEDIUM").upper(),"confidence":finding.get("confidence") or "possible","summary":finding.get("message") or "Provider-native risk finding.","actor":timeline.get("actor"),"role":timeline.get("role"),"resource":timeline.get("resource"),"timestamp":timeline.get("timestamp"),"change_id":finding.get("change_id"),"evidence_ids":[str(x) for x in ids],"recommendation":finding.get("recommendation") or "Review the supporting audit evidence."}
    def _unmatched(self,provider:str,evidence_id:str,timestamp:str,actor:str,role:str|None,resource:str|None,operation:str)->list[dict[str,Any]]:
        category="UNEXPECTED_PRIVILEGE_GRANT" if "grant" in operation.casefold() or "roleassignments/write" in operation.casefold() or "policy" in operation.casefold() else "POSSIBLE_UNAPPROVED_ACTIVITY"
        base={"provider":provider,"severity":"HIGH" if category=="UNEXPECTED_PRIVILEGE_GRANT" else "MEDIUM","confidence":"possible","actor":actor,"role":role,"resource":resource,"timestamp":timestamp,"change_id":None,"evidence_ids":[evidence_id],"recommendation":"Investigate the administrative activity and link it to an approved change only when supported by evidence."}
        return [{**base,"finding_id":f"RISK-{provider.upper()}-{evidence_id}-{category}","category":category,"summary":"Governed administrative activity has no sufficiently supported approved-change match."},{**base,"finding_id":f"RISK-{provider.upper()}-{evidence_id}-MISSING","category":"MISSING_APPROVED_CHANGE","summary":"No approved change record could be correlated with this activity."}]
    def _filter(self,text:Any,needle:str|None)->bool: return not needle or needle.casefold() in str(text or "").casefold()
    def _aws(self,start:datetime,end:datetime,identity:str|None,role:str|None,resource:str|None)->tuple[list,list,list]:
        findings=[]; timeline=[]; evidence=[]; changes=self.aws_repo.changes(); seen=set()
        for event in self.aws_repo.execution_events():
            eid=str(event.get("eventID"));
            if eid in seen: continue
            seen.add(eid)
            try: occurred=parse_utc(event["eventTime"])
            except (KeyError,TypeError,ValueError): continue
            if not start<=occurred<=end or event.get("readOnly") is True: continue
            aliases=aws_aliases(event); resources=aws_resources(event); identity_obj=event.get("userIdentity") or {}; session=identity_obj.get("sessionContext") or {}; issuer=session.get("sessionIssuer") or {}; role_text=" ".join(str(x or "") for x in [identity_obj.get("arn"),issuer.get("arn"),issuer.get("userName")])
            if identity and identity.casefold() not in aliases and not any(identity.casefold() in x for x in aliases): continue
            if not self._filter(role_text,role) or not self._filter(resources,resource): continue
            explicit=aws_change(event); change=next((x for x in changes if x.get("change_id")==explicit),None)
            if not change:
                change=next((x for x in changes if self.aws._classification(event,x) in {"MATCHED","POSSIBLE_MATCH"}),None)
            classification=self.aws._classification(event,change) if change else "UNMATCHED"; actor=aws_actor(event); target=resources[0] if resources else None
            row={"provider":"aws","evidence_id":eid,"timestamp":utc_text(occurred),"actor":actor,"role":role_text or None,"operation":event.get("eventName"),"resource":target,"status":"FAILED" if event.get("errorCode") else "SUCCESS","change_id":change.get("change_id") if change else None,"correlation":classification}
            timeline.append(row); evidence.append({"provider":"aws","evidence_id":eid,"source":"CloudTrail"})
            if change:
                native,_=self.aws._assess(event,change)
                findings.extend(self._native("aws",event,x,row) for x in native if x.get("category")!="COMPLIANT_EXECUTION")
            else: findings.extend(self._unmatched("aws",eid,row["timestamp"],actor,row["role"],target,str(event.get("eventName") or "")))
        return findings,timeline,evidence
    def _azure(self,start:datetime,end:datetime,identity:str|None,role:str|None,resource:str|None)->tuple[list,list,list]:
        findings=[]; timeline=[]; evidence=[]; changes=self.azure_repo.changes(); cache={}; seen=set()
        for event in self.azure_repo.activity_logs():
            eid=str(event.get("event_data_id"));
            if eid in seen: continue
            seen.add(eid)
            try: occurred=parse_utc(event["event_timestamp"])
            except (KeyError,TypeError,ValueError): continue
            if not start<=occurred<=end or not self._filter(f"{event.get('caller')} {event.get('caller_principal_id')}",identity) or not self._filter(event.get("authorization"),role) or not self._filter(event.get("resource_id"),resource): continue
            scored=sorted(((azure_score(event,c)[0],c) for c in changes),key=lambda x:x[0],reverse=True); score,change=scored[0]
            scenario_name=(event.get("properties") or {}).get("synthetic_scenario")
            scenario_change=next((c for c in changes if scenario_name and c.get("scenario")==scenario_name),None)
            if scenario_change: change=scenario_change; score=5
            classification=azure_score(event,change)[1] if score>=5 else "UNMATCHED"; change=change if score>=5 else None
            status=(event.get("status") or {}).get("value"); row={"provider":"azure","evidence_id":eid,"timestamp":utc_text(occurred),"actor":event.get("caller"),"role":str(event.get("authorization") or ""),"operation":azure_operation(event),"resource":event.get("resource_id"),"status":status,"change_id":change.get("change_id") if change else None,"correlation":classification}
            timeline.append(row); evidence.append({"provider":"azure","evidence_id":eid,"source":"Activity Log"})
            if change:
                cid=change["change_id"]; cache.setdefault(cid,self.azure.access_service.validate_access(cid)); native,_=self.azure._assess_event(event,change,cache[cid]); findings.extend(self._native("azure",event,x,row) for x in native if x.get("category")!="COMPLIANT_EXECUTION")
            else: findings.extend(self._unmatched("azure",eid,row["timestamp"],str(row["actor"]),row["role"],row["resource"],str(row["operation"])))
        return findings,timeline,evidence
    def _snowflake(self,start:datetime,end:datetime,identity:str|None,role:str|None,resource:str|None)->tuple[list,list,list]:
        findings=[]; timeline=[]; evidence=[]; changes=self.sf_repo.changes(); access={x.get("query_id"):x for x in self.sf_repo.access_history()}; seen=set()
        for query in self.sf_repo.query_history():
            qid=str(query.get("query_id"));
            if qid in seen: continue
            seen.add(qid)
            try: occurred=parse_utc(query["start_time"])
            except (KeyError,TypeError,ValueError): continue
            if not start<=occurred<=end or _norm(query.get("query_type")) in {_norm(x) for x in READ_ONLY_TYPES} or not self._filter(query.get("user_name"),identity) or not self._filter(query.get("role_name"),role) or not self._filter(query.get("target_object"),resource): continue
            cid=_change_from_tag(query); change=next((x for x in changes if x.get("change_id")==cid),None)
            row={"provider":"snowflake","evidence_id":qid,"timestamp":utc_text(occurred),"actor":query.get("user_name"),"role":query.get("role_name"),"operation":query.get("query_type"),"resource":query.get("target_object"),"status":query.get("execution_status"),"change_id":cid if change else None,"correlation":"MATCHED" if change else "UNMATCHED"}
            timeline.append(row); evidence.append({"provider":"snowflake","evidence_id":qid,"source":"Query History","access_history_available":qid in access})
            if change:
                native,_=self.sf._assess_query(query,change,access); findings.extend(self._native("snowflake",query,x,row) for x in native if x.get("category")!="COMPLIANT_EXECUTION")
            else: findings.extend(self._unmatched("snowflake",qid,row["timestamp"],str(row["actor"]),row["role"],row["resource"],str(row["operation"])))
        return findings,timeline,evidence
    def investigate(self,environment:str="all",identity:str|None=None,role:str|None=None,resource:str|None=None,window_days:int=10,severity:str="all",evaluation_timestamp:datetime|str|None=None,scenario_id:str|None=None)->dict[str,Any]:
        if scenario_id:
            scenario=next((x for x in self.scenarios() if x["scenario_id"]==scenario_id),None)
            if not scenario: raise ValueError("Unknown risk scenario")
            environment=scenario["environment"]; identity=scenario.get("identity"); role=scenario.get("role"); resource=scenario.get("resource"); window_days=scenario["window_days"]; severity=scenario["severity"]; evaluation_timestamp=scenario["evaluation_timestamp"]
        end=parse_utc(evaluation_timestamp) if isinstance(evaluation_timestamp,str) else (evaluation_timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc); start=end-timedelta(days=window_days); providers=["aws","azure","snowflake"] if environment=="all" else [environment]
        findings=[]; timeline=[]; evidence=[]
        for provider in providers:
            f,t,e=getattr(self,f"_{provider}")(start,end,identity,role,resource); findings+=f; timeline+=t; evidence+=e
        if severity!="all": findings=[x for x in findings if x["severity"].casefold()==severity]
        findings=list({x["finding_id"]:x for x in findings}.values()); timeline=list({(x["provider"],x["evidence_id"]):x for x in timeline}.values()); timeline.sort(key=lambda x:x["timestamp"])
        counts={key:sum(1 for x in findings if x["severity"].casefold()==key) for key in ["critical","high","medium","low"]}; uncertain=any(x["confidence"] in {"possible","insufficient"} for x in findings)
        return {"investigation_id":f"RISK-{uuid4().hex[:12].upper()}","providers_investigated":providers,"period_start":utc_text(start),"period_end":utc_text(end),"summary":f"Reviewed {len(timeline)} governed activities across {len(providers)} environment(s) and identified {len(findings)} risk finding(s).","risk_counts":counts,"findings":findings,"evidence_references":evidence,"activity_timeline":timeline,"confidence":"limited" if uncertain else "high" if timeline else "none","evidence_limitations":["Audit events show API or query activity, not verified final resource state.","Unmatched evidence is classified as possible risk, not confirmed malicious activity.","Missing audit evidence is not proof that an operation did not occur."]}

def _norm(value:Any)->str:return str(value or "").strip().casefold()
