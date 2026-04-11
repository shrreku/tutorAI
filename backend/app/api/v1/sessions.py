import logging
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories.session_repo import SessionRepository
from app.models.session import UserSession, UserProfile
from app.models.notebook import NotebookSession
from app.api.deps import require_auth, verify_session_owner
from app.schemas.api import (
    SessionCreate,
    SessionResponse,
    SessionDetailResponse,
    SessionSummaryResponse,
    CurriculumOverview,
    ObjectiveSummary,
    PaginatedResponse,
    NotebookPlanningStateResponse,
)
from app.services.tutor_runtime.persistence import clear_transient_runtime_flags
from app.services.notebook_planning import NotebookPlanningStateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _canonical_turn_count(session: UserSession) -> int:
    turns = getattr(session, "turns", None)
    if turns is not None:
        return len(turns)
    plan_state = session.plan_state or {}
    return int(plan_state.get("turn_count", 0) or 0)


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
        consent_training=session.consent_training,
        current_step=ps.get("current_step"),
        current_concept_id=(ps.get("focus_concepts") or [None])[0],
        mastery=session.mastery,
        curriculum_overview=_build_curriculum_overview(ps),
        plan_state=session.plan_state,
        notebook_planning_state=_planning_state_response(ps.get("notebook_planning_state")),
        created_at=session.created_at,
    )


def _planning_state_response(payload: dict | None):
    if not payload:
        return None
    return NotebookPlanningStateResponse(**payload)


@router.post("/resource", response_model=SessionResponse)
async def create_session(
    request: SessionCreate,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Legacy resource-first session creation endpoint (decommissioned)."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Resource-first session creation has been removed. "
            "Use POST /api/v1/notebooks/{notebook_id}/sessions instead."
        ),
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get a session by ID with details."""
    await verify_session_owner(session_id, user, db)
    session_repo = SessionRepository(db)
    session = await session_repo.get_with_turns(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    planning_snapshot = await NotebookPlanningStateService(db).sync_for_session(session.id)
    if planning_snapshot:
        session.plan_state = {
            **(session.plan_state or {}),
            "notebook_planning_state": planning_snapshot.get("notebook_planning_state"),
            "coverage_snapshot": planning_snapshot.get("coverage_snapshot") or {},
        }
        await db.commit()

    ps = session.plan_state or {}
    return SessionDetailResponse(
        id=session.id,
        user_id=session.user_id,
        resource_id=session.resource_id,
        topic=ps.get("active_topic"),
        status=session.status,
        consent_training=session.consent_training,
        current_step=ps.get("current_step"),
        current_concept_id=(ps.get("focus_concepts") or [None])[0],
        mastery=session.mastery,
        curriculum_overview=_build_curriculum_overview(ps),
        plan_state=session.plan_state,
        notebook_planning_state=_planning_state_response(ps.get("notebook_planning_state")),
        created_at=session.created_at,
        turn_count=_canonical_turn_count(session),
    )


@router.post("/{session_id}/end", response_model=SessionSummaryResponse)
async def end_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """End an active session and return summary."""
    await verify_session_owner(session_id, user, db)
    session_repo = SessionRepository(db)
    session = await session_repo.get_with_turns(session_id)

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

    # Generate summary before ending
    from app.agents.summary_agent import SummaryAgent, SummaryState
    from app.services.llm.factory import create_llm_provider
    from app.config import settings
    from sqlalchemy.orm.attributes import flag_modified

    plan = session.plan_state or {}
    clear_transient_runtime_flags(plan)
    mastery = dict(session.mastery) if session.mastery else {}
    objective_queue = plan.get("objective_queue", [])
    objective_progress = plan.get("objective_progress", {})
    turn_count = _canonical_turn_count(session)
    plan["turn_count"] = turn_count

    try:
        llm = create_llm_provider(settings, task="tutoring")
        summary_agent = SummaryAgent(llm)
        summary_state = SummaryState(
            objectives=objective_queue,
            objective_progress=objective_progress,
            mastery=mastery,
            initial_mastery={c: 0.0 for c in mastery},
            turn_count=turn_count,
            topic=plan.get("active_topic"),
        )
        summary_output = await summary_agent.run(summary_state)
        summary_data = {
            "summary_text": summary_output.summary_text,
            "concepts_strong": summary_output.concepts_strong,
            "concepts_developing": summary_output.concepts_developing,
            "concepts_to_revisit": summary_output.concepts_to_revisit,
            "objectives": [
                {
                    "objective_id": obj.get("objective_id", ""),
                    "title": obj.get("title", ""),
                    "primary_concepts": obj.get("concept_scope", {}).get("primary", []),
                    "progress": objective_progress.get(obj.get("objective_id", ""), {}),
                }
                for obj in objective_queue
            ],
            "mastery_snapshot": mastery,
            "turn_count": turn_count,
            "topic": plan.get("active_topic"),
        }
    except Exception as e:
        logger.warning(f"Summary generation failed on end_session: {e}")
        summary_data = {
            "summary_text": "Session ended. Check the report card for your progress details.",
            "concepts_strong": [c for c, v in mastery.items() if v >= 0.5],
            "concepts_developing": [c for c, v in mastery.items() if 0.15 <= v < 0.5],
            "concepts_to_revisit": [c for c, v in mastery.items() if 0 < v < 0.15],
            "objectives": [
                {
                    "objective_id": obj.get("objective_id", ""),
                    "title": obj.get("title", ""),
                    "primary_concepts": obj.get("concept_scope", {}).get("primary", []),
                    "progress": objective_progress.get(obj.get("objective_id", ""), {}),
                }
                for obj in objective_queue
            ],
            "mastery_snapshot": mastery,
            "turn_count": turn_count,
            "topic": plan.get("active_topic"),
        }

    # Store summary and mark completed
    plan["session_summary"] = summary_data
    session.plan_state = plan
    session.status = "completed"
    session.ended_at = datetime.now(timezone.utc)
    flag_modified(session, "plan_state")
    await db.execute(
        update(NotebookSession)
        .where(NotebookSession.session_id == session.id)
        .values(ended_at=datetime.now(timezone.utc))
    )
    planning_snapshot = await NotebookPlanningStateService(db).sync_for_session(session.id)
    if planning_snapshot:
        session.plan_state = {
            **(session.plan_state or {}),
            "notebook_planning_state": planning_snapshot.get("notebook_planning_state"),
            "coverage_snapshot": planning_snapshot.get("coverage_snapshot") or {},
        }
        flag_modified(session, "plan_state")
    await db.commit()
    await db.refresh(session)

    return SessionSummaryResponse(
        session_id=session.id,
        status=session.status,
        topic=plan.get("active_topic"),
        turn_count=summary_data.get("turn_count", 0),
        summary_text=summary_data.get("summary_text"),
        concepts_strong=summary_data.get("concepts_strong", []),
        concepts_developing=summary_data.get("concepts_developing", []),
        concepts_to_revisit=summary_data.get("concepts_to_revisit", []),
        objectives=summary_data.get("objectives", []),
        mastery_snapshot=summary_data.get("mastery_snapshot", {}),
        notebook_planning_state=_planning_state_response(
            (session.plan_state or {}).get("notebook_planning_state")
        ),
    )


@router.get("/{session_id}/summary", response_model=SessionSummaryResponse)
async def get_session_summary(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get the session summary for a completed session."""
    await verify_session_owner(session_id, user, db)
    session_repo = SessionRepository(db)
    session = await session_repo.get_with_turns(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    planning_snapshot = await NotebookPlanningStateService(db).sync_for_session(session.id)
    if planning_snapshot:
        plan = session.plan_state or {}
        plan = {
            **plan,
            "notebook_planning_state": planning_snapshot.get("notebook_planning_state"),
            "coverage_snapshot": planning_snapshot.get("coverage_snapshot") or {},
        }
        session.plan_state = plan
        await db.commit()

    mastery = dict(session.mastery) if session.mastery else {}
    turn_count = _canonical_turn_count(session)
    plan = session.plan_state or {}
    plan["turn_count"] = turn_count
    summary_data = plan.get("session_summary")

    if not summary_data:
        # Generate on-demand for sessions completed before this feature
        objective_queue = plan.get("objective_queue", [])
        objective_progress = plan.get("objective_progress", {})
        summary_data = {
            "summary_text": None,
            "concepts_strong": [c for c, v in mastery.items() if v >= 0.5],
            "concepts_developing": [c for c, v in mastery.items() if 0.15 <= v < 0.5],
            "concepts_to_revisit": [c for c, v in mastery.items() if 0 < v < 0.15],
            "objectives": [
                {
                    "objective_id": obj.get("objective_id", ""),
                    "title": obj.get("title", ""),
                    "primary_concepts": obj.get("concept_scope", {}).get("primary", []),
                    "progress": objective_progress.get(obj.get("objective_id", ""), {}),
                }
                for obj in objective_queue
            ],
            "mastery_snapshot": mastery,
            "turn_count": turn_count,
            "topic": plan.get("active_topic"),
        }

    return SessionSummaryResponse(
        session_id=session.id,
        status=session.status,
        topic=summary_data.get("topic") or plan.get("active_topic"),
        turn_count=summary_data.get("turn_count") or turn_count,
        summary_text=summary_data.get("summary_text"),
        concepts_strong=summary_data.get("concepts_strong", []),
        concepts_developing=summary_data.get("concepts_developing", []),
        concepts_to_revisit=summary_data.get("concepts_to_revisit", []),
        objectives=summary_data.get("objectives", []),
        mastery_snapshot=summary_data.get("mastery_snapshot", mastery),
        notebook_planning_state=_planning_state_response(plan.get("notebook_planning_state")),
    )


@router.get("", response_model=PaginatedResponse[SessionResponse])
async def list_sessions(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """List sessions for the current user."""
    session_repo = SessionRepository(db)
    sessions = await session_repo.get_by_student(user.id, status=status, limit=limit)

    return PaginatedResponse(
        items=[_session_response(s) for s in sessions],
        total=len(sessions),
        limit=limit,
        offset=offset,
    )
