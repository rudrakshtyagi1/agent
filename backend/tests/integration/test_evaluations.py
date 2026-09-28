from uuid import uuid4, UUID
import pytest
from sqlalchemy import select
from app.db.models.trace import TraceSpanModel
from app.db.models.test_case import TestCaseModel


async def prepare(client, expectations=True):
    agent = (await client.post('/api/v1/agents',json={'name':str(uuid4()),'version':'1.0.0','endpoint':'builtin://support'})).json()
    payload = {'name':'Refund','input':{'order_id':'ORD-1001'}}
    if expectations:
        payload.update({'expected_tools':['lookup_order'],'expected_documents':['refund-policy-v1'],
                        'metadata':{'evaluation':{'expected_output':{'eligible':True},'max_latency_ms':1000}}})
    case = (await client.post('/api/v1/test-cases',json=payload)).json()
    run = (await client.post('/api/v1/runs',json={'agent_id':agent['id'],'agent_version':'1.0.0','test_case_id':case['id']})).json()
    return run, case


@pytest.mark.asyncio
async def test_evaluation_persistence_idempotence_and_frozen_expectations(client, test_session):
    run, case = await prepare(client)
    url = f"/api/v1/runs/{run['id']}"
    assert (await client.post(url+'/evaluate')).status_code == 409
    await client.post(url+'/execute')
    # Mutating the test case does not rewrite the historical execution contract.
    current = await test_session.get(TestCaseModel,UUID(case['id']))
    current.tc_metadata = {'evaluation':{'expected_output':{'eligible':False}}}
    await test_session.commit()
    first = await client.post(url+'/evaluate')
    assert first.status_code == 200, first.text
    report = first.json()
    assert len(report['results']) == 10
    assert report['summary']['task_success']['mean_score'] == 1
    assert report['summary']['token_usage']['unavailable'] == 1
    assert (await client.post(url+'/evaluate')).json() == report
    assert (await client.get(url+'/evaluations')).json() == report
    trace = (await client.get(url+'/trace')).json()
    ids = {s['id'] for s in trace['spans']}
    assert all(set(r['details']['evidence_span_ids']) <= ids for r in report['results'])
    assert all(r['details']['expectations_sha256'] for r in report['results'])


@pytest.mark.asyncio
async def test_legacy_trace_and_missing_labels(client, test_session):
    run, _ = await prepare(client,False)
    url = f"/api/v1/runs/{run['id']}"
    await client.post(url+'/execute')
    result = (await client.post(url+'/evaluate')).json()
    assert result['summary']['task_success']['unavailable'] == 1
    other, _ = await prepare(client)
    await client.post(f"/api/v1/runs/{other['id']}/execute")
    root = (await test_session.execute(select(TraceSpanModel).where(TraceSpanModel.run_id==UUID(other['id']),TraceSpanModel.parent_span_id.is_(None)))).scalar_one()
    root.span_metadata = {}
    await test_session.commit()
    assert (await client.post(f"/api/v1/runs/{other['id']}/evaluate")).status_code == 409
    assert (await client.post(f'/api/v1/runs/{uuid4()}/evaluate')).status_code == 404


@pytest.mark.asyncio
async def test_versioned_suite_report_and_history(client):
    assert (await client.get('/api/v1/evaluation-datasets')).json()[0]['case_count'] == 3
    response = await client.post('/api/v1/evaluation-suites/support-agent')
    assert response.status_code == 201, response.text
    report = response.json()
    assert len(report['cases']) == 3
    assert report['summary']['task_success']['passed'] == 2
    assert report['summary']['task_success']['judged'] == 3
    assert report['summary']['groundedness']['scored'] == 2
    assert report['summary']['groundedness']['unavailable'] == 1
    assert report['summary']['token_usage']['unavailable'] == 3
    assert len(report['dataset_sha256']) == 64
    assert (await client.get('/api/v1/evaluation-suites/'+report['id'])).json() == report
    assert (await client.get('/api/v1/evaluation-suites')).json()[0]['id'] == report['id']


@pytest.mark.asyncio
@pytest.mark.parametrize('evaluation',[{'max_latency_ms':-1},{'unexpected':True},{'expected_output':[]}])
async def test_invalid_contract_rejected(client,evaluation):
    response = await client.post('/api/v1/test-cases',json={'name':'Bad labels','metadata':{'evaluation':evaluation}})
    assert response.status_code == 422
