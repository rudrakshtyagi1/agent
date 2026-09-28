"""Counterexamples for diagnosis certainty, propagation, and recovery."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from uuid import uuid4
from app.failure_intelligence.root_cause import diagnose
from app.failure_intelligence.clustering import fingerprint


def span(name='lookup_order',kind='tool_call',error=None,parent=None,output=None,attempt=None,start=0,end=1,metadata=None):
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    return NS(id=uuid4(),name=name,span_type=kind,error=error,parent_span_id=parent,
              output=output,input={'order_id':'ORD-1001'},span_metadata=metadata or ({'attempt':attempt} if attempt else {}),
              started_at=now+timedelta(seconds=start),ended_at=now+timedelta(seconds=end))


def run(status='failed',error='failure'):
    return NS(id=uuid4(),status=status,error=error)


def test_propagation_is_not_multiple_causes():
    root=span('agent','planner','TimeoutError: tool',end=4)
    parent=span('plan','planner',root.error,root.id,end=3)
    child=span(error=root.error,parent=parent.id,end=2)
    result=diagnose(run(),[root,parent,child])
    assert len(result['findings'])==1
    assert result['findings'][0]['component']=='lookup_order'
    assert result['findings'][0]['cause_status']=='unknown'


def test_recovery_requires_matching_scope_and_attempt():
    root=span('agent','planner',metadata={'test_case_snapshot':{}})
    failed=span(error='TimeoutError: no reply',parent=root.id,attempt=1)
    unrelated=span(parent=uuid4(),attempt=2,start=2,end=3)
    assert diagnose(run('completed'),[root,failed,unrelated])['findings'][0]['status']=='unresolved'
    recovered=span(parent=root.id,attempt=2,start=2,end=3)
    result=diagnose(run('completed'),[root,failed,recovered])
    assert result['outcome']=='recovered'
    assert result['findings'][0]['recovery_span_ids']==[str(recovered.id)]


def test_deadline_distinguished_from_cancellation_symptom():
    root=span('agent','planner','TimeoutError: ',end=3)
    child=span(error='CancelledError: ',parent=root.id,end=2)
    result=diagnose(run(),[root,child])
    assert len(result['findings'])==1
    assert result['findings'][0]['subtype']=='execution_deadline'


def test_configured_fault_does_not_override_observed_error():
    root=span('agent','planner',metadata={'execution_options':{'fault':{'kind':'missing_documents'}}})
    child=span(error='TimeoutError: tool',parent=root.id)
    result=diagnose(run(),[root,child])
    assert result['findings'][0]['subtype']=='tool_timeout'
    assert result['findings'][0]['injection_evidence']==[]


def test_unknown_and_clean_are_not_false_certainty():
    result=diagnose(run(),[])
    assert result['outcome']=='unknown'
    assert result['findings'][0]['evidence_level']=='unknown'
    clean=diagnose(run('completed'),[])
    assert clean['outcome']=='no_failure_observed'
    assert clean['task_passed'] is None


def test_completed_wrong_answer_is_a_failed_check_not_proven_cause():
    result=diagnose(run('completed'),[],{'results':[{'id':str(uuid4()),'evaluator':'task_success',
        'passed':False,'details':{'reason':'Reference mismatch','evidence_span_ids':[]}}]})
    assert result['outcome']=='checks_failed'
    assert result['findings'][0]['subtype']=='reference_mismatch'
    assert result['findings'][0]['cause_status']=='unknown'


def test_grouping_ignores_run_ids_but_not_components():
    assert fingerprint('tool_error','tool_timeout','lookup') == fingerprint('tool_error','tool_timeout','lookup')
    assert fingerprint('tool_error','tool_timeout','lookup') != fingerprint('tool_error','tool_timeout','search')


def test_later_failure_is_not_hidden_by_earlier_recovery():
    root=span('agent','planner')
    first=span(error='TimeoutError: no reply',parent=root.id,attempt=1)
    recovery=span(parent=root.id,attempt=2,start=2,end=3)
    last=span(error='TimeoutError: no reply',parent=root.id,attempt=3,start=4,end=5)
    result=diagnose(run(),[root,first,recovery,last])
    assert len(result['findings'])==1
    assert result['findings'][0]['status']=='unresolved'
    assert len(result['findings'][0]['evidence_span_ids'])==2
