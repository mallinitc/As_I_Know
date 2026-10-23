from __future__ import annotations
from typing import Any, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from backend.schemas.common import AiAnalysis, ExecutionMode

class RiskInvestigationRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    environment: Literal["aws","azure","snowflake","all"]="all"
    identity: str|None=Field(default=None,max_length=254)
    role: str|None=Field(default=None,max_length=254)
    resource: str|None=Field(default=None,max_length=1024)
    window_days: Literal[1,2,7,10,15,30]=7
    severity: Literal["all","critical","high","medium","low"]="all"
    evaluation_timestamp: AwareDatetime|None=None
    scenario_id: str|None=Field(default=None,max_length=100,pattern=r"^[A-Za-z0-9_-]+$")
    execution_mode: ExecutionMode="deterministic"

class RiskScenario(BaseModel):
    scenario_id:str; scenario_name:str; environment:str; evaluation_timestamp:AwareDatetime; window_days:int
    identity:str|None=None; role:str|None=None; resource:str|None=None; severity:str
    expected_providers:list[str]; expected_findings:list[str]
    feature:str|None=None; time_range:str|None=None; expected_count:int|None=None
class RiskScenariosResponse(BaseModel):
    synthetic:Literal[True]=True; count:int; items:list[RiskScenario]
class RiskFinding(BaseModel):
    finding_id:str; provider:str; category:str; severity:str; confidence:str; summary:str
    actor:str|None=None; role:str|None=None; resource:str|None=None; timestamp:AwareDatetime|None=None
    change_id:str|None=None; evidence_ids:list[str]; recommendation:str
class RiskInvestigationResponse(BaseModel):
    investigation_id:str; providers_investigated:list[str]; period_start:AwareDatetime; period_end:AwareDatetime
    summary:str; risk_counts:dict[str,int]; findings:list[RiskFinding]; evidence_references:list[dict[str,Any]]
    activity_timeline:list[dict[str,Any]]; confidence:str; evidence_limitations:list[str]
    ai_analysis:AiAnalysis|None=None
