from __future__ import annotations
from typing import Any,Literal
from pydantic import AwareDatetime,BaseModel,ConfigDict,Field

class AskArcaRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    question:str=Field(min_length=2,max_length=2000)
    mode:Literal["mock","ai","deterministic","llm_assisted"]="mock"
    evaluation_timestamp:AwareDatetime|None=None
    scenario_id:str|None=Field(default=None,max_length=100,pattern=r"^[A-Za-z0-9_-]+$")
class AskScenario(BaseModel):
    scenario_id:str; scenario_name:str; question:str; evaluation_timestamp:AwareDatetime; expected_intent:str; expected_providers:list[str]
class AskScenariosResponse(BaseModel): synthetic:Literal[True]=True; count:int; items:list[AskScenario]
class AskCapabilitiesResponse(BaseModel):
    default_mode:str; modes:list[str]; providers:list[str]; tools:list[dict[str,Any]]; supported_periods:list[str]
    llm:dict[str,Any]
class ToolTrace(BaseModel): step_id:str; tool_name:str; status:str; start_time:AwareDatetime; end_time:AwareDatetime; duration:float; summary:str
class AskArcaResponse(BaseModel):
    investigation_id:str; original_question:str; resolved_intent:dict[str,Any]; providers_investigated:list[str]; execution_mode:str; overall_status:str
    investigation_summary:str; findings:list[dict[str,Any]]; evidence_references:list[dict[str,Any]]; activity_timeline:list[dict[str,Any]]
    tool_execution_trace:list[ToolTrace]; confidence:str; evidence_limitations:list[str]; recommended_actions:list[str]; clarification_request:str|None=None
    llm_provider:str|None=None; llm_status:str; model_identifier:str|None=None; token_usage:dict[str,int]|None=None
    model_generated_explanation:str|None=None; llm_evidence_citations:list[str]=Field(default_factory=list); llm_error:str|None=None
