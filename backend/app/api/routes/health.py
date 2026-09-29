"""Health check route."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    debug: bool
    timestamp: str


@router.get(
    "/health", response_model=HealthResponse, summary="Application health check"
)
async def health_check() -> HealthResponse:
    """Return current application health status and runtime environment."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
        debug=settings.debug,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/ready", summary="Database and monitoring worker readiness")
async def readiness(request: Request):
    import asyncio
    from sqlalchemy import text
    from fastapi.responses import JSONResponse
    from app.db import session as database

    try:
        async with asyncio.timeout(3):
            async with database._session_factory() as db:
                await db.execute(text("SELECT 1"))
        health = getattr(request.app.state, "monitor_health", {})
        last = health.get("last_success")
        if not last or health.get("error"):
            raise RuntimeError("Worker unavailable")
        age = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(last).replace(tzinfo=timezone.utc)
        ).total_seconds()
        if age > max(30, get_settings().monitor_poll_seconds * 3):
            raise RuntimeError("Worker stale")
    except Exception:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return {"status": "ready"}
