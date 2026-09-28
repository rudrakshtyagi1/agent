import asyncio
from uuid import uuid4

import pytest

from app.schemas.trace import SpanType, TraceResponse
from app.tracing.tracer import Tracer


def test_nested_failure_preserves_exception_and_restores_parent():
    tracer = Tracer(uuid4())
    failure = TimeoutError("CRM unavailable")
    with tracer.span("agent", SpanType.PLANNER) as root:
        with pytest.raises(TimeoutError) as caught:
            with tracer.span("CRM", SpanType.TOOL_CALL):
                raise failure
        assert caught.value is failure
        with tracer.span("fallback", SpanType.MODEL) as fallback:
            fallback.output = {"answer": "Please try again"}
    trace = tracer.snapshot()
    assert [s.parent_span_id for s in trace.spans] == [None, root.id, root.id]
    assert trace.spans[1].error == "TimeoutError: CRM unavailable"
    assert trace.spans[0].error is None
    assert all(s.ended_at and s.duration_ms >= 0 for s in trace.spans)
    assert TraceResponse.model_validate_json(trace.model_dump_json()) == trace
    with tracer.span("new root", SpanType.PLANNER) as new_root:
        assert new_root.parent_span_id is None


@pytest.mark.asyncio
async def test_parallel_branches_keep_their_own_parent():
    tracer = Tracer(uuid4())
    async def branch(name):
        with tracer.span(name, SpanType.RETRIEVAL) as parent:
            await asyncio.sleep(0)
            with tracer.span(name + " child", SpanType.RERANKER) as child:
                assert child.parent_span_id == parent.id
            return parent
    with tracer.span("agent", SpanType.PLANNER) as root:
        branches = await asyncio.gather(branch("a"), branch("b"))
    assert all(branch.parent_span_id == root.id for branch in branches)


@pytest.mark.asyncio
async def test_cancellation_is_recorded_and_propagated():
    tracer = Tracer(uuid4())
    with pytest.raises(asyncio.CancelledError):
        with tracer.span("model", SpanType.MODEL):
            raise asyncio.CancelledError()
    record = tracer.snapshot().spans[0]
    assert record.error.startswith("CancelledError:")
    assert record.ended_at is not None


def test_snapshot_is_independent():
    tracer = Tracer(uuid4())
    with tracer.span("model", SpanType.MODEL) as record:
        record.output = {"tokens": [1]}
    snapshot = tracer.snapshot()
    snapshot.spans[0].output["tokens"].append(2)
    assert tracer.snapshot().spans[0].output == {"tokens": [1]}
