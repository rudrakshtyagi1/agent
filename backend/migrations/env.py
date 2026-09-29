"""Async migrations; URL comes from settings and is never logged."""

import asyncio
from alembic import context
from app.config import get_settings
from app.db.session import Base, create_engine_from_url
import app.db.models  # noqa: F401


def migrate(connection):
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_engine_from_url(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
