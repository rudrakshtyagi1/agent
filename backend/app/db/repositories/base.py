"""Generic async repository base class.

Provides standard CRUD operations for any SQLAlchemy 2.x ORM model.
All business-logic repositories should inherit from BaseRepository and
add domain-specific query methods.
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Async-compatible generic CRUD repository."""

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, record_id: uuid.UUID) -> ModelType | None:
        """Fetch a single record by primary key. Returns None if not found."""
        result = await self.session.get(self.model, record_id)
        return result

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[ModelType]:
        """Return a paginated list of records, optionally filtered by column equality."""
        stmt = select(self.model)
        if filters:
            for column_name, value in filters.items():
                column = getattr(self.model, column_name, None)
                if column is not None and value is not None:
                    stmt = stmt.where(column == value)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelType:
        """Create and persist a new record. Returns the persisted instance."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, record_id: uuid.UUID, **kwargs: Any) -> ModelType | None:
        """Apply partial updates to an existing record. Returns None if not found."""
        instance = await self.get_by_id(record_id)
        if instance is None:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(instance, key):
                setattr(instance, key, value)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, record_id: uuid.UUID) -> bool:
        """Delete a record by primary key. Returns True if deleted, False if not found."""
        instance = await self.get_by_id(record_id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True
