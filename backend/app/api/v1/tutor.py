import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories.session_repo import SessionRepository, TutorTurnRepository
from app.models.session import TutorTurn
from app.schemas.api import TutorTurnRequest, TutorTurnResponse
from app.config import settings
from app.services.llm.factory import create_llm_provider
from app.services.embedding.factory import create_embedding_provider
from app.agents.policy_agent import PolicyAgent
from app.agents.tutor_agent import TutorAgent
from app.agents.evaluator_agent import EvaluatorAgent
from app.agents.safety_critic import SafetyCritic
from app.services.retrieval.service import RetrievalService
from app.services.tutor_runtime.orchestrator import TurnPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tutor", tags=["tutor"])

_DEFAULT_TUTORING_LLM = None
_DEFAULT_EVALUATION_LLM = None
_DEFAULT_EMBEDDING_PROVIDER = None


def _serialize_turn(turn: TutorTurn) -> dict:
    """Serialize TutorTurn into API-friendly payload with evidence fields."""
    return {
        "turn_id": turn.id,
        "turn_index": turn.turn_index,
        "student_message": turn.student_message,
        "tutor_response": turn.tutor_response,
        "tutor_question": turn.tutor_question,
        "pedagogical_action": turn.pedagogical_action,
        "progression_decision": turn.progression_decision,
        "current_step": turn.current_step,
        "current_step_index": turn.current_step_index,
        "latency_ms": turn.latency_ms,
        "policy_output": turn.policy_output,
        "evaluator_output": turn.evaluator_output,
        "retrieved_chunks": turn.retrieved_chunks,
        "created_at": turn.created_at,
    }


def get_turn_pipeline(
    db: AsyncSession,
    *,
    tutoring_model_override: str | None = None,
    evaluation_model_override: str | None = None,
) -> TurnPipeline:
    """Create turn pipeline with all dependencies."""
    global _DEFAULT_TUTORING_LLM
    global _DEFAULT_EVALUATION_LLM
    global _DEFAULT_EMBEDDING_PROVIDER

    if tutoring_model_override:
        tutoring_llm = create_llm_provider(
            settings,
            task="tutoring",
            model_override=tutoring_model_override,
        )
    else:
        if _DEFAULT_TUTORING_LLM is None:
            _DEFAULT_TUTORING_LLM = create_llm_provider(settings, task="tutoring")
        tutoring_llm = _DEFAULT_TUTORING_LLM

    if evaluation_model_override:
        eval_llm = create_llm_provider(
            settings,
            task="evaluation",
            model_override=evaluation_model_override,
        )
    else:
        if _DEFAULT_EVALUATION_LLM is None:
            _DEFAULT_EVALUATION_LLM = create_llm_provider(settings, task="evaluation")
        eval_llm = _DEFAULT_EVALUATION_LLM

    if _DEFAULT_EMBEDDING_PROVIDER is None:
        _DEFAULT_EMBEDDING_PROVIDER = create_embedding_provider(settings)
    embedding = _DEFAULT_EMBEDDING_PROVIDER
    
    return TurnPipeline(
        db_session=db,
        policy_agent=PolicyAgent(tutoring_llm),
        tutor_agent=TutorAgent(tutoring_llm),
        evaluator_agent=EvaluatorAgent(eval_llm),
        safety_critic=SafetyCritic(eval_llm),
        retrieval_service=RetrievalService(db, embedding),
    )


@router.post("/turn", response_model=TutorTurnResponse)
async def execute_turn(
    request: TutorTurnRequest,
    db: AsyncSession = Depends(get_db),
    x_llm_model_tutoring: str | None = Header(default=None, alias="X-LLM-Model-Tutoring"),
    x_llm_model_evaluation: str | None = Header(default=None, alias="X-LLM-Model-Evaluation"),
):
    """
    Execute one tutoring turn.
    
    This is the main endpoint for the tutoring workflow:
    1. Receives student message
    2. Runs the turn pipeline (policy → retrieval → tutor → evaluation)
    3. Updates session state
    4. Returns tutor response
    """
    # Get session
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(request.session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found",
        )
    
    if session.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session {request.session_id} is not active",
        )
    
    # Execute turn pipeline
    try:
        tutoring_override = None
        evaluation_override = None
        if settings.ALLOW_LLM_MODEL_OVERRIDE_HEADERS:
            tutoring_override = x_llm_model_tutoring
            evaluation_override = x_llm_model_evaluation

        pipeline = get_turn_pipeline(
            db,
            tutoring_model_override=tutoring_override,
            evaluation_model_override=evaluation_override,
        )
        result = await pipeline.execute_turn(
            session_id=request.session_id,
            student_message=request.message,
        )
        
        logger.info(f"Executed turn {result.turn_id} for session {request.session_id}")
        
        return TutorTurnResponse(
            turn_id=UUID(result.turn_id),
            response=result.tutor_response,
            tutor_question=result.tutor_question,
            current_step=result.current_step,
            current_step_index=result.current_step_index,
            objective_id=result.objective_id,
            objective_title=result.objective_title,
            step_transition=result.step_transition,
            mastery_update=result.mastery_delta if result.mastery_delta else None,
            evaluation=None,
            session_complete=result.session_complete,
            focus_concepts=result.focus_concepts,
            awaiting_evaluation=result.awaiting_evaluation,
        )
    except Exception as e:
        logger.error(f"Turn pipeline failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Turn pipeline error: {str(e)}",
        )


@router.get("/turns/{session_id}")
async def get_turns(
    session_id: UUID,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Get all turns for a session."""
    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    
    turn_repo = TutorTurnRepository(db)
    turns = await turn_repo.get_by_session(session_id, limit=limit)
    
    return {
        "session_id": session_id,
        "turns": [_serialize_turn(t) for t in turns],
    }
