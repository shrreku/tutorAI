from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.resource import Resource
from app.models.knowledge_base import ResourceTopicBundle, ResourceConceptStats
from app.db.repositories.base import BaseRepository


class ResourceRepository(BaseRepository[Resource]):
    """Repository for Resource operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(Resource, db)

    async def get_by_filename(self, filename: str) -> Optional[Resource]:
        """Get resource by filename."""
        result = await self.db.execute(
            select(Resource).where(Resource.filename == filename)
        )
        return result.scalar_one_or_none()

    async def list_resources(
        self,
        status: Optional[str] = None,
        owner_user_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Resource]:
        """List resources with optional status filter."""
        query = select(Resource).limit(limit).offset(offset)
        if owner_user_id is not None:
            query = query.where(Resource.owner_user_id == owner_user_id)
        if status:
            query = query.where(Resource.status == status)
        query = query.order_by(Resource.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_resource_detail(
        self,
        resource_id: UUID,
        owner_user_id: Optional[UUID] = None,
    ) -> Optional[Resource]:
        """Get resource with topic bundles and concept stats loaded."""
        query = (
            select(Resource)
            .where(Resource.id == resource_id)
            .options(
                selectinload(Resource.topic_bundles),
                selectinload(Resource.concept_stats),
            )
        )
        if owner_user_id is not None:
            query = query.where(Resource.owner_user_id == owner_user_id)
        result = await self.db.execute(
            query
        )
        return result.scalar_one_or_none()

    async def count_by_status(self, status: str) -> int:
        """Count resources by status."""
        result = await self.db.execute(
            select(func.count()).select_from(Resource).where(Resource.status == status)
        )
        return result.scalar_one()

    async def update_status(
        self, resource_id: UUID, status: str, error_message: Optional[str] = None
    ) -> Optional[Resource]:
        """Update resource status."""
        kwargs = {"status": status}
        if error_message:
            kwargs["error_message"] = error_message
        return await self.update(resource_id, **kwargs)

    async def count_uploads_since(
        self, user_id: UUID, delta: timedelta
    ) -> int:
        """Count resources uploaded by *user_id* in the last *delta* period.

        This is used for per-user daily upload quota enforcement.
        Note: Resource currently has no ``user_id`` column; we use the
        ingestion_job → resource link via session or simply count by
        uploaded_at window.  When an ``uploaded_by`` column is added, switch
        to filtering by it.
        """
        cutoff = datetime.now(timezone.utc) - delta
        result = await self.db.execute(
            select(func.count())
            .select_from(Resource)
            .where(Resource.owner_user_id == user_id)
            .where(Resource.uploaded_at >= cutoff)
        )
        return result.scalar_one()
