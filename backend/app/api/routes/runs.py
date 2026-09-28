"""Run CRUD routes.

POST /runs creates a queued run; POST /runs/{id}/execute runs its adapter.
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.repositories.agent_repo import AgentRepository
from app.db.repositories.run_repo import RunRepository
from app.db.repositories.test_case_repo import TestCaseRepository
from app.db.models.run import RunModel
from app.schemas.run import RunCreate, RunResponse, RunStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["Runs"])


def _model_to_response(run: RunModel) -> RunResponse:
    return RunResponse(
        id=run.id,
        agent_id=run.agent_id,
        agent_version=run.agent_version,
        test_case_id=run.test_case_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        total_latency_ms=run.total_latency_ms,
        error=run.error,
        created_at=run.created_at,
    )


@router.post(
    "",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a queued run",
)
async def create_run(
    payload: RunCreate,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    """
    Create a new run record in QUEUED state.

    Validates that both the referenced Agent and TestCase exist.
    Snapshots the agent_version from the Agent record to preserve historical
    attribution — the version stored on the Run is immutable after creation.

    Execute the queued record through POST /runs/{run_id}/execute.
    """
    agent_repo = AgentRepository(db)
    tc_repo = TestCaseRepository(db)
    run_repo = RunRepository(db)

    # Validate agent exists
    agent = await agent_repo.get_by_id(payload.agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{payload.agent_id}' not found.",
        )

    # Validate test case exists
    tc = await tc_repo.get_by_id(payload.test_case_id)
    if tc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TestCase '{payload.test_case_id}' not found.",
        )

    # Snapshot agent_version from the agent record for historical traceability.
    # The caller may optionally supply an agent_version in the payload; if it
    # does not match the current agent version, we still store it to support
    # pinning to historical versions in future replay scenarios.
    run = await run_repo.create(
        id=uuid.uuid4(),
        agent_id=payload.agent_id,
        agent_version=payload.agent_version,
        test_case_id=payload.test_case_id,
        status=RunStatus.QUEUED.value,
    )
    logger.info(
        "Created run id=%s agent=%s version=%s test_case=%s",
        run.id,
        run.agent_id,
        run.agent_version,
        run.test_case_id,
    )
    return _model_to_response(run)


@router.get(
    "",
    response_model=list[RunResponse],
    summary="List runs",
)
async def list_runs(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    agent_id: Optional[uuid.UUID] = Query(default=None),
    test_case_id: Optional[uuid.UUID] = Query(default=None),
    run_status: Optional[str] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[RunResponse]:
    """Return a paginated list of runs with optional filtering."""
    repo = RunRepository(db)
    runs = await repo.list_filtered(
        agent_id=agent_id,
        test_case_id=test_case_id,
        status=run_status,
        offset=offset,
        limit=limit,
    )
    return [_model_to_response(r) for r in runs]


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    summary="Get run by ID",
)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    """Retrieve a single run by its UUID."""
    repo = RunRepository(db)
    run = await repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        )
    return _model_to_response(run)


@router.post("/{run_id}/execute", response_model=RunResponse)
async def execute_run_endpoint(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Execute a queued run; return after its status and trace are committed."""
    from app.runtime.executor import execute_run
    run = await RunRepository(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    run = await execute_run(db, run)
    await db.commit()
    return _model_to_response(run)
