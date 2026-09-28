"""Fault reproducibility and retry safety boundaries."""
import asyncio
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.chaos.engine import FaultInjector
from app.runtime.retry import run_with_retry, RecoverableStepError
from app.schemas.chaos import FaultConfig, RetryPolicy, CampaignRequest
from app.tracing.tracer import Tracer


def decisions(seed, probability=0.5):
    tracer = Tracer(uuid4())
    injector = FaultInjector(FaultConfig(kind='tool_timeout', seed=seed, probability=probability,
                                        fail_first_attempts=3), tracer)
    return [injector.decide('lookup_order', i) for i in range(1,4)], tracer.snapshot()


def test_seed_reproducibility_and_isolation():
    first, trace = decisions(42)
    decisions(91)
    assert decisions(42)[0] == first
    assert [s.output for s in decisions(42)[1].spans] == [s.output for s in trace.spans]
    assert decisions(42,0)[0] == [None]*3
    assert decisions(42,1)[0] == ['tool_timeout']*3
    assert decisions(1)[1].spans[0].output['draw'] != trace.spans[0].output['draw']


def test_fault_window_and_target():
    tracer = Tracer(uuid4())
    injector = FaultInjector(FaultConfig(kind='missing_documents'),tracer)
    assert injector.decide('lookup_order',1) is None
    assert injector.decide('retrieve_refund_policy',1) == 'missing_documents'
    assert injector.decide('retrieve_refund_policy',2) is None
    assert len(tracer.snapshot().spans) == 2


@pytest.mark.asyncio
async def test_retry_limits_and_no_cancellation_swallowing():
    tracer = Tracer(uuid4())
    calls = []
    async def broken(attempt):
        calls.append(attempt)
        raise RecoverableStepError('broken')
    with pytest.raises(RecoverableStepError):
        await run_with_retry(broken, RetryPolicy(max_attempts=3,backoff_ms=0), tracer, 'tool')
    assert calls == [1,2,3]
    assert len(tracer.snapshot().spans) == 2
    for error in (asyncio.CancelledError(), ValueError('not recoverable')):
        calls.clear()
        async def stop(attempt):
            calls.append(attempt)
            raise error
        with pytest.raises(type(error)):
            await run_with_retry(stop,RetryPolicy(max_attempts=3),tracer,'tool')
        assert calls == [1]


@pytest.mark.parametrize('payload',[
    {'retry':{'max_attempts':4}}, {'retry':{'backoff_ms':201}},
    {'probability':1.1}, {'seed':-1}, {'fail_first_attempts':0},
    {'faults':['tool_timeout','tool_timeout']}, {'faults':[]}, {'faults':['unknown']},
])
def test_campaign_bounds(payload):
    with pytest.raises(ValidationError):
        CampaignRequest.model_validate(payload)
