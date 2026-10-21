from arca.core import load,stage1,stage2,stage3,unmatched
from arca.workflow import build

def sample():
    c=load('changes.json');a=load('access_requests.json');e=load('events.json');return c,a,e

def test_stage1():
    c,_,_=sample();assert stage1(c[0])['status']=='VALID'

def test_stage2():
    c,a,_=sample();assert stage2(c[0],a[0])['status']=='OVERPRIVILEGED'
    assert stage2(c[1],a[1])['status']=='APPROPRIATE'

def test_deviation():
    c,_,e=sample();assert stage3(c[0],e)['status']=='DEVIATION_DETECTED'

def test_unmatched():
    c,_,e=sample();assert len(unmatched(c,e))>=2

def test_langgraph_end_to_end():
    c,a,e=sample(); result=build().invoke({'change':c[0],'access_request':a[0],'events':e})
    assert result['investigation']['status']=='REVIEW_REQUIRED'
    assert 'narrative' in result
