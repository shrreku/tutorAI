import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.curriculum_agent import CurriculumAgent
from app.api.deps import require_auth, require_notebooks_enabled, verify_notebook_owner
from app.config import settings
from app.db.database import get_db
from app.db.repositories.notebook_repo import (
    NotebookRepository,
    NotebookResourceRepository,
    NotebookSessionRepository,
    NotebookProgressRepository,
    NotebookArtifactRepository,
)
from app.db.repositories.resource_repo import ResourceRepository
from app.db.repositories.session_repo import (
    SessionRepository,
    UserProfileRepository,
    TutorTurnRepository,
)
from app.models.notebook import (
    Notebook,
    NotebookResource,
    NotebookSession,
    NotebookProgress,
    NotebookArtifact,
)
from app.models.session import UserProfile, UserSession
from app.schemas.api import (
    NotebookCreate,
    NotebookUpdate,
    NotebookResponse,
    NotebookResourceAttachRequest,
    NotebookResourceResponse,
    NotebookSessionCreateRequest,
    NotebookSessionResponse,
    NotebookSessionDetailResponse,
    NotebookProgressResponse,
    NotebookArtifactGenerateRequest,
    NotebookArtifactResponse,
    PaginatedResponse,
    SessionResponse,
    CurriculumOverview,
    ObjectiveSummary,
)
from app.services.llm.factory import create_llm_provider
from app.services.telemetry.notebook_events import emit_notebook_event
from app.services.tutor.session_service import SessionService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/notebooks",
    tags=["notebooks"],
    dependencies=[Depends(require_notebooks_enabled)],
)

SUPPORTED_ARTIFACT_TYPES = {"notes", "flashcards", "quiz", "revision_plan"}


def _build_curriculum_overview(plan_state: dict) -> Optional[CurriculumOverview]:
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


def _to_notebook_response(notebook: Notebook) -> NotebookResponse:
    return NotebookResponse(
        id=notebook.id,
        student_id=notebook.student_id,
        title=notebook.title,
        goal=notebook.goal,
        target_date=notebook.target_date,
        status=notebook.status,
        settings_json=notebook.settings_json,
        created_at=notebook.created_at,
        updated_at=notebook.updated_at,
    )


def _to_notebook_resource_response(link: NotebookResource) -> NotebookResourceResponse:
    return NotebookResourceResponse(
        id=link.id,
        notebook_id=link.notebook_id,
        resource_id=link.resource_id,
        role=link.role,
        is_active=link.is_active,
        added_at=link.added_at,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _to_notebook_session_response(link: NotebookSession) -> NotebookSessionResponse:
    return NotebookSessionResponse(
        id=link.id,
        notebook_id=link.notebook_id,
        session_id=link.session_id,
        mode=link.mode,
        started_at=link.started_at,
        ended_at=link.ended_at,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _to_session_response(session: UserSession) -> SessionResponse:
    plan_state = session.plan_state or {}
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        resource_id=session.resource_id,
        topic=plan_state.get("active_topic"),
        status=session.status,
        consent_training=session.consent_training,
        current_step=plan_state.get("current_step"),
        current_concept_id=(plan_state.get("focus_concepts") or [None])[0],
        mastery=session.mastery,
        curriculum_overview=_build_curriculum_overview(plan_state),
        created_at=session.created_at,
    )


def _to_notebook_artifact_response(artifact: NotebookArtifact) -> NotebookArtifactResponse:
    return NotebookArtifactResponse(
        id=artifact.id,
        notebook_id=artifact.notebook_id,
        artifact_type=artifact.artifact_type,
        payload_json=artifact.payload_json,
        source_session_ids=[str(sid) for sid in (artifact.source_session_ids or [])],
        source_resource_ids=[str(rid) for rid in (artifact.source_resource_ids or [])],
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


async def _compute_and_persist_notebook_progress(
    notebook_id: UUID,
    db: AsyncSession,
) -> NotebookProgressResponse:
    notebook_session_repo = NotebookSessionRepository(db)
    session_repo = SessionRepository(db)
    progress_repo = NotebookProgressRepository(db)

    links = await notebook_session_repo.get_by_notebook(notebook_id, limit=1000, offset=0)

    sessions_count = len(links)
    completed_sessions_count = 0
    mastery_accumulator: dict[str, float] = {}
    mastery_counts: dict[str, int] = {}
    objective_progress: dict[str, dict] = {}

    for link in links:
        session = await session_repo.get_by_id(link.session_id)
        if not session:
            continue

        if session.status == "completed":
            completed_sessions_count += 1

        for concept, score in (session.mastery or {}).items():
            try:
                numeric_score = float(score)
            except (TypeError, ValueError):
                continue
            mastery_accumulator[concept] = mastery_accumulator.get(concept, 0.0) + numeric_score
            mastery_counts[concept] = mastery_counts.get(concept, 0) + 1

        session_objective_progress = (session.plan_state or {}).get("objective_progress", {})
        for objective_id, progress in session_objective_progress.items():
            if objective_id not in objective_progress:
                objective_progress[objective_id] = {
                    "attempts": 0,
                    "correct": 0,
                    "steps_completed": 0,
                    "steps_skipped": 0,
                }
            objective_progress[objective_id]["attempts"] += int(progress.get("attempts", 0) or 0)
            objective_progress[objective_id]["correct"] += int(progress.get("correct", 0) or 0)
            objective_progress[objective_id]["steps_completed"] += int(progress.get("steps_completed", 0) or 0)
            objective_progress[objective_id]["steps_skipped"] += int(progress.get("steps_skipped", 0) or 0)

    mastery_snapshot = {
        concept: (mastery_accumulator[concept] / mastery_counts[concept])
        for concept in mastery_accumulator
        if mastery_counts.get(concept, 0) > 0
    }
    weak_concepts_snapshot = [
        concept
        for concept, score in mastery_snapshot.items()
        if score < 0.4
    ]

    progress = await progress_repo.get_by_notebook(notebook_id)
    if not progress:
        progress = NotebookProgress(
            notebook_id=notebook_id,
            mastery_snapshot=mastery_snapshot,
            objective_progress_snapshot=objective_progress,
            weak_concepts_snapshot=weak_concepts_snapshot,
        )
        progress = await progress_repo.create(progress)
    else:
        progress.mastery_snapshot = mastery_snapshot
        progress.objective_progress_snapshot = objective_progress
        progress.weak_concepts_snapshot = weak_concepts_snapshot
        db.add(progress)

    await db.commit()
    await db.refresh(progress)

    return NotebookProgressResponse(
        notebook_id=notebook_id,
        mastery_snapshot=progress.mastery_snapshot or {},
        objective_progress_snapshot=progress.objective_progress_snapshot or {},
        weak_concepts_snapshot=progress.weak_concepts_snapshot or [],
        sessions_count=sessions_count,
        completed_sessions_count=completed_sessions_count,
        updated_at=progress.updated_at,
    )


def _build_notes_payload(sessions: list[UserSession], turns_by_session: dict[str, list]) -> dict:
    note_lines: list[str] = []
    for session in sessions[:5]:
        plan_state = session.plan_state or {}
        topic = plan_state.get("active_topic") or "General"
        turns = turns_by_session.get(str(session.id), [])
        latest_turn = turns[-1] if turns else None
        summary_line = (
            (latest_turn.tutor_response or "").strip()[:240]
            if latest_turn is not None
            else "Session completed with no turn transcript available."
        )
        note_lines.append(f"[{topic}] {summary_line}")
    return {
        "title": "Notebook Study Notes",
        "sections": note_lines,
    }


def _build_flashcards_payload(sessions: list[UserSession]) -> dict:
    concept_scores: dict[str, list[float]] = {}
    for session in sessions:
        for concept, score in (session.mastery or {}).items():
            try:
                concept_scores.setdefault(concept, []).append(float(score))
            except (TypeError, ValueError):
                continue

    cards = []
    for concept, scores in sorted(concept_scores.items(), key=lambda kv: min(kv[1]))[:12]:
        avg_score = sum(scores) / max(len(scores), 1)
        cards.append(
            {
                "front": f"Explain: {concept}",
                "back": f"Mastery trend {avg_score:.2f}. Review definitions and one worked example.",
                "mastery": round(avg_score, 3),
            }
        )
    return {
        "title": "Notebook Flashcards",
        "cards": cards,
    }


def _build_quiz_payload(sessions: list[UserSession]) -> dict:
    concept_scores: dict[str, float] = {}
    for session in sessions:
        for concept, score in (session.mastery or {}).items():
            try:
                value = float(score)
            except (TypeError, ValueError):
                continue
            concept_scores[concept] = min(concept_scores.get(concept, value), value)

    prioritized = [c for c, _ in sorted(concept_scores.items(), key=lambda kv: kv[1])][:5]
    questions = [
        {
            "question_id": f"q{i+1}",
            "question": f"Which statement best describes {concept}?",
            "question_type": "short_answer",
            "concept": concept,
        }
        for i, concept in enumerate(prioritized)
    ]
    return {
        "title": "Notebook Quiz",
        "questions": questions,
    }


def _build_revision_plan_payload(progress: NotebookProgressResponse) -> dict:
    now = datetime.now(timezone.utc)
    items = [
        {
            "concept": concept,
            "scheduled_for": (now + timedelta(days=index + 1)).date().isoformat(),
            "focus": "review + self-explanation + one practice problem",
        }
        for index, concept in enumerate(progress.weak_concepts_snapshot[:10])
    ]
    return {
        "title": "Notebook Revision Plan",
        "items": items,
    }


async def _build_artifact_payload(
    artifact_type: str,
    sessions: list[UserSession],
    turns_by_session: dict[str, list],
    progress: NotebookProgressResponse,
    options: dict,
) -> dict:
    if artifact_type == "notes":
        base_payload = _build_notes_payload(sessions, turns_by_session)
    elif artifact_type == "flashcards":
        base_payload = _build_flashcards_payload(sessions)
    elif artifact_type == "quiz":
        base_payload = _build_quiz_payload(sessions)
    elif artifact_type == "revision_plan":
        base_payload = _build_revision_plan_payload(progress)
    else:
        raise ValueError(f"Unsupported artifact_type: {artifact_type}")

    base_payload["artifact_type"] = artifact_type
    base_payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    base_payload["options"] = options or {}
    base_payload["progress_context"] = {
        "sessions_count": progress.sessions_count,
        "completed_sessions_count": progress.completed_sessions_count,
        "weak_concepts": progress.weak_concepts_snapshot,
    }
    return base_payload


@router.post("", response_model=NotebookResponse, status_code=status.HTTP_201_CREATED)
async def create_notebook(
    request: NotebookCreate,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook_repo = NotebookRepository(db)
    notebook = Notebook(
        student_id=user.id,
        title=request.title.strip(),
        goal=request.goal,
        target_date=request.target_date,
        status="active",
        settings_json=request.settings_json,
    )
    notebook = await notebook_repo.create(notebook)
    await db.commit()
    await db.refresh(notebook)
    emit_notebook_event(
        "notebook.created",
        user_id=str(user.id),
        notebook_id=str(notebook.id),
    )
    return _to_notebook_response(notebook)


@router.get("", response_model=PaginatedResponse[NotebookResponse])
async def list_notebooks(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook_repo = NotebookRepository(db)
    notebooks = await notebook_repo.get_by_student(user.id, status=status_filter, limit=limit, offset=offset)
    total = await notebook_repo.count_by_student(user.id, status=status_filter)
    return PaginatedResponse(
        items=[_to_notebook_response(n) for n in notebooks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    notebook_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook = await verify_notebook_owner(notebook_id, user, db)
    return _to_notebook_response(notebook)


@router.patch("/{notebook_id}", response_model=NotebookResponse)
async def update_notebook(
    notebook_id: UUID,
    request: NotebookUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook = await verify_notebook_owner(notebook_id, user, db)

    updates = request.model_dump(exclude_unset=True)
    if "title" in updates and updates["title"] is not None:
        updates["title"] = updates["title"].strip()

    for key, value in updates.items():
        setattr(notebook, key, value)

    db.add(notebook)
    await db.commit()
    await db.refresh(notebook)
    return _to_notebook_response(notebook)


@router.delete("/{notebook_id}", response_model=NotebookResponse)
async def archive_notebook(
    notebook_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook = await verify_notebook_owner(notebook_id, user, db)
    notebook.status = "archived"
    db.add(notebook)
    await db.commit()
    await db.refresh(notebook)
    return _to_notebook_response(notebook)


@router.post("/{notebook_id}/resources", response_model=NotebookResourceResponse, status_code=status.HTTP_201_CREATED)
async def attach_resource_to_notebook(
    notebook_id: UUID,
    request: NotebookResourceAttachRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    resource_repo = ResourceRepository(db)
    notebook_resource_repo = NotebookResourceRepository(db)

    await verify_notebook_owner(notebook_id, user, db)
    resource = await resource_repo.get_by_id(request.resource_id)
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if resource.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    existing = await notebook_resource_repo.get_by_pair(notebook_id, request.resource_id)
    if existing:
        return _to_notebook_resource_response(existing)

    link = NotebookResource(
        notebook_id=notebook_id,
        resource_id=request.resource_id,
        role=request.role,
        is_active=request.is_active,
    )
    link = await notebook_resource_repo.create(link)
    await db.commit()
    await db.refresh(link)
    return _to_notebook_resource_response(link)


@router.get("/{notebook_id}/resources", response_model=PaginatedResponse[NotebookResourceResponse])
async def list_notebook_resources(
    notebook_id: UUID,
    limit: int = 200,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook_resource_repo = NotebookResourceRepository(db)

    await verify_notebook_owner(notebook_id, user, db)
    resources = await notebook_resource_repo.get_by_notebook(notebook_id)
    sliced = resources[offset: offset + limit]
    return PaginatedResponse(
        items=[_to_notebook_resource_response(r) for r in sliced],
        total=len(resources),
        limit=limit,
        offset=offset,
    )


@router.delete("/{notebook_id}/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_resource_from_notebook(
    notebook_id: UUID,
    resource_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook_resource_repo = NotebookResourceRepository(db)

    await verify_notebook_owner(notebook_id, user, db)
    link = await notebook_resource_repo.get_by_pair(notebook_id, resource_id)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook resource not found")

    await notebook_resource_repo.delete(link.id)
    await db.commit()


@router.post("/{notebook_id}/sessions", response_model=NotebookSessionDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_notebook_session(
    notebook_id: UUID,
    request: NotebookSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook_resource_repo = NotebookResourceRepository(db)
    notebook_session_repo = NotebookSessionRepository(db)
    user_repo = UserProfileRepository(db)

    await verify_notebook_owner(notebook_id, user, db)

    notebook_resource = await notebook_resource_repo.get_by_pair(notebook_id, request.resource_id)
    if not notebook_resource:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource is not attached to this notebook",
        )

    curriculum_llm = create_llm_provider(settings, task="curriculum")
    curriculum_agent = CurriculumAgent(curriculum_llm, db)
    session_service = SessionService(db, curriculum_agent)
    global_consent, _ = await user_repo.get_global_consent(user)

    effective_consent = (
        request.consent_training
        if request.consent_training is not None
        else global_consent
    )

    try:
        session = await session_service.create_session(
            resource_id=request.resource_id,
            user_id=user.id,
            topic=request.topic,
            selected_topics=request.selected_topics,
            consent_training=effective_consent,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    existing_link = await notebook_session_repo.get_by_pair(notebook_id, session.id)
    if existing_link:
        return NotebookSessionDetailResponse(
            notebook_session=_to_notebook_session_response(existing_link),
            session=_to_session_response(session),
        )

    notebook_session = NotebookSession(
        notebook_id=notebook_id,
        session_id=session.id,
        mode=request.mode,
    )
    notebook_session = await notebook_session_repo.create(notebook_session)
    await db.commit()
    await db.refresh(notebook_session)

    emit_notebook_event(
        "notebook.session.created",
        user_id=str(user.id),
        notebook_id=str(notebook_id),
        metadata={
            "session_id": str(session.id),
            "mode": request.mode,
            "resource_id": str(request.resource_id),
        },
    )

    return NotebookSessionDetailResponse(
        notebook_session=_to_notebook_session_response(notebook_session),
        session=_to_session_response(session),
    )


@router.get("/{notebook_id}/sessions", response_model=PaginatedResponse[NotebookSessionResponse])
async def list_notebook_sessions(
    notebook_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook_session_repo = NotebookSessionRepository(db)

    await verify_notebook_owner(notebook_id, user, db)
    links = await notebook_session_repo.get_by_notebook(notebook_id, limit=limit, offset=offset)
    return PaginatedResponse(
        items=[_to_notebook_session_response(link) for link in links],
        total=len(links),
        limit=limit,
        offset=offset,
    )


@router.get("/{notebook_id}/sessions/{session_id}", response_model=NotebookSessionDetailResponse)
async def get_notebook_session(
    notebook_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    notebook_session_repo = NotebookSessionRepository(db)
    session_repo = SessionRepository(db)

    await verify_notebook_owner(notebook_id, user, db)
    link = await notebook_session_repo.get_by_pair(notebook_id, session_id)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook session not found")

    session = await session_repo.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return NotebookSessionDetailResponse(
        notebook_session=_to_notebook_session_response(link),
        session=_to_session_response(session),
    )


@router.get("/{notebook_id}/progress", response_model=NotebookProgressResponse)
async def get_notebook_progress(
    notebook_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    await verify_notebook_owner(notebook_id, user, db)
    progress = await _compute_and_persist_notebook_progress(notebook_id, db)
    emit_notebook_event(
        "notebook.progress.viewed",
        user_id=str(user.id),
        notebook_id=str(notebook_id),
        metadata={
            "sessions_count": progress.sessions_count,
            "completed_sessions_count": progress.completed_sessions_count,
        },
    )
    return progress


@router.get("/{notebook_id}/artifacts", response_model=PaginatedResponse[NotebookArtifactResponse])
async def list_notebook_artifacts(
    notebook_id: UUID,
    artifact_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    await verify_notebook_owner(notebook_id, user, db)
    artifact_repo = NotebookArtifactRepository(db)
    artifacts = await artifact_repo.list_by_notebook(
        notebook_id=notebook_id,
        artifact_type=artifact_type,
        limit=limit,
        offset=offset,
    )
    total = await artifact_repo.count_by_notebook(notebook_id=notebook_id, artifact_type=artifact_type)
    return PaginatedResponse(
        items=[_to_notebook_artifact_response(a) for a in artifacts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{notebook_id}/artifacts:generate", response_model=NotebookArtifactResponse, status_code=status.HTTP_201_CREATED)
async def generate_notebook_artifact(
    notebook_id: UUID,
    request: NotebookArtifactGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    await verify_notebook_owner(notebook_id, user, db)

    if request.artifact_type not in SUPPORTED_ARTIFACT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported artifact_type. Expected one of: {sorted(SUPPORTED_ARTIFACT_TYPES)}",
        )

    session_repo = SessionRepository(db)
    resource_repo = ResourceRepository(db)
    artifact_repo = NotebookArtifactRepository(db)
    notebook_session_repo = NotebookSessionRepository(db)
    notebook_resource_repo = NotebookResourceRepository(db)
    turn_repo = TutorTurnRepository(db)

    notebook_session_links = await notebook_session_repo.get_by_notebook(notebook_id, limit=5000, offset=0)
    notebook_session_ids = {str(link.session_id) for link in notebook_session_links}
    notebook_resource_links = await notebook_resource_repo.get_by_notebook(notebook_id)
    notebook_resource_ids = {str(link.resource_id) for link in notebook_resource_links}

    valid_session_ids: list[str] = []
    for session_id in request.source_session_ids:
        if str(session_id) not in notebook_session_ids:
            continue
        session = await session_repo.get_by_id(session_id)
        if session and session.user_id == user.id:
            valid_session_ids.append(str(session.id))

    valid_resource_ids: list[str] = []
    for resource_id in request.source_resource_ids:
        if str(resource_id) not in notebook_resource_ids:
            continue
        resource = await resource_repo.get_by_id(resource_id)
        if resource and resource.owner_user_id == user.id:
            valid_resource_ids.append(str(resource.id))

    if not valid_session_ids:
        valid_session_ids = sorted(notebook_session_ids)
    if not valid_resource_ids:
        valid_resource_ids = sorted(notebook_resource_ids)

    source_sessions: list[UserSession] = []
    turns_by_session: dict[str, list] = {}
    for session_id in valid_session_ids:
        session = await session_repo.get_by_id(UUID(session_id))
        if not session or session.user_id != user.id:
            continue
        source_sessions.append(session)
        turns_by_session[session_id] = await turn_repo.get_by_session(session.id, limit=20)

    progress = await _compute_and_persist_notebook_progress(notebook_id, db)
    payload = await _build_artifact_payload(
        artifact_type=request.artifact_type,
        sessions=source_sessions,
        turns_by_session=turns_by_session,
        progress=progress,
        options=request.options,
    )
    payload["source_counts"] = {
        "sessions": len(valid_session_ids),
        "resources": len(valid_resource_ids),
    }

    artifact = NotebookArtifact(
        notebook_id=notebook_id,
        artifact_type=request.artifact_type,
        payload_json=payload,
        source_session_ids=valid_session_ids,
        source_resource_ids=valid_resource_ids,
    )
    artifact = await artifact_repo.create(artifact)
    await db.commit()
    await db.refresh(artifact)

    emit_notebook_event(
        "notebook.artifact.generated",
        user_id=str(user.id),
        notebook_id=str(notebook_id),
        metadata={
            "artifact_id": str(artifact.id),
            "artifact_type": request.artifact_type,
            "source_sessions": len(valid_session_ids),
            "source_resources": len(valid_resource_ids),
        },
    )

    return _to_notebook_artifact_response(artifact)
