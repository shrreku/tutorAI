from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import IngestionJob
from app.db.repositories.base import BaseRepository


class IngestionJobRepository(BaseRepository[IngestionJob]):
    """Repository for IngestionJob operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(IngestionJob, db)

    async def get_by_resource(self, resource_id: UUID) -> Optional[IngestionJob]:
        """Get the latest ingestion job for a resource."""
        result = await self.db.execute(
            select(IngestionJob)
            .where(IngestionJob.resource_id == resource_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_pending_jobs(self, limit: int = 10) -> List[IngestionJob]:
        """Get pending jobs for processing."""
        result = await self.db.execute(
            select(IngestionJob)
            .where(IngestionJob.status == "pending")
            .order_by(IngestionJob.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())
