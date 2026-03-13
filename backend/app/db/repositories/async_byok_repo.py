from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.base import BaseRepository
from app.models.async_byok import AsyncByokEscrow


class AsyncByokEscrowRepository(BaseRepository[AsyncByokEscrow]):
    def __init__(self, db: AsyncSession):
        super().__init__(AsyncByokEscrow, db)

    async def expire_due(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        result = await self.db.execute(
            select(AsyncByokEscrow).where(
                AsyncByokEscrow.status == "active",
                AsyncByokEscrow.expires_at <= current,
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.status = "expired"
            row.deleted_at = current
            row.deletion_reason = row.deletion_reason or "ttl_expired"
        if rows:
            await self.db.flush()
        return len(rows)

    async def list_for_user(
        self, user_id: UUID, *, include_inactive: bool = False, limit: int = 50
    ) -> list[AsyncByokEscrow]:
        query = (
            select(AsyncByokEscrow)
            .where(AsyncByokEscrow.user_id == user_id)
            .order_by(AsyncByokEscrow.created_at.desc())
            .limit(limit)
        )
        if not include_inactive:
            query = query.where(AsyncByokEscrow.status == "active")
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_for_user(
        self, escrow_id: UUID, user_id: UUID
    ) -> AsyncByokEscrow | None:
        result = await self.db.execute(
            select(AsyncByokEscrow).where(
                AsyncByokEscrow.id == escrow_id,
                AsyncByokEscrow.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_decrypt(
        self, escrow_id: UUID, *, purpose_type: str, purpose_id: str
    ) -> AsyncByokEscrow | None:
        result = await self.db.execute(
            select(AsyncByokEscrow).where(
                AsyncByokEscrow.id == escrow_id,
                AsyncByokEscrow.purpose_type == purpose_type,
                AsyncByokEscrow.purpose_id == purpose_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_accessed(
        self, escrow: AsyncByokEscrow, *, when: datetime | None = None
    ) -> None:
        current = when or datetime.now(timezone.utc)
        escrow.last_accessed_at = current
        escrow.access_count = int(escrow.access_count or 0) + 1
        await self.db.flush()

    async def revoke(
        self, escrow: AsyncByokEscrow, *, reason: str, when: datetime | None = None
    ) -> None:
        current = when or datetime.now(timezone.utc)
        escrow.status = "revoked"
        escrow.revoked_at = current
        escrow.deleted_at = current
        escrow.deletion_reason = reason
        await self.db.flush()

    async def finalize_terminal(
        self,
        escrow: AsyncByokEscrow,
        *,
        reason: str,
        success: bool,
        when: datetime | None = None,
    ) -> None:
        current = when or datetime.now(timezone.utc)
        escrow.status = "consumed" if success else "deleted"
        escrow.deleted_at = current
        escrow.deletion_reason = reason
        await self.db.flush()
