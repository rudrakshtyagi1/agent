"""Evaluation repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.evaluation import EvaluationModel
from app.db.repositories.base import BaseRepository


class EvaluationRepository(BaseRepository[EvaluationModel]):
    """Data-access methods for evaluation results."""

    model = EvaluationModel

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_run(self, run_id: uuid.UUID) -> list[EvaluationModel]:
        """Return all evaluations for a given run."""
        stmt = (
            select(EvaluationModel)
            .where(EvaluationModel.run_id == run_id)
            .order_by(EvaluationModel.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
