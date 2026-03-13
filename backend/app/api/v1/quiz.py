"""
Quiz API endpoints — generate quizzes from completed sessions, submit answers, get results.

Quiz state is held in-memory (per-process dict keyed by quiz_id) since quizzes are
ephemeral, short-lived interactions tied to a single page load. For persistence
across restarts, the session's plan_state stores the final results.
"""

import logging
import uuid
from typing import Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.database import get_db
from app.db.repositories.session_repo import SessionRepository
from app.models.session import UserProfile
from app.services.llm.factory import create_llm_provider
from app.config import settings
from app.api.deps import require_auth, verify_session_owner, get_byok_api_key
from app.schemas.api import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestionResponse,
    QuizAnswerRequest,
    QuizAnswerResponse,
    QuizResultsResponse,
)


def _extract_byok_key(byok: dict | None) -> str | None:
    """Extract the API key string from the BYOK dependency dict."""
    if byok and isinstance(byok, dict):
        return byok.get("api_key")
    return None


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quiz", tags=["quiz"])

# ── In-memory quiz store ──────────────────────────────────────────────
# Keyed by quiz_id → { session_id, questions (with answers), answers, ... }
_active_quizzes: Dict[str, Dict[str, Any]] = {}


def _get_quiz(quiz_id: str) -> Dict[str, Any]:
    """Retrieve an active quiz or raise 404."""
    quiz = _active_quizzes.get(quiz_id)
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz {quiz_id} not found or expired. Generate a new quiz.",
        )
    return quiz


@router.post("/generate", response_model=QuizGenerateResponse)
async def generate_quiz(
    request: QuizGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
    byok: dict = Depends(get_byok_api_key),
):
    """Generate a quiz from a completed (or active) session's mastery data."""
    byok_api_key = _extract_byok_key(byok)
    await verify_session_owner(request.session_id, user, db)
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(request.session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found",
        )

    plan = session.plan_state or {}
    mastery = dict(session.mastery) if session.mastery else {}
    objective_queue = plan.get("objective_queue", [])
    concepts = list(mastery.keys()) or [
        c
        for obj in objective_queue
        for c in obj.get("concept_scope", {}).get("primary", [])
    ]

    # Generate quiz questions via QuizAgent
    from app.agents.quiz_agent import QuizAgent, QuizGenerateState

    try:
        llm = create_llm_provider(
            settings,
            task="tutoring",
            byok_api_key=byok_api_key,
        )
        agent = QuizAgent(llm)
    except Exception:
        agent = QuizAgent(None)

    state = QuizGenerateState(
        concepts=concepts,
        mastery=mastery,
        topic=plan.get("active_topic"),
        objectives=objective_queue,
        num_questions=request.num_questions,
    )

    output = await agent.run(state)

    # Store full questions (with answers) in memory
    quiz_id = str(uuid.uuid4())[:8]
    _active_quizzes[quiz_id] = {
        "quiz_id": quiz_id,
        "session_id": str(request.session_id),
        "user_id": str(user.id),
        "topic": plan.get("active_topic"),
        "quiz_focus": output.quiz_focus,
        "questions": [q.model_dump() for q in output.questions],
        "answers": {},  # question_id → { answer, grade }
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Return questions WITHOUT correct answers
    safe_questions = [
        QuizQuestionResponse(
            question_id=q.question_id,
            question_text=q.question_text,
            question_type=q.question_type,
            options=q.options,
            concept=q.concept,
            difficulty=q.difficulty,
        )
        for q in output.questions
    ]

    return QuizGenerateResponse(
        quiz_id=quiz_id,
        session_id=request.session_id,
        topic=plan.get("active_topic"),
        quiz_focus=output.quiz_focus,
        questions=safe_questions,
        total_questions=len(safe_questions),
    )


@router.post("/answer", response_model=QuizAnswerResponse)
async def submit_answer(
    request: QuizAnswerRequest,
    user: UserProfile = Depends(require_auth),
    byok: dict = Depends(get_byok_api_key),
):
    """Submit an answer to a quiz question and get immediate feedback."""
    byok_api_key = _extract_byok_key(byok)
    quiz = _get_quiz(request.quiz_id)

    # Verify ownership
    if quiz["user_id"] != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Find the question
    question_data = None
    for q in quiz["questions"]:
        if q["question_id"] == request.question_id:
            question_data = q
            break

    if not question_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question {request.question_id} not found in quiz {request.quiz_id}",
        )

    # Check if already answered
    if request.question_id in quiz["answers"]:
        # Return the cached grade
        cached = quiz["answers"][request.question_id]
        return QuizAnswerResponse(**cached["grade"])

    # Grade the answer
    from app.agents.quiz_agent import QuizAgent, QuizQuestion, QuizGradeState

    question = QuizQuestion(**question_data)
    grade_state = QuizGradeState(question=question, student_answer=request.answer)

    try:
        llm = create_llm_provider(
            settings,
            task="tutoring",
            byok_api_key=byok_api_key,
        )
        agent = QuizAgent(llm)
    except Exception:
        agent = QuizAgent(None)

    grade_output = await agent.grade(grade_state)

    grade_data = {
        "question_id": request.question_id,
        "is_correct": grade_output.is_correct,
        "score": grade_output.score,
        "feedback": grade_output.feedback,
        "correct_answer": grade_output.correct_answer,
        "explanation": grade_output.explanation,
    }

    # Store the answer and grade
    quiz["answers"][request.question_id] = {
        "answer": request.answer,
        "grade": grade_data,
    }

    return QuizAnswerResponse(**grade_data)


@router.get("/{quiz_id}/results", response_model=QuizResultsResponse)
async def get_quiz_results(
    quiz_id: str,
    user: UserProfile = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get full quiz results after answering questions."""
    quiz = _get_quiz(quiz_id)

    if quiz["user_id"] != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    total = len(quiz["questions"])
    answers = quiz["answers"]
    answered = len(answers)
    correct = sum(1 for a in answers.values() if a["grade"]["is_correct"])
    total_score = sum(a["grade"]["score"] for a in answers.values())
    score_percent = (total_score / total * 100) if total > 0 else 0

    # Per-question breakdown
    per_question = []
    for q in quiz["questions"]:
        qid = q["question_id"]
        a = answers.get(qid)
        per_question.append(
            {
                "question_id": qid,
                "question_text": q["question_text"],
                "concept": q["concept"],
                "answered": a is not None,
                "student_answer": a["answer"] if a else None,
                "is_correct": a["grade"]["is_correct"] if a else None,
                "score": a["grade"]["score"] if a else 0,
                "correct_answer": q["correct_answer"],
                "explanation": q["explanation"],
            }
        )

    # Concept-level scores
    concept_scores: Dict[str, list] = {}
    for q in quiz["questions"]:
        concept = q["concept"]
        a = answers.get(q["question_id"])
        score = a["grade"]["score"] if a else 0.0
        concept_scores.setdefault(concept, []).append(score)

    concept_averages = {
        c: sum(scores) / len(scores) for c, scores in concept_scores.items()
    }

    summary = f"You scored {correct}/{total} ({score_percent:.0f}%). " + (
        "Great job! You've shown solid understanding."
        if score_percent >= 80
        else "Good effort! Review the explanations for questions you missed."
        if score_percent >= 50
        else "Keep practicing! Review the concepts and try again."
    )

    # Persist results to session plan_state
    try:
        session_id = quiz["session_id"]
        session_repo = SessionRepository(db)
        session = await session_repo.get_by_id(uuid.UUID(session_id))
        if session and session.plan_state is not None:
            plan = session.plan_state
            plan.setdefault("quiz_results", []).append(
                {
                    "quiz_id": quiz_id,
                    "score_percent": score_percent,
                    "correct": correct,
                    "total": total,
                    "concept_scores": concept_averages,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            session.plan_state = plan
            flag_modified(session, "plan_state")
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist quiz results: {e}")

    return QuizResultsResponse(
        quiz_id=quiz_id,
        session_id=uuid.UUID(quiz["session_id"]),
        total_questions=total,
        answered=answered,
        correct=correct,
        score_percent=round(score_percent, 1),
        per_question=per_question,
        concept_scores=concept_averages,
        summary=summary,
    )
