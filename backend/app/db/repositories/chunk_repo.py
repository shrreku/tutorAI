from typing import List
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.db.repositories.base import BaseRepository


class ChunkRepository(BaseRepository[Chunk]):
    """Repository for Chunk operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(Chunk, db)

    async def get_by_resource_id(
        self,
        resource_id: UUID,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Chunk]:
        """Get all chunks for a resource."""
        result = await self.db.execute(
            select(Chunk)
            .where(Chunk.resource_id == resource_id)
            .order_by(Chunk.chunk_index)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_ids(self, chunk_ids: List[UUID]) -> List[Chunk]:
        """Get chunks by a list of IDs."""
        if not chunk_ids:
            return []
        result = await self.db.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
        return list(result.scalars().all())

    async def count_by_resource(self, resource_id: UUID) -> int:
        """Count chunks for a resource."""
        result = await self.db.execute(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.resource_id == resource_id)
        )
        return int(result.scalar_one() or 0)
