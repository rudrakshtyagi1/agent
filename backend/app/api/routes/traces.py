"""Read persisted traces by trace or run identifier."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.repositories.trace_repo import TraceSpanRepository
from app.schemas.trace import TraceResponse
from app.tracing.trace_store import span_response

router = APIRouter(tags=["Traces"])


@router.get("/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(trace_id: UUID, db: AsyncSession = Depends(get_db)):
    spans = await TraceSpanRepository(db).list_by_trace(trace_id)
    if not spans:
        raise HTTPException(404, "Trace not found")
    return TraceResponse(trace_id=trace_id, run_id=spans[0].run_id,
                         spans=[span_response(s) for s in spans])


@router.get("/runs/{run_id}/trace", response_model=TraceResponse)
async def get_run_trace(run_id: UUID, db: AsyncSession = Depends(get_db)):
    spans = await TraceSpanRepository(db).list_by_run(run_id)
    if not spans:
        raise HTTPException(404, "No persisted trace for this run")
    return TraceResponse(trace_id=spans[0].trace_id, run_id=run_id,
                         spans=[span_response(s) for s in spans])
