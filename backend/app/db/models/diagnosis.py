"""Immutable per-run diagnosis cache, including no-failure reports."""
import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class DiagnosisModel(Base):
    __tablename__ = 'run_diagnoses'
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), sa.ForeignKey('runs.id'), nullable=False)
    version: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    report: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (sa.UniqueConstraint('run_id','version',name='uq_diagnosis_run_version'),)


class DiagnosisBenchmarkModel(Base):
    __tablename__ = 'diagnosis_benchmarks'
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
