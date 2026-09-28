"""Bounded execution with atomic run status and trace persistence.

Only explicitly registered adapters run. User-supplied endpoints are never
imported or fetched. The caller owns the transaction and commits on success.
"""
import asyncio
from datetime import datetime, timezone
from time import perf_counter_ns

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import AgentModel
from app.db.models.run import RunModel
from app.db.models.test_case import TestCaseModel
from app.schemas.trace import SpanType
from app.evaluation.contracts import snapshot_case
from app.target_agents import support
from app.tracing.tracer import Tracer
from app.tracing.trace_store import save_trace


EXECUTION_TIMEOUT_SECONDS = 10


async def execute_run(db: AsyncSession, run: RunModel) -> RunModel:
    agent = await db.get(AgentModel, run.agent_id)
    case = await db.get(TestCaseModel, run.test_case_id)
    if agent is None or case is None:
        raise HTTPException(404, "Agent or test case no longer exists")
    if agent.status != "active":
        raise HTTPException(409, "Agent is not active")
    if agent.endpoint != support.ENDPOINT:
        raise HTTPException(422, "Unsupported adapter; use builtin://support")
    if agent.version != support.VERSION or run.agent_version != support.VERSION:
        raise HTTPException(409, "This adapter only executes version 1.0.0")
    # Conditional update prevents concurrent requests from executing a run twice.
    result = await db.execute(update(RunModel).where(
        RunModel.id == run.id, RunModel.status == "queued"
    ).values(status="running", started_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        raise HTTPException(409, "Only queued runs can be executed; create a new run to retry")
    await db.refresh(run)
    tracer = Tracer(run.id)
    started = perf_counter_ns()
    try:
        with tracer.span("support_agent", SpanType.PLANNER,
                         metadata={"agent_version": run.agent_version, "test_case_id": str(case.id),
                                   "test_case_snapshot": snapshot_case(case)}) as root:
            async with asyncio.timeout(EXECUTION_TIMEOUT_SECONDS):
                root.output = await support.execute(case.input, tracer)
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
    else:
        run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.total_latency_ms = (perf_counter_ns() - started) // 1_000_000
    await save_trace(db, tracer.snapshot())
    await db.flush()
    return run
