"""Agent repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import AgentModel
from app.db.repositories.base import BaseRepository


class AgentRepository(BaseRepository[AgentModel]):
    """Data-access methods for agents."""

    model = AgentModel

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_name_and_version(
        self, name: str, version: str
    ) -> AgentModel | None:
        """Return the agent matching the exact (name, version) pair, or None."""
        stmt = select(AgentModel).where(
            AgentModel.name == name,
            AgentModel.version == version,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_name(self, name: str) -> list[AgentModel]:
        """Return all versions of an agent by name."""
        stmt = select(AgentModel).where(AgentModel.name == name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
