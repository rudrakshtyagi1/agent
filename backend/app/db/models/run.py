"""ORM model for the runs table.

Design note — agent_version denormalisation
-------------------------------------------
agent_version is stored directly on the Run row.  It is copied from the
Agent record at run-creation time and is immutable thereafter.  This ensures:

* Historical runs remain attributable to the exact agent version that executed
  them even if the parent Agent record is later updated or deleted.
* Future replay and regression comparison phases can reconstruct the precise
  execution context without joining back to a potentially stale Agent row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RunModel(Base):
    """Persisted representation of a single agent test run."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Denormalised snapshot of the agent version at run creation time.
    # Immutable after creation — see docstring above.
    agent_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("test_cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="queued", index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    total_latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
