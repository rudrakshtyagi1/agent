"""Top-level API router aggregating all v1 routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import agents, health, runs, test_cases, traces, evaluations, chaos, failures

# Root health router (mounted at /)
health_router = APIRouter()
health_router.include_router(health.router)

# v1 API router
v1_router = APIRouter()
v1_router.include_router(agents.router)
v1_router.include_router(test_cases.router)
v1_router.include_router(runs.router)

v1_router.include_router(traces.router)

v1_router.include_router(evaluations.router)

v1_router.include_router(chaos.router)

v1_router.include_router(failures.router)
