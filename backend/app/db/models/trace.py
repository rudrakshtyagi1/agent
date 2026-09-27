"""ORM model for the trace_spans table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TraceSpanModel(Base):
    """
    A single span in an agent execution trace.

    trace_id groups all spans belonging to one execution session (1:1 with a Run).
    parent_span_id enables hierarchical/nested span relationships.
    """

    __tablename__ = "trace_spans"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), nullable=False, index=True
    )
    parent_span_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("trace_spans.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    span_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    input: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    span_metadata: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
