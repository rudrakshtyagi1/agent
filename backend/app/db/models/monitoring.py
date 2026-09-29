"""Separate tenant-scoped durable inbox and alert records; additive schema."""

from datetime import datetime, timezone
from uuid import uuid4
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def now():
    return datetime.now(timezone.utc)


class MonitorTrace(Base):
    __tablename__ = "monitor_traces"
    __table_args__ = (sa.UniqueConstraint("tenant", "external_id"),)
    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid4())
    )
    tenant: Mapped[str] = mapped_column(sa.String(128), index=True)
    external_id: Mapped[str] = mapped_column(sa.String(36))
    fingerprint: Mapped[str] = mapped_column(sa.String(64))
    status: Mapped[str] = mapped_column(sa.String(20), default="queued", index=True)
    payload: Mapped[dict] = mapped_column(sa.JSON)
    summary: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=now, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class MonitorTenant(Base):
    __tablename__ = "monitor_tenants"
    tenant: Mapped[str] = mapped_column(sa.String(128), primary_key=True)
    accepted: Mapped[int] = mapped_column(default=0)
    sampled_out: Mapped[int] = mapped_column(default=0)
    rejected: Mapped[int] = mapped_column(default=0)
    dropped_spans: Mapped[int] = mapped_column(default=0)


class MonitorAlert(Base):
    __tablename__ = "monitor_alerts"
    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid4())
    )
    tenant: Mapped[str] = mapped_column(sa.String(128), index=True)
    scope: Mapped[str] = mapped_column(sa.String(400), index=True)
    kind: Mapped[str] = mapped_column(sa.String(32))
    status: Mapped[str] = mapped_column(sa.String(20), default="open")
    evidence: Mapped[dict] = mapped_column(sa.JSON)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=now
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
