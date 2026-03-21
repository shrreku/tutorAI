import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.notebook import NotebookSession
from app.models.session import TutorTurn, UserSession
from app.agents.summary_agent import SummaryAgent, SummaryState
from app.services.tutor_runtime.state_loader import next_turn_index
from app.services.tutor_runtime.step_state import get_step_index
from app.services.tutor_runtime.types import TurnResult

logger = logging.getLogger(__name__)


TRANSIENT_PLAN_KEYS = (
    "awaiting_evaluation",
    "awaiting_turn_id",
    "last_tutor_question",
    "last_tutor_response",
    "effective_step_type",
)


def clear_transient_runtime_flags(plan: dict) -> dict:
    """Clear ephemeral runtime flags that should not survive completion."""
    for key in TRANSIENT_PLAN_KEYS:
        if key == "awaiting_evaluation":
            plan[key] = False
        else:
            plan[key] = None
    return plan


def _serialize_policy_output(
    policy_output,
    *,
    evidence_chunk_ids: Optional[list[str]] = None,
    progression_applied: Optional[str] = None,
    guard_override_labels: Optional[list[str]] = None,
    policy_metadata: Optional[dict] = None,
    step_transition: Optional[str] = None,
) -> dict:
    policy_metadata = policy_metadata or {}
    guard_labels = guard_override_labels or []
    fallback_quality_flags = sorted(
        {
            label
            for label in guard_labels
            if label
            in {
                "low_evidence_response_guard",
                "safety_block",
                "unsupported_citation_pruned",
            }
        }
    )
    return {
        "action": policy_output.pedagogical_action,
        "progression": (
            policy_output.progression_decision.value
            if hasattr(policy_output.progression_decision, "value")
            else str(policy_output.progression_decision)
        ),
        "progression_applied": progression_applied,
        "decision_requested": policy_metadata.get("decision_requested"),
        "decision_applied": policy_metadata.get("decision_applied"),
        "step_transition": step_transition,
        "objective_id": policy_metadata.get("objective_id"),
        "step_type": policy_metadata.get("step_type"),
        "reranker_enabled": policy_metadata.get("reranker_enabled", False),
        "reranker_changed": policy_metadata.get("reranker_changed", False),
        "rerank_reason": policy_metadata.get("rerank_reason"),
        "candidate_scores": policy_metadata.get("candidate_scores"),
        "confidence": getattr(policy_output, "confidence", None),
        "reasoning": getattr(policy_output, "reasoning", None),
        "student_intent": policy_metadata.get("student_intent")
        or getattr(policy_output, "student_intent", None),
        "recommended_strategy": getattr(policy_output, "recommended_strategy", None),
        "ad_hoc_step_type": getattr(policy_output, "ad_hoc_step_type", None),
        "target_concepts": getattr(policy_output, "target_concepts", None),
        "planner_guidance": getattr(policy_output, "planner_guidance", None),
        "turn_plan": (
            policy_output.turn_plan.model_dump()
            if getattr(policy_output, "turn_plan", None) is not None
            and hasattr(policy_output.turn_plan, "model_dump")
            else getattr(policy_output, "turn_plan", None)
        ),
        "guard_override_labels": guard_labels,
        "fallback_quality_flags": fallback_quality_flags,
        "delegated": bool(policy_metadata.get("delegated", False)),
        "delegation_reason": policy_metadata.get("delegation_reason"),
        "delegation_outcome": policy_metadata.get("delegation_outcome"),
        "evidence_chunk_ids": evidence_chunk_ids or None,
        "progression_contract": policy_metadata.get("progression_contract") or {},
        "retrieval_contract": policy_metadata.get("retrieval_contract") or {},
        "response_contract": policy_metadata.get("response_contract") or {},
        "study_map_delta": policy_metadata.get("study_map_delta"),
    }


def _serialize_eval_output(evaluation_result) -> Optional[dict]:
    if not evaluation_result:
        return None

    deltas_serialized = None
    if getattr(evaluation_result, "concept_deltas", None):
        deltas_serialized = {
            c: (d.model_dump() if hasattr(d, "model_dump") else d.__dict__)
            for c, d in evaluation_result.concept_deltas.items()
        }
    return {
        "score": getattr(evaluation_result, "overall_score", None),
        "label": getattr(evaluation_result, "correctness_label", None),
        "feedback": getattr(evaluation_result, "overall_feedback", None),
        "misconceptions": getattr(evaluation_result, "misconceptions", []),
        "concept_deltas": deltas_serialized,
        "confidence": getattr(evaluation_result, "confidence", None),
        "uncertainty": getattr(evaluation_result, "uncertainty", None),
        "uncertainty_hints": getattr(evaluation_result, "uncertainty_hints", []),
        "ready_to_advance": getattr(evaluation_result, "ready_to_advance", None),
        "recommended_intervention": getattr(
            evaluation_result,
            "recommended_intervention",
            None,
        ),
    }


async def persist_turn(
    db: AsyncSession,
    turn_id: str,
    session: UserSession,
    student_message: str,
    tutor_output,
    policy_output,
    evaluation_result,
    retrieved_chunks,
    evidence_chunk_ids: Optional[list[str]] = None,
    plan: Optional[dict] = None,
    latency_ms: Optional[int] = None,
    mastery_before: Optional[dict] = None,
    policy_metadata: Optional[dict] = None,
    step_transition: Optional[str] = None,
) -> None:
    """Persist a tutor turn and flush it to the DB session."""
    plan = plan or session.plan_state or {}
    focus_concepts = plan.get("focus_concepts", [])
    cited_evidence = set(evidence_chunk_ids or [])
    trace_events = plan.get("__trace_events", [])
    guard_override_labels = sorted(
        {
            event.get("guard_name")
            for event in trace_events
            if isinstance(event, dict)
            and event.get("name") == "guard_override"
            and event.get("guard_name")
        }
    )
    progression_applied = plan.get("last_decision")

    max_attempts = 3
    for attempt in range(max_attempts):
        turn_index = await next_turn_index(db, session.id)
        try:
            async with db.begin_nested():
                turn = TutorTurn(
                    id=uuid.UUID(turn_id),
                    session_id=session.id,
                    turn_index=turn_index,
                    student_message=student_message,
                    tutor_response=tutor_output.response_text,
                    tutor_question=plan.get("last_tutor_question"),
                    current_step_index=get_step_index(plan),
                    current_step=plan.get("current_step", "explain"),
                    target_concepts=focus_concepts[:5] if focus_concepts else None,
                    pedagogical_action=policy_output.pedagogical_action,
                    progression_decision=(
                        policy_output.progression_decision.value
                        if hasattr(policy_output.progression_decision, "value")
                        else None
                    ),
                    policy_output=_serialize_policy_output(
                        policy_output,
                        evidence_chunk_ids=evidence_chunk_ids,
                        progression_applied=progression_applied,
                        guard_override_labels=guard_override_labels,
                        policy_metadata=policy_metadata,
                        step_transition=step_transition,
                    ),
                    evaluator_output=_serialize_eval_output(evaluation_result),
                    retrieved_chunks=[
                        {
                            "chunk_id": str(c.chunk_id),
                            "text": c.text[:300],
                            "is_cited_evidence": str(c.chunk_id) in cited_evidence,
                            "resource_id": str(getattr(c, "resource_id", "") or "")
                            or None,
                            "sub_chunk_id": str(getattr(c, "sub_chunk_id", "") or "")
                            or None,
                        }
                        for c in retrieved_chunks
                    ],
                    mastery_before=mastery_before
                    or (dict(session.mastery) if session.mastery else None),
                    mastery_after=dict(session.mastery) if session.mastery else None,
                    latency_ms=latency_ms,
                )
                db.add(turn)
                await db.flush()
                plan["turn_count"] = turn_index + 1
            return
        except IntegrityError:
            if attempt == max_attempts - 1:
                raise


async def handle_session_complete(
    db: AsyncSession,
    session: UserSession,
    turn_id: str,
    *,
    llm_provider=None,
) -> TurnResult:
    """Finalize session state and return completion result with LLM-generated summary."""
    completed_at = datetime.now(timezone.utc)
    session.status = "completed"
    session.ended_at = completed_at
    plan = session.plan_state or {}
    clear_transient_runtime_flags(plan)
    mastery = dict(session.mastery) if session.mastery else {}
    objective_queue = plan.get("objective_queue", [])
    objective_progress = plan.get("objective_progress", {})

    # Build initial mastery (all zeros) for delta computation
    initial_mastery = {c: 0.0 for c in mastery}

    # Generate LLM summary
    summary_state = SummaryState(
        objectives=objective_queue,
        objective_progress=objective_progress,
        mastery=mastery,
        initial_mastery=initial_mastery,
        turn_count=plan.get("turn_count", 0),
        topic=plan.get("active_topic"),
    )

    summary_agent = SummaryAgent(llm_provider)
    try:
        summary_output = await summary_agent.run(summary_state)
        summary_text = summary_output.summary_text
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
            "turn_count": plan.get("turn_count", 0),
            "topic": plan.get("active_topic"),
        }
    except Exception as e:
        logger.warning(f"Summary generation failed, using fallback: {e}")
        summary_text = (
            "Great work completing this session! "
            "You've worked through all the learning objectives. "
            "Check the session report below for a detailed breakdown of your progress."
        )
        summary_data = {
            "summary_text": summary_text,
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
            "turn_count": plan.get("turn_count", 0),
            "topic": plan.get("active_topic"),
        }

    # Store summary in plan_state for later retrieval
    plan["session_summary"] = summary_data
    session.plan_state = plan
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(session, "plan_state")
    await db.execute(
        update(NotebookSession)
        .where(NotebookSession.session_id == session.id)
        .values(ended_at=completed_at)
    )
    await db.commit()

    return TurnResult(
        turn_id=turn_id,
        tutor_response=summary_text,
        tutor_question=None,
        action="summarize",
        current_step="complete",
        current_step_index=get_step_index(plan),
        concept="",
        focus_concepts=[],
        mastery=mastery,
        mastery_delta={},
        objective_progress={},
        session_complete=True,
        awaiting_evaluation=False,
        session_summary=summary_data,
    )
