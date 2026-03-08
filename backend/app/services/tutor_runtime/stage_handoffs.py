from __future__ import annotations

from app.services.tutor_runtime.policy_runner import run_policy
from app.services.tutor_runtime.response_runner import generate_response
from app.services.tutor_runtime.retrieval_runner import retrieve_knowledge
from app.services.tutor_runtime.step_state import (
    compute_effective_step_type,
    update_objective_progress,
)
from app.services.tutor_runtime.types import (
    PolicyStageResult,
    ResponseStageResult,
    RetrievalStageResult,
    StageContext,
)


def apply_evaluation_plan_updates(
    plan: dict,
    current_obj: dict,
    evaluation_result,
) -> None:
    """Apply evaluation-derived plan mutations from orchestrator only."""
    update_objective_progress(plan, current_obj, evaluation_result)
    plan["awaiting_evaluation"] = False
    plan["awaiting_turn_id"] = None


async def run_policy_stage(
    policy_agent,
    stage_ctx: StageContext,
    evaluation_result,
    recent_turns,
    *,
    max_ad_hoc_default: int,
    lf,
) -> PolicyStageResult:
    policy_output, policy_metadata = await run_policy(
        policy_agent,
        stage_ctx.plan,
        stage_ctx.student_message,
        stage_ctx.focus_concepts,
        stage_ctx.mastery_snapshot,
        evaluation_result,
        stage_ctx.current_objective,
        recent_turns,
        max_ad_hoc_default=max_ad_hoc_default,
        lf=lf,
    )
    canonical_step = stage_ctx.plan.get("current_step", "explain")
    effective_step_type = compute_effective_step_type(
        canonical_step,
        policy_output=policy_output,
    )
    target_concepts = policy_output.target_concepts or stage_ctx.focus_concepts[:3]
    return PolicyStageResult(
        policy_output=policy_output,
        effective_step_type=effective_step_type,
        target_concepts=target_concepts,
        policy_metadata=policy_metadata,
    )


async def run_retrieval_stage(
    retriever,
    stage_ctx: StageContext,
    target_concepts: list[str],
    *,
    policy_output=None,
    lf,
) -> RetrievalStageResult:
    roadmap = stage_ctx.current_objective.get("step_roadmap") or []
    step_idx = int(stage_ctx.step_index or 0)
    current_step = roadmap[step_idx] if 0 <= step_idx < len(roadmap) else {}
    try:
        retrieved_chunks = await retrieve_knowledge(
            retriever,
            stage_ctx.session,
            stage_ctx.plan,
            stage_ctx.student_message,
            target_concepts,
            current_step.get("type") or stage_ctx.plan.get("effective_step_type"),
            current_step.get("goal"),
            objective_title=stage_ctx.current_objective.get("title"),
            objective_description=stage_ctx.current_objective.get("description"),
            policy_output=policy_output,
            notebook_id=stage_ctx.notebook_id,
            notebook_resource_ids=stage_ctx.notebook_resource_ids,
            lf=lf,
        )
    except TypeError:
        retrieved_chunks = await retrieve_knowledge(
            retriever,
            stage_ctx.session,
            stage_ctx.student_message,
            target_concepts,
            current_step.get("type") or stage_ctx.plan.get("effective_step_type"),
            current_step.get("goal"),
            objective_title=stage_ctx.current_objective.get("title"),
            objective_description=stage_ctx.current_objective.get("description"),
            policy_output=policy_output,
            lf=lf,
        )
    evidence_chunk_ids = [
        str(chunk.chunk_id)
        for chunk in retrieved_chunks
        if getattr(chunk, "chunk_id", None) is not None
    ]
    return RetrievalStageResult(
        retrieved_chunks=retrieved_chunks,
        evidence_chunk_ids=evidence_chunk_ids,
    )


async def run_response_stage(
    tutor_agent,
    stage_ctx: StageContext,
    policy_output,
    retrieved_chunks,
    *,
    lf,
) -> ResponseStageResult:
    tutor_output = await generate_response(
        tutor_agent,
        stage_ctx.student_message,
        stage_ctx.plan,
        policy_output,
        retrieved_chunks,
        stage_ctx.current_objective,
        lf=lf,
    )
    return ResponseStageResult(tutor_output=tutor_output)
