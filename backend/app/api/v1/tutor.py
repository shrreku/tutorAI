import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories.session_repo import SessionRepository, TutorTurnRepository
from app.db.repositories.notebook_repo import NotebookResourceRepository
from app.models.chunk import Chunk
from app.models.session import TutorTurn, UserProfile
from app.schemas.api import TutorTurnRequest, TutorTurnResponse, CitationData
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
from app.agents.curriculum_agent import CurriculumAgent
from app.agents.policy_agent import PolicyAgent
from app.agents.tutor_agent import TutorAgent
from app.agents.evaluator_agent import EvaluatorAgent
from app.agents.safety_critic import SafetyCritic
from app.services.retrieval.service import RetrievalService
from app.services.tutor_runtime.orchestrator import TurnPipeline
from app.services.tutor_runtime.step_state import normalize_runtime_plan_state
from app.services.credits.meter import CreditMeter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tutor", tags=["tutor"])

_DEFAULT_POLICY_LLM = None
_DEFAULT_RESPONSE_LLM = None
_DEFAULT_EVALUATION_LLM = None
_DEFAULT_CURRICULUM_LLM = None
_DEFAULT_EMBEDDING_PROVIDER = None


def _supports_operation_metering(db: AsyncSession, meter: object) -> bool:
    if not settings.OPERATION_METERING_ENABLED:
        return False
    if not hasattr(db, "add") or not hasattr(db, "flush"):
        return False
    return all(
        hasattr(meter, method_name)
        for method_name in (
            "create_operation",
            "append_usage_line",
            "finalize_operation",
            "release_operation",
        )
    )


def _build_turn_citations(
    turn: TutorTurn, chunk_lookup: dict[str, Chunk] | None = None
) -> list[dict]:
    policy_output = turn.policy_output if isinstance(turn.policy_output, dict) else {}
    stored_citations = policy_output.get("citations")
    if isinstance(stored_citations, list) and stored_citations:
        return stored_citations

    retrieved_chunks = (
        turn.retrieved_chunks if isinstance(turn.retrieved_chunks, list) else []
    )
    if not retrieved_chunks:
        return []

    evidence_chunk_ids = {
        str(chunk_id)
        for chunk_id in (policy_output.get("evidence_chunk_ids") or [])
        if chunk_id
    }

    citations: list[dict] = []
    for index, item in enumerate(retrieved_chunks):
        if not isinstance(item, dict):
            continue
        chunk_id = item.get("chunk_id")
        if not chunk_id:
            continue
        chunk_id = str(chunk_id)
        is_cited = bool(item.get("is_cited_evidence"))
        if evidence_chunk_ids and chunk_id not in evidence_chunk_ids:
            continue
        if not evidence_chunk_ids and "is_cited_evidence" in item and not is_cited:
            continue

        chunk = (chunk_lookup or {}).get(chunk_id)
        snippet = item.get("text") or (chunk.text[:200] if chunk and chunk.text else "")
        citations.append(
            {
                "citation_id": f"cite-{index + 1}",
                "resource_id": str(chunk.resource_id)
                if chunk and chunk.resource_id
                else None,
                "chunk_id": chunk_id,
                "sub_chunk_id": item.get("sub_chunk_id"),
                "page_start": getattr(chunk, "page_start", None),
                "page_end": getattr(chunk, "page_end", None),
                "section_heading": getattr(chunk, "section_heading", None),
                "snippet": snippet,
                "relevance_score": 1.0 if is_cited else 0.5,
            }
        )
    return citations


def _serialize_turn(
    turn: TutorTurn, chunk_lookup: dict[str, Chunk] | None = None
) -> dict:
    """Serialize TutorTurn into API-friendly payload with evidence fields."""
    policy_output = turn.policy_output if isinstance(turn.policy_output, dict) else {}
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
        "step_transition": policy_output.get("step_transition"),
        "latency_ms": turn.latency_ms,
        "policy_output": turn.policy_output,
        "evaluator_output": turn.evaluator_output,
        "progression_contract": policy_output.get("progression_contract") or {},
        "retrieval_contract": policy_output.get("retrieval_contract") or {},
        "response_contract": policy_output.get("response_contract") or {},
        "study_map_delta": policy_output.get("study_map_delta"),
        "retrieved_chunks": turn.retrieved_chunks,
        "citations": _build_turn_citations(turn, chunk_lookup),
        "created_at": turn.created_at,
    }


def _uses_platform_credits(byok: dict) -> bool:
    """Hosted credits apply only when the platform key is used."""
    return settings.CREDITS_ENABLED and not bool(byok.get("api_key"))


def get_turn_pipeline(
    db: AsyncSession,
    *,
    policy_model_override: str | None = None,
    response_model_override: str | None = None,
    evaluation_model_override: str | None = None,
    byok_api_key: str | None = None,
    byok_api_base_url: str | None = None,
) -> TurnPipeline:
    """Create turn pipeline with all dependencies.  Supports BYOK."""
    global _DEFAULT_POLICY_LLM
    global _DEFAULT_RESPONSE_LLM
    global _DEFAULT_EVALUATION_LLM
    global _DEFAULT_CURRICULUM_LLM
    global _DEFAULT_EMBEDDING_PROVIDER

    # When a BYOK key is provided we always create fresh, non-cached providers
    # to avoid leaking one user's key to another.
    use_byok = bool(byok_api_key)

    if policy_model_override or use_byok:
        policy_llm = create_llm_provider(
            settings,
            task="tutoring",
            model_override=policy_model_override,
            byok_api_key=byok_api_key,
            byok_api_base_url=byok_api_base_url,
        )
    else:
        if _DEFAULT_POLICY_LLM is None:
            _DEFAULT_POLICY_LLM = create_llm_provider(settings, task="tutoring")
        policy_llm = _DEFAULT_POLICY_LLM

    if response_model_override or use_byok:
        response_llm = create_llm_provider(
            settings,
            task="tutoring",
            model_override=response_model_override,
            byok_api_key=byok_api_key,
            byok_api_base_url=byok_api_base_url,
        )
    else:
        if _DEFAULT_RESPONSE_LLM is None:
            _DEFAULT_RESPONSE_LLM = create_llm_provider(settings, task="tutoring")
        response_llm = _DEFAULT_RESPONSE_LLM

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

    if use_byok:
        curriculum_llm = create_llm_provider(
            settings,
            task="curriculum",
            byok_api_key=byok_api_key,
            byok_api_base_url=byok_api_base_url,
        )
    else:
        if _DEFAULT_CURRICULUM_LLM is None:
            _DEFAULT_CURRICULUM_LLM = create_llm_provider(settings, task="curriculum")
        curriculum_llm = _DEFAULT_CURRICULUM_LLM

    if _DEFAULT_EMBEDDING_PROVIDER is None:
        _DEFAULT_EMBEDDING_PROVIDER = create_embedding_provider(settings)
    embedding = _DEFAULT_EMBEDDING_PROVIDER

    return TurnPipeline(
        db_session=db,
        policy_agent=PolicyAgent(policy_llm),
        tutor_agent=TutorAgent(response_llm),
        evaluator_agent=EvaluatorAgent(eval_llm),
        safety_critic=SafetyCritic(eval_llm),
        retrieval_service=RetrievalService(db, embedding),
        curriculum_agent=CurriculumAgent(curriculum_llm, db),
    )


@router.post("/turn", response_model=TutorTurnResponse)
async def execute_turn(
    request: TutorTurnRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(check_rate_limit),
    byok: dict = Depends(get_byok_api_key),
    x_llm_model_tutoring: str | None = Header(
        default=None, alias="X-LLM-Model-Tutoring"
    ),
    x_llm_model_evaluation: str | None = Header(
        default=None, alias="X-LLM-Model-Evaluation"
    ),
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
    x_llm_model_tutoring: str | None = Header(
        default=None, alias="X-LLM-Model-Tutoring"
    ),
    x_llm_model_evaluation: str | None = Header(
        default=None, alias="X-LLM-Model-Evaluation"
    ),
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
    notebook_resource_ids = await notebook_resource_repo.list_active_resource_ids(
        notebook_id
    )

    turn_id = str(uuid4())
    reserved_credits = 0
    operation_id = None
    meter = CreditMeter(db)
    uses_platform_credits = _uses_platform_credits(byok)
    supports_operation_metering = _supports_operation_metering(db, meter)
    model_prefs = user.model_preferences or {}
    policy_model_override = model_prefs.get("policy_model_id") or model_prefs.get("tutoring_model_id")
    response_model_override = model_prefs.get("response_model_id") or model_prefs.get("tutoring_model_id")

    if uses_platform_credits:
        billing_model_id = response_model_override or settings.LLM_MODEL_TUTORING or settings.LLM_MODEL
        estimated = await meter.estimate_turn_credits(
            billing_model_id,
        )
        if supports_operation_metering:
            op = await meter.create_operation(
                user.id,
                "tutor_turn",
                session_id=str(request.session_id),
                selected_model_id=billing_model_id,
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
                operation_id,
                "reserved",
                reserved_credits=reserved_credits,
            )

    try:
        tutoring_override = None
        evaluation_override = None
        if settings.ALLOW_LLM_MODEL_OVERRIDE_HEADERS:
            tutoring_override = x_llm_model_tutoring
            evaluation_override = x_llm_model_evaluation

        pipeline = get_turn_pipeline(
            db,
            policy_model_override=tutoring_override or policy_model_override,
            response_model_override=tutoring_override or response_model_override,
            evaluation_model_override=evaluation_override,
            byok_api_key=byok.get("api_key"),
            byok_api_base_url=byok.get("api_base_url"),
        )

        # CM-005: Snapshot LLM token counters before turn execution
        policy_llm = pipeline.policy.llm
        response_llm = pipeline.tutor.llm
        eval_llm = pipeline.evaluator.llm
        tutor_tokens_before = dict(
            getattr(response_llm, "total_tokens_used", None)
            or {"prompt_tokens": 0, "completion_tokens": 0}
        )
        policy_tokens_before = dict(
            getattr(policy_llm, "total_tokens_used", None)
            or {"prompt_tokens": 0, "completion_tokens": 0}
        )
        eval_tokens_before = dict(
            getattr(eval_llm, "total_tokens_used", None)
            or {"prompt_tokens": 0, "completion_tokens": 0}
        )

        result = await pipeline.execute_turn(
            session_id=request.session_id,
            student_message=request.message,
            notebook_context={
                "notebook_id": str(notebook_id),
                "resource_ids": [
                    str(resource_id) for resource_id in notebook_resource_ids
                ],
            },
        )

        if uses_platform_credits:
            response_model_id = response_model_override or settings.LLM_MODEL_TUTORING or settings.LLM_MODEL
            policy_model_id = policy_model_override or settings.LLM_MODEL_TUTORING or settings.LLM_MODEL

            # CM-005: Compute actual token deltas from LLM providers
            tutor_tokens_after = dict(
                getattr(response_llm, "total_tokens_used", None)
                or {"prompt_tokens": 0, "completion_tokens": 0}
            )
            policy_tokens_after = dict(
                getattr(policy_llm, "total_tokens_used", None)
                or {"prompt_tokens": 0, "completion_tokens": 0}
            )
            eval_tokens_after = dict(
                getattr(eval_llm, "total_tokens_used", None)
                or {"prompt_tokens": 0, "completion_tokens": 0}
            )
            tutor_prompt_delta = tutor_tokens_after.get(
                "prompt_tokens", 0
            ) - tutor_tokens_before.get("prompt_tokens", 0)
            tutor_completion_delta = tutor_tokens_after.get(
                "completion_tokens", 0
            ) - tutor_tokens_before.get("completion_tokens", 0)
            policy_prompt_delta = policy_tokens_after.get(
                "prompt_tokens", 0
            ) - policy_tokens_before.get("prompt_tokens", 0)
            policy_completion_delta = policy_tokens_after.get(
                "completion_tokens", 0
            ) - policy_tokens_before.get("completion_tokens", 0)
            eval_prompt_delta = eval_tokens_after.get(
                "prompt_tokens", 0
            ) - eval_tokens_before.get("prompt_tokens", 0)
            eval_completion_delta = eval_tokens_after.get(
                "completion_tokens", 0
            ) - eval_tokens_before.get("completion_tokens", 0)

            prompt_tokens = tutor_prompt_delta + eval_prompt_delta
            completion_tokens = tutor_completion_delta + eval_completion_delta

            # Fallback to estimate if providers didn't report usage
            if prompt_tokens == 0 and completion_tokens == 0:
                prompt_tokens = 800
                completion_tokens = 400

            # CM-005: Record usage lines for the turn subcalls using measured token deltas
            if operation_id and supports_operation_metering:
                eval_model = settings.LLM_MODEL_EVALUATION or settings.LLM_MODEL
                # Policy + tutor response usage (tutoring LLM)
                await meter.append_usage_line(
                    operation_id,
                    "tutor_response",
                    response_model_id,
                    input_tokens=max(0, int(tutor_prompt_delta * 0.85)),
                    output_tokens=max(0, int(tutor_completion_delta * 0.85)),
                )
                # Policy usage line (tutoring LLM)
                await meter.append_usage_line(
                    operation_id,
                    "tutor_policy",
                    policy_model_id,
                    input_tokens=max(0, int(policy_prompt_delta)),
                    output_tokens=max(0, int(policy_completion_delta)),
                )
                # Evaluator usage line (evaluation LLM)
                await meter.append_usage_line(
                    operation_id,
                    "tutor_evaluation",
                    eval_model,
                    input_tokens=max(0, int(eval_prompt_delta * 0.7)),
                    output_tokens=max(0, int(eval_completion_delta * 0.7)),
                )
                # Safety critic usage line (evaluation LLM)
                await meter.append_usage_line(
                    operation_id,
                    "tutor_safety",
                    eval_model,
                    input_tokens=max(0, int(eval_prompt_delta * 0.3)),
                    output_tokens=max(0, int(eval_completion_delta * 0.3)),
                )

                # Finalize through operation-based path
                await meter.finalize_operation(
                    user.id,
                    operation_id,
                    reserved_credits,
                    reference_id=turn_id,
                    reference_type="turn",
                )
            else:
                await meter.finalize_turn(
                    user.id,
                    turn_id,
                    billing_model_id,
                    prompt_tokens,
                    completion_tokens,
                    reserved_credits,
                )
        elif byok.get("api_key"):
            logger.info(
                "Notebook turn %s used BYOK and bypassed platform credits", turn_id
            )

        return TutorTurnResponse(
            turn_id=UUID(result.turn_id),
            response=result.tutor_response,
            tutor_question=getattr(result, "tutor_question", None),
            current_step=getattr(result, "current_step", None),
            current_step_index=getattr(result, "current_step_index", 0),
            objective_id=getattr(result, "objective_id", None),
            objective_title=getattr(result, "objective_title", None),
            step_transition=getattr(result, "step_transition", None),
            mastery_update=(
                getattr(result, "mastery_delta", None)
                if getattr(result, "mastery_delta", None)
                else None
            ),
            evaluation=None,
            session_complete=result.session_complete,
            focus_concepts=result.focus_concepts,
            awaiting_evaluation=result.awaiting_evaluation,
            session_summary=getattr(result, "session_summary", None),
            progression_contract=getattr(result, "progression_contract", {}) or {},
            retrieval_contract=getattr(result, "retrieval_contract", {}) or {},
            response_contract=getattr(result, "response_contract", {}) or {},
            study_map_delta=getattr(result, "study_map_delta", None),
            study_map_snapshot=getattr(result, "study_map_snapshot", None),
            citations=[
                CitationData(**c) for c in (getattr(result, "citations", None) or [])
            ],
            selected_model_id=billing_model_id if uses_platform_credits else (response_model_override or settings.LLM_MODEL_TUTORING or settings.LLM_MODEL),
        )
    except Exception as e:
        if operation_id and supports_operation_metering:
            await meter.release_operation(
                user.id,
                operation_id,
                reserved_credits,
                reference_id=turn_id,
                reference_type="turn",
            )
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
    chunk_ids = sorted(
        {
            str(item.get("chunk_id"))
            for turn in turns
            if isinstance(turn.retrieved_chunks, list)
            for item in turn.retrieved_chunks
            if isinstance(item, dict) and item.get("chunk_id")
        }
    )
    chunk_lookup: dict[str, Chunk] = {}
    if chunk_ids:
        chunk_rows = (
            (
                await db.execute(
                    select(Chunk).where(Chunk.id.in_([UUID(cid) for cid in chunk_ids]))
                )
            )
            .scalars()
            .all()
        )
        chunk_lookup = {str(chunk.id): chunk for chunk in chunk_rows}

    serialized_turns = [_serialize_turn(t, chunk_lookup) for t in turns]

    study_map_snapshot = None
    try:
        if session.plan_state and "objective_queue" in session.plan_state:
            plan = normalize_runtime_plan_state(session.plan_state)
            study_map_snapshot = TurnPipeline._build_study_map_snapshot(
                plan, session.status == "completed"
            )
    except Exception as exc:
        logger.warning(
            "Failed to build study map snapshot for session %s: %s", session_id, exc
        )

    if serialized_turns and study_map_snapshot:
        serialized_turns[-1]["study_map_snapshot"] = study_map_snapshot

    return {
        "session_id": session_id,
        "turns": serialized_turns,
    }
