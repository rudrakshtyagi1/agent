from uuid import uuid4
import pytest
from app.schemas.chaos import FAULT_KINDS


async def queued(client):
    agent = (await client.post('/api/v1/agents',json={'name':str(uuid4()),'version':'1.0.0','endpoint':'builtin://support'})).json()
    case = (await client.post('/api/v1/test-cases',json={'name':'Resilience','input':{},
        'metadata':{'evaluation':{'expected_output':{'eligible':True}}}})).json()
    return (await client.post('/api/v1/runs',json={'agent_id':agent['id'],'test_case_id':case['id'],'agent_version':'1.0.0'})).json()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',FAULT_KINDS)
async def test_transient_fault_recovery_and_evidence(client, kind):
    run = await queued(client)
    url = f"/api/v1/runs/{run['id']}"
    options = {'fault':{'kind':kind,'seed':17}, 'retry':{'max_attempts':2,'backoff_ms':0}}
    response = await client.post(url+'/execute',json=options)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'completed'
    spans = (await client.get(url+'/trace')).json()['spans']
    assert spans[0]['metadata']['execution_options']['fault']['kind'] == kind
    events = [s for s in spans if s['name']=='fault_decision']
    assert [s['output']['injected'] for s in events] == [True,False]
    assert len([s for s in spans if s['name']=='retry_scheduled']) == 1
    target = events[0]['output']['target']
    attempts = [s for s in spans if s['name']==target]
    assert [s['metadata']['attempt'] for s in attempts] == [1,2]
    assert attempts[0]['error'] and not attempts[1]['error']
    if kind in ('malformed_tool','missing_documents','irrelevant_retrieval'):
        assert attempts[0]['output'] is not None
    evaluations = (await client.post(url+'/evaluate')).json()
    assert evaluations['summary']['task_success']['mean_score'] == 1
    assert evaluations['summary']['groundedness']['mean_score'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',FAULT_KINDS)
async def test_persistent_fault_exhausts_budget_without_answer(client,kind):
    run = await queued(client)
    url = f"/api/v1/runs/{run['id']}"
    response = await client.post(url+'/execute',json={'fault':{'kind':kind,'fail_first_attempts':3},'retry':{'max_attempts':2,'backoff_ms':0}})
    assert response.json()['status'] == 'failed'
    spans = (await client.get(url+'/trace')).json()['spans']
    assert not any(s['span_type']=='final_response' for s in spans)
    assert len([s for s in spans if s['name']=='fault_decision']) == 2
    assert len([s for s in spans if s['name']=='retry_scheduled']) == 1
    assert (await client.post(url+'/evaluate')).json()['summary']['task_success']['mean_score'] == 0


@pytest.mark.asyncio
async def test_campaign_pairs_persistence_and_denominators(client):
    result = await client.post('/api/v1/chaos/campaigns',json={'retry':{'max_attempts':2,'backoff_ms':0}})
    assert result.status_code == 201, result.text
    report = result.json()
    assert report['baseline']['task_passed'] is True
    assert report['summary']['recovered_cases'] == 4
    assert report['summary']['injected_cases'] == 4
    assert report['summary']['retry_rescued_cases'] == 4
    baseline_hash = report['baseline']['evaluation']['results'][0]['details']['expectations_sha256']
    for pair in report['comparisons']:
        assert pair['protected']['evaluation']['results'][0]['details']['expectations_sha256'] == baseline_hash
        assert pair['unprotected']['evaluation']['results'][0]['details']['expectations_sha256'] == baseline_hash
        assert pair['unprotected']['task_passed'] is False
        assert pair['protected']['task_passed'] is True
        assert pair['unprotected']['fault_events'][0]['draw'] == pair['protected']['fault_events'][0]['draw']
    assert (await client.get('/api/v1/chaos/campaigns/'+report['id'])).json() == report
    assert (await client.get('/api/v1/chaos/campaigns')).json()[0]['id'] == report['id']
    control = (await client.post('/api/v1/chaos/campaigns',json={'faults':['tool_timeout'],'probability':0})).json()
    assert control['summary']['recovery_rate'] is None
    assert control['summary']['injected_cases'] == 0
    assert control['summary']['not_injected_cases'] == 1
    assert control['comparisons'][0]['recovered'] is None
    persistent = (await client.post('/api/v1/chaos/campaigns',json={'faults':['tool_timeout'],'fail_first_attempts':3})).json()
    assert persistent['summary']['recovery_rate'] == 0
    assert persistent['summary']['retry_rescued_cases'] == 0


@pytest.mark.asyncio
async def test_bad_options_do_not_claim_run(client):
    run = await queued(client)
    url = f"/api/v1/runs/{run['id']}"
    assert (await client.post(url+'/execute',json={'fault':{'kind':'unknown'}})).status_code == 422
    assert (await client.get(url)).json()['status'] == 'queued'
    assert (await client.get(f'/api/v1/chaos/campaigns/{uuid4()}')).status_code == 404
    assert len((await client.get('/api/v1/chaos/faults')).json()['faults']) == 4


@pytest.mark.asyncio
async def test_overall_deadline_interrupts_retry_backoff(client,monkeypatch):
    from app.runtime import executor
    monkeypatch.setattr(executor,'EXECUTION_TIMEOUT_SECONDS',0.15)
    run = await queued(client)
    url = f"/api/v1/runs/{run['id']}"
    response = await client.post(url+'/execute',json={'fault':{'kind':'tool_timeout'},'retry':{'max_attempts':3,'backoff_ms':200}})
    assert response.json()['status'] == 'failed'
    spans = (await client.get(url+'/trace')).json()['spans']
    assert len([s for s in spans if s['name']=='lookup_order']) == 1
    assert any(s['name']=='retry_scheduled' for s in spans)
    assert not any(s['span_type']=='final_response' for s in spans)


@pytest.mark.asyncio
async def test_scheduled_retry_is_not_counted_as_started(client,monkeypatch):
    from app.runtime import executor
    monkeypatch.setattr(executor,'EXECUTION_TIMEOUT_SECONDS',0.15)
    result = await client.post('/api/v1/chaos/campaigns',json={
        'faults':['tool_timeout'], 'retry':{'max_attempts':2,'backoff_ms':200}})
    assert result.status_code == 201
    protected = result.json()['comparisons'][0]['protected']
    assert protected['status'] == 'failed'
    assert protected['scheduled_retry_count'] == 1
    assert protected['retry_count'] == 0
