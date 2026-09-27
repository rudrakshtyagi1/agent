"""
AgentGuard FastAPI application entry point.

Responsibilities:
- Create and configure the FastAPI app.
- Manage async lifespan (DB init on startup, dispose on shutdown).
- Register API routers.
- Configure CORS.
- Set up structured exception handlers.
- Configure application logging.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.observability.logging import setup_logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown sequences."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Starting %s [env=%s]", settings.app_name, settings.app_env)

    # Initialise database engine and create tables
    from app.db.session import close_db, init_db, init_engine

    init_engine(settings.database_url)
    await init_db()
    logger.info("Database ready.")

    yield  # Application runs here

    await close_db()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "AgentGuard — AI Agent Reliability, Evaluation, Observability, "
            "and Failure-Intelligence Platform"
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ #
    # CORS — configurable; permissive in development, locked in production
    # ------------------------------------------------------------------ #
    if settings.is_production:
        allow_origins = []  # Override with explicit domain list in production
    else:
        allow_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ #
    # Exception handlers
    # ------------------------------------------------------------------ #

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "status_code": exc.status_code},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal server error", "status_code": 500},
        )

    # ------------------------------------------------------------------ #
    # Routers
    # ------------------------------------------------------------------ #
    from app.api.router import health_router, v1_router

    # Health endpoint at root level (no prefix)
    app.include_router(health_router)

    # All versioned API routes under /api/v1
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    return app


# Module-level app instance used by uvicorn
app = create_app()
