"""
Shared pytest fixtures for AgentGuard test suite.

Database strategy
-----------------
Tests use an in-memory SQLite database via aiosqlite.
The engine and session factory are created fresh for each test function
to ensure full isolation.

FastAPI client
--------------
httpx.AsyncClient with ASGITransport is used to test routes end-to-end
without a live server, using the same lifespan as the real application
but with the test database injected.
"""

from __future__ import annotations

import sys
import os

# Ensure the backend directory is on the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base, get_db
from app.db import models as _models_pkg  # noqa: F401 — ensures all models registered


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create an isolated in-memory SQLite engine per test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine) -> AsyncSession:
    """Provide a transactional AsyncSession backed by the test engine."""
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(test_engine):
    """
    Provide an httpx.AsyncClient with the FastAPI app, overriding the DB
    dependency to use the isolated test database.
    """
    from app.main import app

    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
