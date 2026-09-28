"""End-to-end execution, failure preservation, and trace boundaries."""
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.trace import TraceSpanModel
from app.tracing.tracer import Tracer
from app.tracing.trace_store import save_trace
from app.schemas.trace import SpanType


async def queued_run(client, payload=None, endpoint="builtin://support", version="1.0.0"):
    agent = (await client.post('/api/v1/agents', json={
        'name': str(uuid4()), 'version': version, 'endpoint': endpoint,
    })).json()
    case = (await client.post('/api/v1/test-cases', json={
        'name': 'Refund', 'input': payload or {},
    })).json()
    return (await client.post('/api/v1/runs', json={
        'agent_id': agent['id'], 'test_case_id': case['id'], 'agent_version': version,
    })).json()


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario,status,count', [('success','completed',7), ('tool_timeout','failed',5)])
async def test_execute_and_persist(client, test_engine, scenario, status, count):
    run = await queued_run(client, {'scenario': scenario})
    url = f"/api/v1/runs/{run['id']}"
    response = await client.post(url + '/execute')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == status
    assert result['started_at'] and result['completed_at']
    trace = (await client.get(url + '/trace')).json()
    assert len(trace['spans']) == count
    assert all(s['run_id'] == run['id'] and s['ended_at'] for s in trace['spans'])
    assert len({s['trace_id'] for s in trace['spans']}) == 1
    assert (await client.get('/api/v1/traces/' + trace['trace_id'])).json() == trace
    # New session proves the request committed; no dependency on tracer memory.
    async with async_sessionmaker(test_engine)() as session:
        rows = (await session.execute(select(TraceSpanModel))).scalars().all()
        assert len(rows) == count
    if status == 'failed':
        assert 'TimeoutError' in result['error']
        assert trace['spans'][-1]['name'] == 'lookup_order'
        assert trace['spans'][-1]['error']
        assert not trace['spans'][3]['error']
    else:
        assert trace['spans'][-1]['output']['eligible'] is True
    assert (await client.post(url + '/execute')).status_code == 409
    assert (await client.get(url + '/trace')).json() == trace


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint,version,code', [('https://example.com','1.0.0',422), ('builtin://support','2.0.0',409)])
async def test_reject_unsupported_adapter(client, endpoint, version, code):
    run = await queued_run(client, endpoint=endpoint, version=version)
    url = f"/api/v1/runs/{run['id']}"
    assert (await client.post(url + '/execute')).status_code == code
    assert (await client.get(url)).json()['status'] == 'queued'
    assert (await client.get(url + '/trace')).status_code == 404


@pytest.mark.asyncio
async def test_validation_failure_and_negative_refund(client):
    invalid = await queued_run(client, {'order_id': 'unknown'})
    result = await client.post(f"/api/v1/runs/{invalid['id']}/execute")
    assert result.json()['status'] == 'failed'
    trace = (await client.get(f"/api/v1/runs/{invalid['id']}/trace")).json()
    assert trace['spans'][-1]['name'] == 'validate_input'
    run = await queued_run(client, {'order_id': 'ORD-1002'})
    await client.post(f"/api/v1/runs/{run['id']}/execute")
    trace = (await client.get(f"/api/v1/runs/{run['id']}/trace")).json()
    assert trace['spans'][-1]['output']['eligible'] is False


@pytest.mark.asyncio
async def test_missing_and_pagination(client):
    assert (await client.post(f'/api/v1/runs/{uuid4()}/execute')).status_code == 404
    assert (await client.get(f'/api/v1/traces/{uuid4()}')).status_code == 404
    assert (await client.get('/api/v1/runs?limit=0')).status_code == 422


@pytest.mark.asyncio
async def test_store_rejects_foreign_parent_and_ownership(test_session):
    tracer = Tracer(uuid4())
    with tracer.span('root', SpanType.PLANNER):
        pass
    trace = tracer.snapshot()
    trace.spans[0].run_id = uuid4()
    with pytest.raises(ValueError, match='belong'):
        await save_trace(test_session, trace)
    trace.spans[0].run_id = trace.run_id
    trace.spans[0].parent_span_id = uuid4()
    with pytest.raises(ValueError, match='parent'):
        await save_trace(test_session, trace)


@pytest.mark.asyncio
async def test_restart_and_concurrent_execution(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from app.main import create_app
    from app.db.session import Base, get_db, create_engine_from_url, create_session_factory

    url = f"sqlite+aiosqlite:///{tmp_path / 'persistent.db'}"
    engine = create_engine_from_url(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    app = create_app()
    async def dependency():
        async with factory() as session:
            yield session
            await session.commit()
    app.dependency_overrides[get_db] = dependency
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        run = await queued_run(client)
        results = await asyncio.gather(*[
            client.post(f"/api/v1/runs/{run['id']}/execute") for _ in range(2)
        ])
        assert sorted(r.status_code for r in results) == [200,409]
        before = (await client.get(f"/api/v1/runs/{run['id']}/trace")).json()
        evaluations = await asyncio.gather(*[
            client.post(f"/api/v1/runs/{run['id']}/evaluate") for _ in range(2)
        ])
        assert all(r.status_code == 200 for r in evaluations)
        assert evaluations[0].json() == evaluations[1].json()
        saved_evaluation = evaluations[0].json()
        campaign_response = await client.post('/api/v1/chaos/campaigns', json={'faults':['tool_timeout']})
        assert campaign_response.status_code == 201
        saved_campaign = campaign_response.json()
    await engine.dispose()
    # Recreate the engine and application against the existing file.
    engine = create_engine_from_url(url)
    factory = create_session_factory(engine)
    app = create_app()
    app.dependency_overrides[get_db] = dependency
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get(f"/api/v1/runs/{run['id']}/trace")).json() == before
        assert (await client.get(f"/api/v1/runs/{run['id']}/evaluations")).json() == saved_evaluation
        assert (await client.get('/api/v1/chaos/campaigns/' + saved_campaign['id'])).json() == saved_campaign
    await engine.dispose()


@pytest.mark.asyncio
async def test_execution_deadline_preserves_partial_trace(client, monkeypatch):
    from app.runtime import executor
    monkeypatch.setattr(executor, 'EXECUTION_TIMEOUT_SECONDS', 0.005)
    run = await queued_run(client)
    response = await client.post(f"/api/v1/runs/{run['id']}/execute")
    assert response.json()['status'] == 'failed'
    assert response.json()['error'].startswith('TimeoutError:')
    trace = (await client.get(f"/api/v1/runs/{run['id']}/trace")).json()
    assert trace['spans'][-1]['name'] == 'retrieve_refund_policy'
    assert trace['spans'][-1]['error'].startswith('CancelledError:')
    assert all(s['ended_at'] for s in trace['spans'])
