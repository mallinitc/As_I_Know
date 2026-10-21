"""Conservative, deterministic analysis for synthetic demo events.

NOT a complete AWS IAM policy engine or authoritative CloudTrail parser.
"""
from __future__ import annotations
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import json
from .paths import data_dir

DATA = data_dir("aws")

def load(filename):
    return json.loads((DATA / filename).read_text(encoding='utf-8'))

def at(s):
    return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(timezone.utc)

def stage1(change):
    missing=[k for k in ('change_id','description','environment','actor','start','end','expected') if not change.get(k)]
    if change.get('start') and change.get('end') and at(change['start']) >= at(change['end']):
        missing.append('valid_change_window')
    return {'status':'VALID' if not missing else 'NEEDS_INFO','missing':missing,'expected':change.get('expected',[])}

REQUIRED_ACTIONS={'PutBucketPolicy': 's3:PutBucketPolicy', 'TerminateInstances':'ec2:TerminateInstances'}

def stage2(change, request):
    required=[REQUIRED_ACTIONS.get(x['eventName']) for x in change.get('expected',[])]
    if not request or any(r is None for r in required):
        return {'status':'MANUAL_REVIEW','reason':'Unknown operation or missing access request'}
    actions=request['actions']; resources=request['resources']
    missing=[a for a in required if not any(fnmatchcase(a.lower(),p.lower()) for p in actions)]
    if missing: return {'status':'INSUFFICIENT','missing_actions':missing}
    expected_resources=[x['resource'] for x in change['expected']]
    over=any('*' in p for p in actions) or any(r=='*' for r in resources)
    if any(not any(fnmatchcase(e,r) for r in resources) for e in expected_resources):
        return {'status':'INSUFFICIENT','reason':'Resource not granted in demo comparison'}
    return {'status':'OVERPRIVILEGED' if over else 'APPROPRIATE',
            'reason':'Wildcard scope/action in demo policy' if over else 'Demo action/resource match; IAM conditions and denies not evaluated',
            'warning':'Illustrative check only; not AWS effective permissions analysis'}

def relevant(e, change):
    # Consider same actor, or events on named target resources, within 2h of window.
    return (e['actor']==change['actor'] or any(r in e['resources'] for r in [x['resource'] for x in change['expected']])) and at(change['start']).timestamp()-7200 <= at(e['eventTime']).timestamp() <= at(change['end']).timestamp()+7200

def stage3(change, events):
    rows=[]
    for e in events:
        if not relevant(e,change) or e.get('readOnly') or e.get('errorCode'): continue
        reasons=[]
        if e['actor']!=change['actor']:reasons.append('ACTOR_MISMATCH')
        if not (at(change['start']) <= at(e['eventTime']) <= at(change['end'])):reasons.append('OUTSIDE_WINDOW')
        if not any(x['eventName']==e['eventName'] and x['resource'] in e['resources'] for x in change['expected']): reasons.append('UNEXPECTED_OPERATION_OR_RESOURCE')
        rows.append({'event_id':e['eventID'],'operation':e['eventName'],'status':'DEVIATION' if reasons else 'POTENTIAL_MATCH','reasons':reasons})
    observed_ids=[r['event_id'] for r in rows if r['status']=='POTENTIAL_MATCH']
    missing_expected=[x for x in change['expected'] if not any(e['eventID'] in observed_ids and e['eventName']==x['eventName'] and x['resource'] in e['resources'] for e in events)]
    return {'status':'DEVIATION_DETECTED' if any(x['status']=='DEVIATION' for x in rows) else ('EVIDENCE_INCOMPLETE' if missing_expected else 'POTENTIAL_MATCH'),'events':rows,'missing_expected':missing_expected,'warning':'CloudTrail event matching does not prove desired resource state'}

def unmatched(changes,events):
    out=[]
    for e in events:
        if e.get('readOnly') or e.get('errorCode'):continue
        matched=False
        for c in changes:
            if at(c['start'])<=at(e['eventTime'])<=at(c['end']) and e['actor']==c['actor'] and any(x['eventName']==e['eventName'] and x['resource'] in e['resources'] for x in c['expected']):
                matched=True;break
        if not matched:out.append({'event_id':e['eventID'],'operation':e['eventName'],'classification':'UNMATCHED_IN_AVAILABLE_RECORDS'})
    return out
