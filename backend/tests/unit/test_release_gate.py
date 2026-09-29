from copy import deepcopy
import pytest
from app.reliability.regression_detector import compare_cases
from app.reliability.release_gate import evaluate_gate
from app.schemas.regression import GatePolicy
from app.replay.replay_engine import Playback,ReplayMismatchError
from types import SimpleNamespace


def case(old=True,new=True):
    def result(value):
        return {'latency_ms':10,'evaluation':{'evaluator_version':'v1','results':[{'evaluator':'task_success','passed':value,'details':{'expectations_sha256':'same'}}]}}
    return {'case_id':'one','tags':['boundary'],'baseline':result(old),'candidate':result(new)}

@pytest.mark.parametrize('old,new,status',[(True,True,'passed'),(True,False,'failed'),(None,True,'blocked')])
def test_fail_closed(old,new,status):
    report=compare_cases([case(old,new)])
    gate=evaluate_gate(report['summary'],GatePolicy(min_measured_cases=1))
    assert gate['status']==status


def test_incompatible_expectations_missing_latency_and_duplicate_ids():
    pair=case()
    pair['candidate']['evaluation']['results'][0]['details']['expectations_sha256']='changed'
    assert evaluate_gate(compare_cases([pair])['summary'],GatePolicy(min_measured_cases=1))['status']=='blocked'
    pair=case()
    pair['candidate']['latency_ms']=None
    assert evaluate_gate(compare_cases([pair])['summary'],GatePolicy(min_measured_cases=1,max_mean_latency_increase_ms=100))['status']=='blocked'
    with pytest.raises(ValueError):
        compare_cases([pair,deepcopy(pair)])
    assert evaluate_gate(compare_cases([])['summary'],GatePolicy())['status']=='blocked'


def test_playback_requires_exact_order_input_and_full_consumption():
    playback=Playback({'records':[{'name':'lookup_order','input':{'order_id':'A'},'output':{'days':2},'error':None,'span_id':'x'}]})
    span=SimpleNamespace(metadata={},output=None)
    with pytest.raises(ReplayMismatchError):
        playback.consume('lookup_order',{'order_id':'B'},span)
    with pytest.raises(ReplayMismatchError):
        playback.assert_consumed()
    assert playback.consume('lookup_order',{'order_id':'A'},span)=={'days':2}
    playback.assert_consumed()
    with pytest.raises(ReplayMismatchError):
        playback.consume('lookup_order',{'order_id':'A'},span)
