"""ORM model for the evaluations table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EvaluationModel(Base):
    """Persisted evaluation result associated with a run."""

    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluator: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    dimension: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    details: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
