from datetime import datetime, timedelta, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func
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

    async def expire_stale_active_jobs(self, max_age_minutes: int = 30) -> int:
        """Mark orphaned pending/running jobs as failed.

        This prevents historical stuck jobs (for example from disabled workers)
        from blocking new uploads via the active-job concurrency guard.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        result = await self.db.execute(
            select(IngestionJob).where(
                IngestionJob.status.in_(["pending", "running"]),
                IngestionJob.completed_at.is_(None),
                IngestionJob.created_at < cutoff,
            )
        )
        stale_jobs = list(result.scalars().all())
        if not stale_jobs:
            return 0

        for job in stale_jobs:
            job.status = "failed"
            job.error_stage = job.error_stage or "queue"
            job.error_message = (
                "Marked failed automatically because the job was stale "
                "and not picked up by a worker."
            )
            job.completed_at = datetime.now(timezone.utc)

        await self.db.flush()
        return len(stale_jobs)

    async def count_active_jobs(self, *, include_pending: bool = True) -> int:
        """Count active jobs for concurrency guarding.

        In durable-queue mode we count both ``pending`` and ``running`` jobs.
        In in-process mode, ``pending`` can represent orphaned queue-era rows,
        so callers can opt to count only ``running``.
        """
        statuses = ["running"]
        if include_pending:
            statuses.append("pending")
        result = await self.db.execute(
            select(func.count())
            .select_from(IngestionJob)
            .where(IngestionJob.status.in_(statuses))
            .where(IngestionJob.completed_at.is_(None))
        )
        return result.scalar_one()
