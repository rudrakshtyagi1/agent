"""Saved chaos report; additive schema, existing databases remain usable."""
import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class ChaosCampaignModel(Base):
    __tablename__ = 'chaos_campaigns'
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    report: Mapped[dict] = mapped_column(sa.JSON, nullable=False)
