"""Run repository."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.run import RunModel
from app.db.repositories.base import BaseRepository


class RunRepository(BaseRepository[RunModel]):
    """Data-access methods for test runs."""

    model = RunModel

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_agent(self, agent_id: uuid.UUID) -> list[RunModel]:
        """Return all runs for a given agent."""
        stmt = select(RunModel).where(RunModel.agent_id == agent_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_test_case(self, test_case_id: uuid.UUID) -> list[RunModel]:
        """Return all runs for a given test case."""
        stmt = select(RunModel).where(RunModel.test_case_id == test_case_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_status(self, status: str) -> list[RunModel]:
        """Return all runs with a given status."""
        stmt = select(RunModel).where(RunModel.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_filtered(
        self,
        *,
        agent_id: uuid.UUID | None = None,
        test_case_id: uuid.UUID | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[RunModel]:
        """Return runs with optional multi-field filtering."""
        stmt = select(RunModel)
        if agent_id is not None:
            stmt = stmt.where(RunModel.agent_id == agent_id)
        if test_case_id is not None:
            stmt = stmt.where(RunModel.test_case_id == test_case_id)
        if status is not None:
            stmt = stmt.where(RunModel.status == status)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
