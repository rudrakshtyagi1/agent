"""ORM model for the agents table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AgentModel(Base):
    """Persisted representation of a registered agent."""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False, index=True)
    version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    endpoint: Mapped[str | None] = mapped_column(sa.String(2048), nullable=True)
    model: Mapped[str | None] = mapped_column(sa.String(256), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="active")
    agent_metadata: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Unique constraint: (name, version) — each named agent/version is distinct
    __table_args__ = (
        sa.UniqueConstraint("name", "version", name="uq_agents_name_version"),
    )
