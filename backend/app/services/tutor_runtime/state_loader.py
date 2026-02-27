import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import TutorTurn, UserSession


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Optional[UserSession]:
    result = await db.execute(
        select(UserSession).where(UserSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def load_recent_turns(
    db: AsyncSession,
    session_id: uuid.UUID,
    count: int = 5,
) -> list[dict]:
    result = await db.execute(
        select(TutorTurn)
        .where(TutorTurn.session_id == session_id)
        .order_by(TutorTurn.turn_index.desc())
        .limit(count)
    )
    turns = list(result.scalars().all())
    turns.reverse()
    return [
        {
            "student_message": t.student_message,
            "tutor_response": (t.tutor_response or "")[:300],
            "pedagogical_action": t.pedagogical_action,
            "current_step": t.current_step,
        }
        for t in turns
    ]


async def next_turn_index(db: AsyncSession, session_id: uuid.UUID) -> int:
    """Return the next turn_index for a session."""
    # Serialize concurrent turn writers per session to reduce index collisions.
    await db.execute(
        select(UserSession.id)
        .where(UserSession.id == session_id)
        .with_for_update()
    )

    result = await db.execute(
        select(func.coalesce(func.max(TutorTurn.turn_index), -1))
        .where(TutorTurn.session_id == session_id)
    )
    return result.scalar_one() + 1
