from uuid import uuid4,UUID
import pytest
from sqlalchemy import select
from app.db.models.run import RunModel
from app.db.models.trace import TraceSpanModel
from app.db.models.failure import FailureModel


async def prepare(client,expected=True):
    agent=(await client.post('/api/v1/agents',json={'name':str(uuid4()),'version':'1.0.0','endpoint':'builtin://support'})).json()
    case=(await client.post('/api/v1/test-cases',json={'name':'Diagnosis','input':{},
        'metadata':{'evaluation':{'expected_output':{'eligible':expected}}}})).json()
    return (await client.post('/api/v1/runs',json={'agent_id':agent['id'],'agent_version':'1.0.0','test_case_id':case['id']})).json()


@pytest.mark.asyncio
async def test_saved_diagnosis_links_grouping_and_idempotence(client,test_session):
    run=await prepare(client)
    url=f"/api/v1/runs/{run['id']}"
    assert (await client.get(url+'/diagnosis')).json() is None
    assert (await client.post(url+'/diagnose')).status_code==409
    await client.post(url+'/execute',json={'fault':{'kind':'tool_timeout'}})
    result=await client.post(url+'/diagnose')
    assert result.status_code==200,result.text
    report=result.json()
    assert report['outcome']=='failed'
    primary=next(f for f in report['findings'] if f['id']==report['primary_finding_id'])
    assert primary['subtype']=='tool_timeout'
    assert len(primary['injection_evidence'])==1
    assert primary['cause_status']=='unknown'
    trace=(await client.get(url+'/trace')).json()
    ids={s['id'] for s in trace['spans']}
    assert all(set(f['evidence_span_ids'])<=ids for f in report['findings'])
    assert (await client.post(url+'/diagnose')).json()==report
    assert (await client.get(url+'/diagnosis')).json()==report
    assert (await client.get(url)).json()['status']=='failed'
    assert len((await test_session.execute(select(FailureModel))).scalars().all())==len(report['findings'])
    groups=(await client.get('/api/v1/failures/groups')).json()['groups']
    assert groups[0]['occurrences']==1
    assert groups[0]['runs'][0]['run_id']==run['id']


@pytest.mark.asyncio
async def test_recovered_and_wrong_answer_runs_are_analyzed(client):
    recovered=await prepare(client)
    url=f"/api/v1/runs/{recovered['id']}"
    await client.post(url+'/execute',json={'fault':{'kind':'malformed_tool'},'retry':{'max_attempts':2,'backoff_ms':0}})
    report=(await client.post(url+'/diagnose')).json()
    assert report['outcome']=='recovered'
    assert report['task_passed'] is True
    assert report['findings'][0]['recovery_span_ids']
    wrong=await prepare(client,False)
    url=f"/api/v1/runs/{wrong['id']}"
    await client.post(url+'/execute')
    report=(await client.post(url+'/diagnose')).json()
    assert report['outcome']=='checks_failed'
    assert report['findings'][0]['subtype']=='reference_mismatch'
    assert (await client.get(url)).json()['status']=='completed'
    result=(await client.post('/api/v1/failures/analyze-recent?limit=20')).json()
    assert result['analyzed']==2
    assert (await client.post('/api/v1/failures/analyze-recent?limit=51')).status_code==422


@pytest.mark.asyncio
async def test_legacy_error_still_diagnosed_without_evaluation(client,test_session):
    run=await prepare(client)
    url=f"/api/v1/runs/{run['id']}"
    await client.post(url+'/execute',json={'fault':{'kind':'tool_timeout'}})
    root=(await test_session.execute(select(TraceSpanModel).where(TraceSpanModel.run_id==UUID(run['id']),TraceSpanModel.parent_span_id.is_(None)))).scalar_one()
    root.span_metadata={}
    await test_session.commit()
    report=(await client.post(url+'/diagnose')).json()
    assert report['evaluation_note']
    assert report['findings'][0]['subtype']=='tool_timeout'
    assert (await client.post(f'/api/v1/runs/{uuid4()}/diagnose')).status_code==404


@pytest.mark.asyncio
async def test_blind_fixture_audit_and_persistence(client):
    assert (await client.get('/api/v1/failures/benchmarks/latest')).json() is None
    response=await client.post('/api/v1/failures/benchmark')
    assert response.status_code==201,response.text
    result=response.json()
    assert result['total']==9
    assert result['correct']==9,result['samples']
    assert (await client.get('/api/v1/failures/benchmarks/latest')).json()==result
    groups=(await client.get('/api/v1/failures/groups')).json()['groups']
    timeouts=next(g for g in groups if g['subtype']=='tool_timeout')
    assert timeouts['occurrences']==2
    assert timeouts['recovered']==1
