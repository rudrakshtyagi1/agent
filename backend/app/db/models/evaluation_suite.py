"""Immutable report for a completed dataset execution; additive table."""
import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class EvaluationSuiteModel(Base):
    __tablename__ = 'evaluation_suites'
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_version: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    report: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
