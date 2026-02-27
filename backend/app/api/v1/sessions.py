import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories.session_repo import SessionRepository, UserProfileRepository
from app.models.session import UserSession
from app.agents.curriculum_agent import CurriculumAgent
from app.services.llm.factory import create_llm_provider
from app.services.tutor.session_service import SessionService
from app.config import settings
from app.schemas.api import (
    SessionCreate,
    SessionResponse,
    SessionDetailResponse,
    CurriculumOverview,
    ObjectiveSummary,
    PaginatedResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _build_curriculum_overview(plan_state: dict) -> Optional[CurriculumOverview]:
    """Build a CurriculumOverview from plan_state."""
    if not plan_state or "objective_queue" not in plan_state:
        return None
    objectives = plan_state.get("objective_queue", [])
    return CurriculumOverview(
        active_topic=plan_state.get("active_topic"),
        total_objectives=len(objectives),
        objectives=[
            ObjectiveSummary(
                objective_id=obj.get("objective_id", ""),
                title=obj.get("title", ""),
                description=obj.get("description"),
                primary_concepts=obj.get("concept_scope", {}).get("primary", []),
                estimated_turns=obj.get("estimated_turns", 5),
            )
            for obj in objectives
        ],
        session_overview=plan_state.get("session_overview"),
    )


def _session_response(session: UserSession) -> SessionResponse:
    """Build a SessionResponse from a UserSession model."""
    ps = session.plan_state or {}
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        resource_id=session.resource_id,
        topic=ps.get("active_topic"),
        status=session.status,
        current_step=ps.get("current_step"),
        current_concept_id=(ps.get("focus_concepts") or [None])[0],
        mastery=session.mastery,
        curriculum_overview=_build_curriculum_overview(ps),
        created_at=session.created_at,
    )


@router.post("/resource", response_model=SessionResponse)
async def create_session(
    request: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new tutoring session bound to a resource.

    This eagerly generates the curriculum plan so the student sees
    an overview of what the session will cover before the first turn.
    """
    curriculum_llm = create_llm_provider(settings, task="curriculum")
    curriculum_agent = CurriculumAgent(curriculum_llm, db)
    session_service = SessionService(db, curriculum_agent)

    try:
        session = await session_service.create_session(
            resource_id=request.resource_id,
            topic=request.topic,
            selected_topics=request.selected_topics,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            )
        if "not ready" in msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )
    except Exception as e:
        logger.error(f"Curriculum generation failed during session creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}",
        )
    return _session_response(session)


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a session by ID with details."""
    session_repo = SessionRepository(db)
    session = await session_repo.get_with_turns(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    ps = session.plan_state or {}
    return SessionDetailResponse(
        id=session.id,
        user_id=session.user_id,
        resource_id=session.resource_id,
        topic=ps.get("active_topic"),
        status=session.status,
        current_step=ps.get("current_step"),
        current_concept_id=(ps.get("focus_concepts") or [None])[0],
        mastery=session.mastery,
        curriculum_overview=_build_curriculum_overview(ps),
        created_at=session.created_at,
        plan_state=session.plan_state,
        turn_count=len(session.turns) if session.turns else 0,
    )


@router.post("/{session_id}/end", response_model=SessionResponse)
async def end_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """End an active session."""
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    if session.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session {session_id} is not active (status: {session.status})",
        )
    
    session = await session_repo.end_session(session_id)
    return _session_response(session)


@router.get("", response_model=PaginatedResponse[SessionResponse])
async def list_sessions(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List sessions for the current user."""
    user_repo = UserProfileRepository(db)
    user = await user_repo.get_or_create_default()
    
    session_repo = SessionRepository(db)
    sessions = await session_repo.get_by_student(user.id, status=status, limit=limit)
    
    return PaginatedResponse(
        items=[_session_response(s) for s in sessions],
        total=len(sessions),
        limit=limit,
        offset=offset,
    )
