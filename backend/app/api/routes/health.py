"""Health check route."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    debug: bool
    timestamp: str


@router.get("/health", response_model=HealthResponse, summary="Application health check")
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
