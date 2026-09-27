"""
Database session management for AgentGuard.

Architecture notes
------------------
* Uses SQLAlchemy 2.x with full async support.
* PostgreSQL (postgresql+asyncpg) is the production target.
* SQLite (sqlite+aiosqlite) is the zero-config local-dev / test fallback.
* `init_db()` calls `create_all()` for Phase 1 convenience.
  The Base metadata structure is kept migration-compatible so Alembic can
  be introduced in a later phase without restructuring models.
* All models are imported inside `init_db()` to ensure they are registered
  in Base.metadata before `create_all()` runs.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """
    Declarative base class for all ORM models.

    All models inherit from this class.  The `metadata` attribute exposed
    here is passed to Alembic's `env.py` when migrations are introduced.
    """


def _build_engine_kwargs(database_url: str) -> dict:
    """Return engine kwargs appropriate for the database dialect."""
    if database_url.startswith("sqlite"):
        # SQLite requires connect_args and does not support pool_size/max_overflow
        return {
            "connect_args": {"check_same_thread": False},
            "echo": False,
        }
    return {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "echo": False,
    }


def create_engine_from_url(database_url: str):
    """Create and return an AsyncEngine for the given URL."""
    engine_kwargs = _build_engine_kwargs(database_url)
    return create_async_engine(database_url, **engine_kwargs)


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to the given engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


# ---------------------------------------------------------------------------
# Module-level singletons — populated in main.py lifespan startup.
# ---------------------------------------------------------------------------
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str) -> None:
    """Initialise the module-level engine and session factory."""
    global _engine, _session_factory
    _engine = create_engine_from_url(database_url)
    _session_factory = create_session_factory(_engine)
    logger.info("Database engine initialised for URL scheme: %s", database_url.split(":")[0])


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session per request."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_engine() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """
    Create all database tables defined in ORM models.

    Phase 1 convenience: uses SQLAlchemy create_all().
    Migration-ready: Base.metadata is the single source of truth;
    Alembic can be pointed at it in a later phase without restructuring.
    """
    # Import all models so SQLAlchemy registers them in Base.metadata.
    import app.db.models  # noqa: F401  (side-effect import)

    if _engine is None:
        raise RuntimeError("Database not initialised. Call init_engine() first.")

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created (create_all).")


async def close_db() -> None:
    """Dispose the database engine on application shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine disposed.")
