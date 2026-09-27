"""Failure repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.failure import FailureModel
from app.db.repositories.base import BaseRepository


class FailureRepository(BaseRepository[FailureModel]):
    """Data-access methods for failure records."""

    model = FailureModel

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_run(self, run_id: uuid.UUID) -> list[FailureModel]:
        """Return all failures detected in a given run."""
        stmt = (
            select(FailureModel)
            .where(FailureModel.run_id == run_id)
            .order_by(FailureModel.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_severity(self, severity: str) -> list[FailureModel]:
        """Return all failures matching a given severity level."""
        stmt = select(FailureModel).where(FailureModel.severity == severity)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
