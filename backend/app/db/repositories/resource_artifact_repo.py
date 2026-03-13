from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.resource_artifact import ResourceArtifactState


class ResourceArtifactRepository(BaseRepository[ResourceArtifactState]):
    """Repository for internal resource/notebook preparation artifacts."""

    def __init__(self, db: AsyncSession):
        super().__init__(ResourceArtifactState, db)

    async def list_by_resource(
        self,
        resource_id: UUID,
        *,
        artifact_kind: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ResourceArtifactState]:
        query = select(ResourceArtifactState).where(
            ResourceArtifactState.resource_id == resource_id
        )
        if artifact_kind:
            query = query.where(ResourceArtifactState.artifact_kind == artifact_kind)
        query = (
            query.order_by(ResourceArtifactState.generated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_by_resource(
        self, resource_id: UUID, *, artifact_kind: Optional[str] = None
    ) -> int:
        query = select(ResourceArtifactState).where(
            ResourceArtifactState.resource_id == resource_id
        )
        if artifact_kind:
            query = query.where(ResourceArtifactState.artifact_kind == artifact_kind)
        result = await self.db.execute(query)
        return len(list(result.scalars().all()))

    async def get_for_scope(
        self,
        *,
        resource_id: Optional[UUID] = None,
        notebook_id: Optional[UUID] = None,
        scope_type: str,
        scope_key: str,
        artifact_kind: str,
    ) -> Optional[ResourceArtifactState]:
        query = select(ResourceArtifactState).where(
            ResourceArtifactState.scope_type == scope_type,
            ResourceArtifactState.scope_key == scope_key,
            ResourceArtifactState.artifact_kind == artifact_kind,
        )
        if resource_id is not None:
            query = query.where(ResourceArtifactState.resource_id == resource_id)
        if notebook_id is not None:
            query = query.where(ResourceArtifactState.notebook_id == notebook_id)
        result = await self.db.execute(
            query.order_by(ResourceArtifactState.generated_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()
