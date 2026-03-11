import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories.session_repo import SessionRepository, TutorTurnRepository
from app.db.repositories.notebook_repo import NotebookResourceRepository
from app.models.session import TutorTurn, UserProfile
from app.schemas.api import TutorTurnRequest, TutorTurnResponse
from app.config import settings
from app.api.deps import (
    require_auth,
    check_rate_limit,
    require_notebooks_enabled,
    verify_session_owner,
    verify_notebook_session_link,
    get_byok_api_key,
)
from app.services.llm.factory import create_llm_provider
from app.services.embedding.factory import create_embedding_provider
from app.agents.policy_agent import PolicyAgent
from app.agents.tutor_agent import TutorAgent
from app.agents.evaluator_agent import EvaluatorAgent
from app.agents.safety_critic import SafetyCritic
from app.services.retrieval.service import RetrievalService
from app.services.tutor_runtime.orchestrator import TurnPipeline
from app.services.credits.meter import CreditMeter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tutor", tags=["tutor"])

_DEFAULT_TUTORING_LLM = None
_DEFAULT_EVALUATION_LLM = None
_DEFAULT_EMBEDDING_PROVIDER = None


def _supports_operation_metering(db: AsyncSession, meter: object) -> bool:
    if not settings.OPERATION_METERING_ENABLED:
        return False
    if not hasattr(db, "add") or not hasattr(db, "flush"):
        return False
    return all(
        hasattr(meter, method_name)
        for method_name in ("create_operation", "append_usage_line", "finalize_operation", "release_operation")
    )


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


def _uses_platform_credits(byok: dict) -> bool:
    """Hosted credits apply only when the platform key is used."""
    return settings.CREDITS_ENABLED and not bool(byok.get("api_key"))


def get_turn_pipeline(
    db: AsyncSession,
    *,
    tutoring_model_override: str | None = None,
    evaluation_model_override: str | None = None,
    byok_api_key: str | None = None,
    byok_api_base_url: str | None = None,
) -> TurnPipeline:
    """Create turn pipeline with all dependencies.  Supports BYOK."""
    global _DEFAULT_TUTORING_LLM
    global _DEFAULT_EVALUATION_LLM
    global _DEFAULT_EMBEDDING_PROVIDER

    # When a BYOK key is provided we always create fresh, non-cached providers
    # to avoid leaking one user's key to another.
    use_byok = bool(byok_api_key)

    if tutoring_model_override or use_byok:
        tutoring_llm = create_llm_provider(
            settings,
            task="tutoring",
            model_override=tutoring_model_override,
            byok_api_key=byok_api_key,
            byok_api_base_url=byok_api_base_url,
        )
    else:
        if _DEFAULT_TUTORING_LLM is None:
            _DEFAULT_TUTORING_LLM = create_llm_provider(settings, task="tutoring")
        tutoring_llm = _DEFAULT_TUTORING_LLM

    if evaluation_model_override or use_byok:
        eval_llm = create_llm_provider(
            settings,
            task="evaluation",
            model_override=evaluation_model_override,
            byok_api_key=byok_api_key,
            byok_api_base_url=byok_api_base_url,
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
    user: UserProfile = Depends(check_rate_limit),
    byok: dict = Depends(get_byok_api_key),
    x_llm_model_tutoring: str | None = Header(default=None, alias="X-LLM-Model-Tutoring"),
    x_llm_model_evaluation: str | None = Header(default=None, alias="X-LLM-Model-Evaluation"),
):
    """Legacy non-notebook tutor turn endpoint (decommissioned)."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Legacy tutor turn path has been removed. "
            "Use POST /api/v1/tutor/notebooks/{notebook_id}/turn instead."
        ),
    )


@router.post(
    "/notebooks/{notebook_id}/turn",
    response_model=TutorTurnResponse,
    dependencies=[Depends(require_notebooks_enabled)],
)
async def execute_notebook_turn(
    notebook_id: UUID,
    request: TutorTurnRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(check_rate_limit),
    byok: dict = Depends(get_byok_api_key),
    x_llm_model_tutoring: str | None = Header(default=None, alias="X-LLM-Model-Tutoring"),
    x_llm_model_evaluation: str | None = Header(default=None, alias="X-LLM-Model-Evaluation"),
):
    """Execute one tutoring turn under notebook context."""
    # Ownership check
    await verify_session_owner(request.session_id, user, db)

    session_repo = SessionRepository(db)
    notebook_resource_repo = NotebookResourceRepository(db)

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

    await verify_notebook_session_link(notebook_id, request.session_id, user, db)
    notebook_resource_ids = await notebook_resource_repo.list_active_resource_ids(notebook_id)

    turn_id = str(uuid4())
    reserved_credits = 0
    operation_id = None
    meter = CreditMeter(db)
    uses_platform_credits = _uses_platform_credits(byok)
    supports_operation_metering = _supports_operation_metering(db, meter)

    if uses_platform_credits:
        estimated = await meter.estimate_turn_credits(
            settings.LLM_MODEL_TUTORING or settings.LLM_MODEL,
        )
        if supports_operation_metering:
            op = await meter.create_operation(
                user.id, "tutor_turn",
                session_id=str(request.session_id),
                selected_model_id=settings.LLM_MODEL_TUTORING or settings.LLM_MODEL,
            )
            operation_id = op.id
        reserved = await meter.reserve_for_turn(user.id, turn_id, estimated)
        if reserved is None:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient credits. Check your balance in Settings.",
            )
        reserved_credits = reserved
        if operation_id and hasattr(meter, "metering_repo"):
            await meter.metering_repo.update_operation_status(
                operation_id, "reserved", reserved_credits=reserved_credits,
            )

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
            byok_api_key=byok.get("api_key"),
            byok_api_base_url=byok.get("api_base_url"),
        )

        # CM-005: Snapshot LLM token counters before turn execution
        tutoring_llm = pipeline.tutor.llm
        eval_llm = pipeline.evaluator.llm
        tutor_tokens_before = dict(getattr(tutoring_llm, "total_tokens_used", None) or {"prompt_tokens": 0, "completion_tokens": 0})
        eval_tokens_before = dict(getattr(eval_llm, "total_tokens_used", None) or {"prompt_tokens": 0, "completion_tokens": 0})

        result = await pipeline.execute_turn(
            session_id=request.session_id,
            student_message=request.message,
            notebook_context={
                "notebook_id": str(notebook_id),
                "resource_ids": [str(resource_id) for resource_id in notebook_resource_ids],
            },
        )

        if uses_platform_credits:
            model_id = settings.LLM_MODEL_TUTORING or settings.LLM_MODEL

            # CM-005: Compute actual token deltas from LLM providers
            tutor_tokens_after = dict(getattr(tutoring_llm, "total_tokens_used", None) or {"prompt_tokens": 0, "completion_tokens": 0})
            eval_tokens_after = dict(getattr(eval_llm, "total_tokens_used", None) or {"prompt_tokens": 0, "completion_tokens": 0})
            tutor_prompt_delta = tutor_tokens_after.get("prompt_tokens", 0) - tutor_tokens_before.get("prompt_tokens", 0)
            tutor_completion_delta = tutor_tokens_after.get("completion_tokens", 0) - tutor_tokens_before.get("completion_tokens", 0)
            eval_prompt_delta = eval_tokens_after.get("prompt_tokens", 0) - eval_tokens_before.get("prompt_tokens", 0)
            eval_completion_delta = eval_tokens_after.get("completion_tokens", 0) - eval_tokens_before.get("completion_tokens", 0)

            prompt_tokens = tutor_prompt_delta + eval_prompt_delta
            completion_tokens = tutor_completion_delta + eval_completion_delta

            # Fallback to estimate if providers didn't report usage
            if prompt_tokens == 0 and completion_tokens == 0:
                prompt_tokens = 800
                completion_tokens = 400

            # CM-005: Record usage lines for the turn subcalls using measured token deltas
            if operation_id and supports_operation_metering:
                eval_model = settings.LLM_MODEL_EVALUATION or model_id
                # Policy + tutor response usage (tutoring LLM)
                await meter.append_usage_line(
                    operation_id, "tutor_response", model_id,
                    input_tokens=max(0, int(tutor_prompt_delta * 0.85)),
                    output_tokens=max(0, int(tutor_completion_delta * 0.85)),
                )
                # Policy usage line (tutoring LLM)
                await meter.append_usage_line(
                    operation_id, "tutor_policy", model_id,
                    input_tokens=max(0, int(tutor_prompt_delta * 0.15)),
                    output_tokens=max(0, int(tutor_completion_delta * 0.15)),
                )
                # Evaluator usage line (evaluation LLM)
                await meter.append_usage_line(
                    operation_id, "tutor_evaluation", eval_model,
                    input_tokens=max(0, int(eval_prompt_delta * 0.7)),
                    output_tokens=max(0, int(eval_completion_delta * 0.7)),
                )
                # Safety critic usage line (evaluation LLM)
                await meter.append_usage_line(
                    operation_id, "tutor_safety", eval_model,
                    input_tokens=max(0, int(eval_prompt_delta * 0.3)),
                    output_tokens=max(0, int(eval_completion_delta * 0.3)),
                )

                # Finalize through operation-based path
                final_credits = await meter.finalize_operation(
                    user.id, operation_id, reserved_credits,
                    reference_id=turn_id, reference_type="turn",
                )
            else:
                await meter.finalize_turn(
                    user.id, turn_id, model_id,
                    prompt_tokens, completion_tokens,
                    reserved_credits,
                )
        elif byok.get("api_key"):
            logger.info("Notebook turn %s used BYOK and bypassed platform credits", turn_id)

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
            session_summary=result.session_summary,
            selected_model_id=settings.LLM_MODEL_TUTORING or settings.LLM_MODEL,
        )
    except Exception as e:
        if operation_id and supports_operation_metering:
            await meter.release_operation(user.id, operation_id, reserved_credits, reference_id=turn_id, reference_type="turn")
        else:
            await meter.release_turn(user.id, turn_id, reserved_credits)
        logger.error(f"Notebook turn pipeline failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Turn pipeline error",
        )


@router.get("/turns/{session_id}")
async def get_turns(
    session_id: UUID,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get all turns for a session."""
    await verify_session_owner(session_id, user, db)
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
