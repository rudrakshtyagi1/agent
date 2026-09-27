"""ORM model for the experiments table (Phase 1 scaffold, used in Phase 5+)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ExperimentModel(Base):
    """Persisted experiment definition.

    Experiments compare two or more agent configurations (A/B, hypothesis
    testing, etc.). Scaffold provided in Phase 1 for FK compatibility.
    """

    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(sa.String(512), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="draft")
    config: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
