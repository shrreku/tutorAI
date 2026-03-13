from __future__ import annotations

from typing import Any, Protocol

from app.schemas.agent_output import PolicyOrchestratorOutput, TutorOutput
from app.schemas.agent_state import TutorState
from app.services.retrieval.service import RetrievedChunk
from app.services.tutor_runtime.events import append_trace_event
from app.services.tutor_runtime.guardrails import (
    build_guard_override_metadata,
    is_low_evidence,
)

from app.services.tutor_runtime.step_state import build_curriculum_slice, get_step_index


class TutorAgentProtocol(Protocol):
    async def generate(self, state: TutorState) -> TutorOutput: ...


def _augment_guidance(
    planner_guidance: str | None,
    low_evidence: bool,
) -> str | None:
    """Augment planner guidance with evidence-availability context."""
    guidance = (planner_guidance or "").strip()
    if low_evidence:
        guidance = (
            f"{guidance} "
            "[Low evidence: Limited source material retrieved. Teach using the "
            "curriculum context, objective description, and your pedagogical "
            "knowledge. Stay on-topic and be helpful.]"
        ).strip()
    return guidance or None


async def generate_response(
    tutor_agent: TutorAgentProtocol,
    student_message: str,
    plan: dict[str, Any],
    policy_output: PolicyOrchestratorOutput,
    retrieved_chunks: list[RetrievedChunk],
    current_obj: dict[str, Any],
    *,
    lf: Any,
) -> TutorOutput:
    """Generate tutor response with optional tracing span."""
    step_idx = get_step_index(plan)
    evidence_chunk_ids = [
        str(c.chunk_id)
        for c in retrieved_chunks
        if getattr(c, "chunk_id", None) is not None
    ]

    low_evidence, low_evidence_reason = is_low_evidence(
        evidence_chunk_ids,
        minimum_count=1,
    )
    if low_evidence:
        append_trace_event(
            plan,
            "guard_override",
            build_guard_override_metadata(
                guard_name="low_evidence_response_guard",
                decision_requested="grounded_response",
                decision_applied="proceed_with_curriculum_context",
                reason=low_evidence_reason or "low_evidence",
                details={"evidence_count": len(evidence_chunk_ids)},
            ),
        )
        return TutorOutput(
            response_text=(
                "I want to keep this accurate. I don’t have enough grounded evidence "
                "from your uploaded material for this turn. Could you share more context "
                "or ask me to focus on a specific section so I can continue safely?"
            ),
            evidence_chunk_ids=None,
        )

    gen_meta = {
        "objective_id": current_obj.get("objective_id"),
        "step_type": plan.get("effective_step_type", plan.get("current_step")),
        "action": policy_output.pedagogical_action,
        "chunks_available": len(retrieved_chunks),
        "evidence_chunk_ids": evidence_chunk_ids,
    }
    gen_span_ctx = None
    if lf:
        gen_span_ctx = lf.start_as_current_observation(
            as_type="span", name="agent.tutor", metadata=gen_meta
        )
        gen_span_ctx.__enter__()

    try:
        tutor_state = TutorState(
            student_message=student_message,
            session_mode=str(plan.get("mode") or "learn"),
            current_step_index=step_idx,
            current_step=plan.get("current_step", "explain"),
            effective_step_type=plan.get(
                "effective_step_type",
                plan.get("current_step", "explain"),
            ),
            curriculum_slice=build_curriculum_slice(current_obj, step_idx),
            target_concepts=getattr(policy_output, "target_concepts", None) or [],
            ad_hoc_step_type=getattr(policy_output, "ad_hoc_step_type", None),
            turn_plan=(
                getattr(policy_output, "turn_plan", None).model_dump()
                if hasattr(getattr(policy_output, "turn_plan", None), "model_dump")
                else getattr(policy_output, "turn_plan", None)
            ),
            retrieved_chunks=[
                {
                    "text": c.text,
                    "chunk_id": str(c.chunk_id),
                    "pedagogy_role": getattr(c, "pedagogy_role", "explanation"),
                }
                for c in retrieved_chunks
            ],
            evidence_chunk_ids=evidence_chunk_ids,
            planner_guidance=_augment_guidance(
                getattr(policy_output, "planner_guidance", None),
                low_evidence,
            ),
            recommended_strategy=getattr(policy_output, "recommended_strategy", None),
        )
        tutor_output = await tutor_agent.generate(tutor_state)
        raw_cited_ids = getattr(tutor_output, "evidence_chunk_ids", None) or []
        allowed_ids = set(evidence_chunk_ids)
        if raw_cited_ids:
            filtered_cited_ids = [cid for cid in raw_cited_ids if cid in allowed_ids]
            if len(filtered_cited_ids) != len(raw_cited_ids):
                append_trace_event(
                    plan,
                    "guard_override",
                    build_guard_override_metadata(
                        guard_name="unsupported_citation_pruned",
                        decision_requested="use_cited_evidence",
                        decision_applied="use_retrieved_subset_only",
                        reason="cited_ids_not_in_retrieved_chunks",
                        details={
                            "cited_count": len(raw_cited_ids),
                            "kept_count": len(filtered_cited_ids),
                            "retrieved_count": len(evidence_chunk_ids),
                        },
                    ),
                )
            tutor_output.evidence_chunk_ids = filtered_cited_ids or None
        else:
            tutor_output.evidence_chunk_ids = evidence_chunk_ids or None
    finally:
        if gen_span_ctx:
            gen_span_ctx.__exit__(None, None, None)

    return tutor_output
