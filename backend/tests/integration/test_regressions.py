import pytest
from app.target_agents import support

@pytest.mark.asyncio
@pytest.mark.parametrize('candidate,passes,regressions,status', [('1.1.0',5,0,'passed'),('1.1.0-regression',2,2,'failed')])
async def test_comparison_gate_and_saved_evidence(client,candidate,passes,regressions,status):
    response=await client.post('/api/v1/regressions/compare',json={'candidate_version':candidate})
    assert response.status_code==201,response.text
    report=response.json()
    assert report['summary']['baseline_passes']==4
    assert report['summary']['candidate_passes']==passes
    assert report['summary']['regressions']==regressions
    assert report['gate']['status']==status
    assert report['summary']['measured_pairs']==5
    assert report['slices']['boundary']['total']==2
    assert (await client.get('/api/v1/regressions/reports/'+report['id'])).json()==report
    assert (await client.get('/api/v1/regressions/reports')).json()[0]['id']==report['id']
    source=report['cases'][0]['baseline']['run_id']
    # Playback must use stored responses even when the fixture changes.
    original=support.ORDER_AGES['ORD-1001']
    try:
        support.ORDER_AGES['ORD-1001']=99
        playback=await client.post(f'/api/v1/runs/{source}/replay',json={'candidate_version':'1.1.0'})
    finally:
        support.ORDER_AGES['ORD-1001']=original
    assert playback.status_code==201,playback.text
    replay=playback.json()
    assert replay['status']=='completed',replay
    assert replay['consumed_calls']==replay['recorded_calls']==2
    assert replay['candidate_output']==replay['source_output']
    trace=(await client.get(f"/api/v1/runs/{replay['run_id']}/trace")).json()
    boundaries=[s for s in trace['spans'] if s['span_type'] in ('retrieval','tool_call')]
    assert all(s['metadata']['replayed'] for s in boundaries)
    failed_source=report['cases'][-1]['baseline']['run_id']
    mismatch=(await client.post(f'/api/v1/runs/{failed_source}/replay',json={'candidate_version':'1.1.0'})).json()
    assert mismatch['status']=='failed'
    assert 'ReplayMismatchError' in mismatch['error']

@pytest.mark.asyncio
async def test_invalid_version_rejected(client):
    assert (await client.post('/api/v1/regressions/compare',json={'candidate_version':'unknown'})).status_code==422
