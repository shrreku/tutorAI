from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.repositories.base import BaseRepository
from app.models.notebook import (
    Notebook,
    NotebookResource,
    NotebookSession,
    NotebookProgress,
    NotebookArtifact,
)


class NotebookRepository(BaseRepository[Notebook]):
    """Repository for Notebook operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(Notebook, db)

    async def get_by_student(
        self,
        student_id: UUID,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Notebook]:
        query = select(Notebook).where(Notebook.student_id == student_id)
        if status:
            query = query.where(Notebook.status == status)
        query = query.order_by(Notebook.updated_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_by_student(
        self, student_id: UUID, status: Optional[str] = None
    ) -> int:
        query = select(Notebook.id).where(Notebook.student_id == student_id)
        if status:
            query = query.where(Notebook.status == status)
        result = await self.db.execute(query)
        return len(result.scalars().all())

    async def get_with_relations(self, notebook_id: UUID) -> Optional[Notebook]:
        result = await self.db.execute(
            select(Notebook)
            .where(Notebook.id == notebook_id)
            .options(
                selectinload(Notebook.resources),
                selectinload(Notebook.sessions),
                selectinload(Notebook.progress),
                selectinload(Notebook.artifacts),
            )
        )
        return result.scalar_one_or_none()


class NotebookResourceRepository(BaseRepository[NotebookResource]):
    """Repository for notebook-resource link operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(NotebookResource, db)

    async def get_by_notebook(self, notebook_id: UUID) -> List[NotebookResource]:
        result = await self.db.execute(
            select(NotebookResource)
            .where(NotebookResource.notebook_id == notebook_id)
            .order_by(NotebookResource.added_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_pair(
        self, notebook_id: UUID, resource_id: UUID
    ) -> Optional[NotebookResource]:
        result = await self.db.execute(
            select(NotebookResource).where(
                NotebookResource.notebook_id == notebook_id,
                NotebookResource.resource_id == resource_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_active_resource_ids(self, notebook_id: UUID) -> List[UUID]:
        result = await self.db.execute(
            select(NotebookResource.resource_id)
            .where(
                NotebookResource.notebook_id == notebook_id,
                NotebookResource.is_active.is_(True),
            )
            .order_by(NotebookResource.added_at.desc())
        )
        return [row[0] for row in result.all()]


class NotebookSessionRepository(BaseRepository[NotebookSession]):
    """Repository for notebook-session link operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(NotebookSession, db)

    async def get_by_notebook(
        self, notebook_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[NotebookSession]:
        result = await self.db.execute(
            select(NotebookSession)
            .where(NotebookSession.notebook_id == notebook_id)
            .order_by(NotebookSession.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_pair(
        self, notebook_id: UUID, session_id: UUID
    ) -> Optional[NotebookSession]:
        result = await self.db.execute(
            select(NotebookSession).where(
                NotebookSession.notebook_id == notebook_id,
                NotebookSession.session_id == session_id,
            )
        )
        return result.scalar_one_or_none()

    async def end(self, notebook_session: NotebookSession) -> NotebookSession:
        notebook_session.ended_at = datetime.now(timezone.utc)
        self.db.add(notebook_session)
        await self.db.flush()
        await self.db.refresh(notebook_session)
        return notebook_session


class NotebookProgressRepository(BaseRepository[NotebookProgress]):
    """Repository for notebook progress snapshots."""

    def __init__(self, db: AsyncSession):
        super().__init__(NotebookProgress, db)

    async def get_by_notebook(self, notebook_id: UUID) -> Optional[NotebookProgress]:
        result = await self.db.execute(
            select(NotebookProgress).where(NotebookProgress.notebook_id == notebook_id)
        )
        return result.scalar_one_or_none()


class NotebookArtifactRepository(BaseRepository[NotebookArtifact]):
    """Repository for notebook artifact persistence and retrieval."""

    def __init__(self, db: AsyncSession):
        super().__init__(NotebookArtifact, db)

    async def list_by_notebook(
        self,
        notebook_id: UUID,
        artifact_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[NotebookArtifact]:
        query = select(NotebookArtifact).where(
            NotebookArtifact.notebook_id == notebook_id
        )
        if artifact_type:
            query = query.where(NotebookArtifact.artifact_type == artifact_type)
        query = (
            query.order_by(NotebookArtifact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_by_notebook(
        self, notebook_id: UUID, artifact_type: Optional[str] = None
    ) -> int:
        query = select(NotebookArtifact.id).where(
            NotebookArtifact.notebook_id == notebook_id
        )
        if artifact_type:
            query = query.where(NotebookArtifact.artifact_type == artifact_type)
        result = await self.db.execute(query)
        return len(result.scalars().all())
