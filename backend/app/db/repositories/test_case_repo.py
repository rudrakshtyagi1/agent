"""TestCase repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.test_case import TestCaseModel
from app.db.repositories.base import BaseRepository


class TestCaseRepository(BaseRepository[TestCaseModel]):
    """Data-access methods for test cases."""

    model = TestCaseModel

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_category(self, category: str) -> list[TestCaseModel]:
        """Return all test cases for a given category."""
        stmt = select(TestCaseModel).where(TestCaseModel.category == category)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tag(self, tag: str) -> list[TestCaseModel]:
        """Return all test cases that contain a specific tag (JSON array contains)."""
        # JSON_CONTAINS / json_each is dialect-specific; use Python-side filter
        # as a portable Phase 1 fallback.
        stmt = select(TestCaseModel)
        result = await self.session.execute(stmt)
        all_cases = result.scalars().all()
        return [tc for tc in all_cases if tag in (tc.tags or [])]
