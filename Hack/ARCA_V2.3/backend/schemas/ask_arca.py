from __future__ import annotations
from typing import Any,Literal
from pydantic import AwareDatetime,BaseModel,ConfigDict,Field
from backend.schemas.common import AiExecutionMetrics

class AskConversationContext(BaseModel):
    model_config=ConfigDict(extra="forbid")
    provider:Literal["azure","aws","snowflake","all"]|None=None
    selected_resource:str|None=Field(default=None,max_length=1024)
    selected_identity:str|None=Field(default=None,max_length=320)
    subscription:str|None=Field(default=None,max_length=200)
    resource_group:str|None=Field(default=None,max_length=300)
    investigation_window:dict[str,Any]|None=None
    previous_findings:list[dict[str,Any]]=Field(default_factory=list,max_length=500)
    last_intent:str|None=Field(default=None,max_length=100)
    pending_clarification:Literal["resource","identity"]|None=None
    pending_intent:str|None=Field(default=None,max_length=100)
    candidate_resources:list[str]=Field(default_factory=list,max_length=50)

class AskArcaRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    question:str=Field(min_length=2,max_length=2000)
    mode:Literal["mock","ai","deterministic","llm_assisted"]="mock"
    evaluation_timestamp:AwareDatetime|None=None
    scenario_id:str|None=Field(default=None,max_length=100,pattern=r"^[A-Za-z0-9_-]+$")
    conversation_context:AskConversationContext|None=None
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
    llm_provider:str|None=None; llm_status:str; model_identifier:str|None=None; token_usage:dict[str,Any]|None=None
    execution_metrics:AiExecutionMetrics
    model_generated_explanation:str|None=None; llm_evidence_citations:list[str]=Field(default_factory=list); llm_error:str|None=None
    conversation_context:AskConversationContext=Field(default_factory=AskConversationContext)
