from typing import Optional, List
from uuid import UUID
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.session import UserSession, UserProfile, TutorTurn
from app.db.repositories.base import BaseRepository


class UserProfileRepository(BaseRepository[UserProfile]):
    """Repository for UserProfile operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(UserProfile, db)

    async def get_by_email(self, email: str) -> Optional[UserProfile]:
        """Get user by email."""
        result = await self.db.execute(
            select(UserProfile).where(UserProfile.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(self, external_id: str) -> Optional[UserProfile]:
        """Get user by external identity (JWT subject)."""
        result = await self.db.execute(
            select(UserProfile).where(UserProfile.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_default(self) -> UserProfile:
        """Get or create a default user for unauthenticated access."""
        default_email = "default@studyagent.local"
        user = await self.get_by_email(default_email)
        if not user:
            user = UserProfile(
                display_name="Default User",
                email=default_email,
                preferences={"consent_training_global": False},
            )
            user = await self.create(user)
        return user

    async def get_global_consent(self, user: UserProfile) -> tuple[bool, bool]:
        """Return (consent_value, preference_set)."""
        preferences = user.preferences or {}
        if "consent_training_global" not in preferences:
            return False, False
        return bool(preferences.get("consent_training_global")), True

    async def update_settings(
        self,
        user: UserProfile,
        *,
        consent_training_global: bool | None = None,
    ) -> UserProfile:
        """Update mutable user settings stored in preferences JSON."""
        preferences = dict(user.preferences or {})

        if consent_training_global is not None:
            preferences["consent_training_global"] = bool(consent_training_global)

        user.preferences = preferences
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user


class SessionRepository(BaseRepository[UserSession]):
    """Repository for UserSession operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(UserSession, db)

    async def get_by_student(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[UserSession]:
        """Get sessions for a user."""
        query = select(UserSession).where(UserSession.user_id == user_id)
        if status:
            query = query.where(UserSession.status == status)
        query = query.order_by(UserSession.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_with_turns(self, session_id: UUID) -> Optional[UserSession]:
        """Get session with turns loaded."""
        result = await self.db.execute(
            select(UserSession)
            .where(UserSession.id == session_id)
            .options(selectinload(UserSession.turns))
        )
        return result.scalar_one_or_none()

    async def get_active_for_resource(
        self,
        user_id: UUID,
        resource_id: UUID,
    ) -> Optional[UserSession]:
        """Get active session for a user and resource."""
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.resource_id == resource_id,
                UserSession.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def end_session(self, session_id: UUID) -> Optional[UserSession]:
        """End a session."""
        return await self.update(
            session_id,
            status="ended",
            ended_at=datetime.utcnow(),
        )


class TutorTurnRepository(BaseRepository[TutorTurn]):
    """Repository for TutorTurn operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(TutorTurn, db)

    async def get_by_session(
        self,
        session_id: UUID,
        limit: int = 100,
    ) -> List[TutorTurn]:
        """Get turns for a session."""
        result = await self.db.execute(
            select(TutorTurn)
            .where(TutorTurn.session_id == session_id)
            .order_by(TutorTurn.turn_index)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent_turns(
        self,
        session_id: UUID,
        count: int = 5,
    ) -> List[TutorTurn]:
        """Get most recent turns for context."""
        result = await self.db.execute(
            select(TutorTurn)
            .where(TutorTurn.session_id == session_id)
            .order_by(TutorTurn.turn_index.desc())
            .limit(count)
        )
        turns = list(result.scalars().all())
        turns.reverse()  # Return in chronological order
        return turns

    async def get_next_turn_index(self, session_id: UUID) -> int:
        """Get the next turn index for a session."""
        result = await self.db.execute(
            select(TutorTurn.turn_index)
            .where(TutorTurn.session_id == session_id)
            .order_by(TutorTurn.turn_index.desc())
            .limit(1)
        )
        last_index = result.scalar_one_or_none()
        return (last_index or -1) + 1
