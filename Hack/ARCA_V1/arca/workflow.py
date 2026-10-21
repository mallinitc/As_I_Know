"""Stateful, conditional LangGraph orchestration over demo evidence."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .core import stage1,stage2,stage3
from .bedrock import explain
from .providers import get_provider

class State(TypedDict, total=False):
    change:dict
    access_request:dict
    events:list
    stage1:dict
    stage2:dict
    stage3:dict
    investigation:dict
    narrative:str
    provider:str
    context:dict

def investigation_node(s):
    deviations=[x for x in s['stage3']['events'] if x['status']=='DEVIATION']
    return {'investigation':{'status':'REVIEW_REQUIRED','deviations':deviations}}
def summary_node(s):
    return {'narrative':explain({k:s.get(k) for k in ('provider','stage1','stage2','stage3','investigation')})}
def next_step(s, default_provider='aws'):
    return 'summary' if (s.get('provider') or default_provider) == 'snowflake' else ('privilege' if s['stage1']['status']=='VALID' else 'summary')
def after_audit(s):return 'investigate' if s['stage3']['status']=='DEVIATION_DETECTED' else 'summary'
def after_privilege(s, default_provider='aws'):return 'summary' if (s.get('provider') or default_provider) == 'snowflake' else 'audit'

def build(provider='aws'):
    """Build the workflow; state provider wins, with AWS as compatibility default."""
    def adapter_for(s):return get_provider(s.get('provider') or provider)
    def change_node(s):return {'stage1':adapter_for(s).evaluate_stage1(s['change'],s.get('context'))}
    def privilege_node(s):return {'stage2':adapter_for(s).evaluate_stage2(s['change'],s.get('access_request',{}),s.get('context'))}
    def audit_node(s):return {'stage3':adapter_for(s).evaluate_stage3(s['change'],s['events'],s.get('context'))}
    g=StateGraph(State)
    for name,fn in [('change',change_node),('privilege',privilege_node),('audit',audit_node),('investigate',investigation_node),('summary',summary_node)]:g.add_node(name,fn)
    g.add_edge(START,'change')
    g.add_conditional_edges('change',lambda s: next_step(s,provider),{'privilege':'privilege','summary':'summary'})
    g.add_conditional_edges('privilege',lambda s: after_privilege(s,provider),{'audit':'audit','summary':'summary'})
    g.add_conditional_edges('audit',after_audit,{'investigate':'investigate','summary':'summary'})
    g.add_edge('investigate','summary')
    g.add_edge('summary',END)
    return g.compile()
