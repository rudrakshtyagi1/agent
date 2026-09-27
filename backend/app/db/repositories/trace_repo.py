"""TraceSpan repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trace import TraceSpanModel
from app.db.repositories.base import BaseRepository


class TraceSpanRepository(BaseRepository[TraceSpanModel]):
    """Data-access methods for execution trace spans."""

    model = TraceSpanModel

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_run(self, run_id: uuid.UUID) -> list[TraceSpanModel]:
        """Return all spans for a given run, ordered by started_at."""
        stmt = (
            select(TraceSpanModel)
            .where(TraceSpanModel.run_id == run_id)
            .order_by(TraceSpanModel.started_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_trace(self, trace_id: uuid.UUID) -> list[TraceSpanModel]:
        """Return all spans for a trace, ordered by started_at."""
        stmt = (
            select(TraceSpanModel)
            .where(TraceSpanModel.trace_id == trace_id)
            .order_by(TraceSpanModel.started_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_children(self, parent_span_id: uuid.UUID) -> list[TraceSpanModel]:
        """Return direct child spans of the given parent span."""
        stmt = select(TraceSpanModel).where(
            TraceSpanModel.parent_span_id == parent_span_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
