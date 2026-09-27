"""ORM model for the test_cases table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TestCaseModel(Base):
    """Persisted representation of a test case."""

    __tablename__ = "test_cases"
    __test__ = False  # Prevent pytest from treating this model as a test suite

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(sa.String(512), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    category: Mapped[str] = mapped_column(sa.String(64), nullable=False, default="functional")
    input: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    expected_tools: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    forbidden_tools: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    expected_documents: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    expected_behavior: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    tags: Mapped[list] = mapped_column(sa.JSON, nullable=False, default=list)
    tc_metadata: Mapped[dict] = mapped_column(sa.JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
