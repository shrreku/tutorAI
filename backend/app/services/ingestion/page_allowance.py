import uuid
from typing import Optional

from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.session import UserProfile


class PageAllowanceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_user_defaults(self, user: UserProfile) -> UserProfile:
        changed = False
        if user.parse_page_limit is None or int(user.parse_page_limit) <= 0:
            user.parse_page_limit = settings.INGESTION_DEFAULT_PAGE_ALLOWANCE
            changed = True
        if user.parse_page_used is None:
            user.parse_page_used = 0
            changed = True
        if user.parse_page_reserved is None:
            user.parse_page_reserved = 0
            changed = True
        if changed:
            self.db.add(user)
            await self.db.flush()
            await self.db.refresh(user)
        return user

    async def get_user(self, user_id: uuid.UUID) -> Optional[UserProfile]:
        result = await self.db.execute(
            select(UserProfile).where(UserProfile.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        return await self.ensure_user_defaults(user)

    async def reserve_pages(
        self, user_id: uuid.UUID, estimated_pages: int
    ) -> Optional[int]:
        estimated_pages = max(int(estimated_pages or 0), 0)
        user = await self.get_user(user_id)
        if user is None:
            return None
        if estimated_pages == 0:
            return 0
        remaining = self.remaining_pages_for(user)
        if remaining < estimated_pages:
            return None
        result = await self.db.execute(
            update(UserProfile)
            .where(
                UserProfile.id == user_id,
                (
                    UserProfile.parse_page_limit
                    - UserProfile.parse_page_used
                    - UserProfile.parse_page_reserved
                )
                >= estimated_pages,
            )
            .values(
                parse_page_reserved=UserProfile.parse_page_reserved + estimated_pages
            )
        )
        await self.db.flush()
        if not result.rowcount:
            return None
        return estimated_pages

    async def finalize_pages(
        self, user_id: uuid.UUID, actual_pages: int, reserved_pages: int
    ) -> int:
        actual_pages = max(int(actual_pages or 0), 0)
        reserved_pages = max(int(reserved_pages or 0), 0)
        charge_pages = max(actual_pages, reserved_pages)
        user = await self.get_user(user_id)
        if user is None:
            return charge_pages
        release_amount = min(reserved_pages, int(user.parse_page_reserved or 0))
        await self.db.execute(
            update(UserProfile)
            .where(UserProfile.id == user_id)
            .values(
                parse_page_reserved=UserProfile.parse_page_reserved - release_amount,
                parse_page_used=UserProfile.parse_page_used + charge_pages,
            )
        )
        await self.db.flush()
        return charge_pages

    async def release_pages(self, user_id: uuid.UUID, reserved_pages: int) -> None:
        reserved_pages = max(int(reserved_pages or 0), 0)
        if reserved_pages <= 0:
            return
        user = await self.get_user(user_id)
        if user is None:
            return
        release_amount = min(reserved_pages, int(user.parse_page_reserved or 0))
        if release_amount <= 0:
            return
        await self.db.execute(
            update(UserProfile)
            .where(UserProfile.id == user_id)
            .values(
                parse_page_reserved=UserProfile.parse_page_reserved - release_amount
            )
        )
        await self.db.flush()

    async def grant_pages(self, user_id: uuid.UUID, amount: int) -> UserProfile:
        amount = max(int(amount or 0), 0)
        user = await self.get_user(user_id)
        if user is None:
            raise RuntimeError("User not found")
        await self.db.execute(
            update(UserProfile)
            .where(UserProfile.id == user_id)
            .values(parse_page_limit=UserProfile.parse_page_limit + amount)
        )
        await self.db.flush()
        refreshed = await self.get_user(user_id)
        if refreshed is None:
            raise RuntimeError("User not found")
        return refreshed

    @staticmethod
    def remaining_pages_for(user: UserProfile) -> int:
        return max(
            int(user.parse_page_limit or 0)
            - int(user.parse_page_used or 0)
            - int(user.parse_page_reserved or 0),
            0,
        )
