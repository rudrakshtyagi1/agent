"""Every query derives tenant scope from authentication, never client JSON."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models.monitoring import MonitorTrace, MonitorTenant, MonitorAlert
from app.monitoring.security import tenant
from app.monitoring.schemas import IncomingTrace
from app.monitoring.service import admit, window_metrics
from app.config import get_settings

router = APIRouter(prefix="/monitoring", tags=["Live monitoring"])


@router.post("/traces", status_code=202)
async def ingest(
    payload: IncomingTrace, owner=Depends(tenant), db: AsyncSession = Depends(get_db)
):
    return await admit(db, owner, payload, get_settings())


@router.get("/traces")
async def traces(
    owner=Depends(tenant),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
):
    rows = (
        (
            await db.execute(
                select(MonitorTrace)
                .where(MonitorTrace.tenant == owner)
                .order_by(MonitorTrace.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "trace_id": r.external_id,
            "status": r.status,
            "created_at": r.created_at,
            "summary": r.summary,
        }
        for r in rows
    ]


@router.get("/traces/{trace_id}")
async def trace(
    trace_id: str, owner=Depends(tenant), db: AsyncSession = Depends(get_db)
):
    row = (
        await db.execute(
            select(MonitorTrace).where(
                MonitorTrace.id == trace_id, MonitorTrace.tenant == owner
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Trace not found")
    return {
        "id": row.id,
        "status": row.status,
        "payload": row.payload,
        "summary": row.summary,
        "created_at": row.created_at,
    }


@router.get("/overview")
async def overview(
    request: Request, owner=Depends(tenant), db: AsyncSession = Depends(get_db)
):
    settings = get_settings()
    counter = await db.get(MonitorTenant, owner)
    counts = dict(
        (
            await db.execute(
                select(MonitorTrace.status, func.count())
                .where(MonitorTrace.tenant == owner)
                .group_by(MonitorTrace.status)
            )
        ).all()
    )
    rows = (
        (
            await db.execute(
                select(MonitorTrace)
                .where(MonitorTrace.tenant == owner, MonitorTrace.status == "processed")
                .order_by(MonitorTrace.created_at.desc())
                .limit(settings.monitor_window)
            )
        )
        .scalars()
        .all()
    )
    return {
        "tenant": owner,
        "auth_mode": "bearer" if settings.monitor_keys else "local_demo",
        "counts": counts,
        "admission": {
            k: getattr(counter, k, 0) if counter else 0
            for k in ("accepted", "sampled_out", "rejected", "dropped_spans")
        },
        "window": window_metrics(rows),
        "worker": getattr(
            request.app.state,
            "monitor_health",
            {"last_success": None, "error": "Worker not started"},
        ),
        "policy": {
            "sample_rate": settings.monitor_sample_rate,
            "retention_days": settings.monitor_retention_days,
            "capture_payloads": settings.monitor_capture_payloads,
            "queue_capacity": settings.monitor_queue_capacity,
            "window": settings.monitor_window,
            "min_samples": settings.monitor_min_samples,
            "failure_rate": settings.monitor_failure_rate,
            "latency_ms": settings.monitor_latency_ms,
        },
    }


@router.get("/alerts")
async def alerts(owner=Depends(tenant), db: AsyncSession = Depends(get_db)):
    rows = (
        (
            await db.execute(
                select(MonitorAlert)
                .where(MonitorAlert.tenant == owner)
                .order_by(MonitorAlert.created_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "status": r.status,
            "evidence": r.evidence,
            "created_at": r.created_at,
            "resolved_at": r.resolved_at,
        }
        for r in rows
    ]
