from __future__ import annotations

import logging
from typing import Any, Protocol

from app.services.retrieval.service import RetrievalResult, RetrievedChunk

logger = logging.getLogger(__name__)


class SessionWithResourceId(Protocol):
    resource_id: Any


class RetrieverProtocol(Protocol):
    async def retrieve(
        self,
        resource_id: Any,
        query: str | None = None,
        target_concepts: list[str] | None = None,
        pedagogy_roles: list[str] | None = None,
        exclude_chunk_ids: list[str] | None = None,
        top_k: int = 5,
    ) -> RetrievalResult:
        ...


def _roles_for_step(step_type: str | None) -> list[str]:
    """Return preferred pedagogy roles for a step type.

    Always includes 'explanation' as a universal fallback so retrieval
    never returns empty results due to role mismatch.
    """
    step = (step_type or "").strip().lower()
    if step in {"define", "explain", "connect", "compare_contrast", "derive"}:
        return ["definition", "theory", "explanation"]
    if step in {"worked_example"}:
        return ["example", "derivation", "explanation"]
    if step in {"probe", "practice", "assess"}:
        return ["exercise", "example", "hint", "explanation"]
    if step in {"correct", "reflect", "summarize"}:
        return ["misconception", "summary", "explanation"]
    if step in {"motivate", "activate_prior"}:
        return ["intuition", "example", "motivation", "explanation"]
    return ["explanation"]


_THIN_MESSAGES = {
    "ok", "yes", "no", "sure", "yeah", "yep", "nope", "i see",
    "got it", "thanks", "thank you", "go on", "continue", "next",
    "i don't know", "idk", "hmm", "hm", "what", "why", "how",
    "i don't understand", "confused", "help", "hint", "explain",
}


def _is_thin_message(msg: str) -> bool:
    """Return True if the student message carries little semantic content for retrieval."""
    cleaned = msg.strip().lower().rstrip(".!?")
    if cleaned in _THIN_MESSAGES:
        return True
    if len(cleaned.split()) <= 3:
        return True
    return False


def _build_retrieval_query(
    student_message: str,
    target_concepts: list[str],
    step_type: str | None,
    step_goal: str | None,
    objective_title: str | None,
    objective_description: str | None,
    policy_output: Any | None,
) -> str:
    """Build a purpose-driven retrieval query from policy and curriculum context.

    Priority order for the primary query component:
      1. retrieval_directives.query  (explicit policy directive)
      2. turn_plan.goal              (policy's goal for this turn)
      3. planner_guidance            (policy's guidance string)
      4. step_goal                   (from the step roadmap)
      5. objective_title + description (curriculum context fallback)

    The student message is appended only if it carries meaningful
    semantic content (i.e. it's not a thin acknowledgment like "ok").
    """
    parts: list[str] = []

    # --- Extract policy-driven signals ---
    retrieval_directives: dict[str, Any] = {}
    turn_plan_goal: str = ""
    planner_guidance: str = ""
    pedagogical_action: str = ""
    if policy_output is not None:
        retrieval_directives = getattr(policy_output, "retrieval_directives", None) or {}
        tp = getattr(policy_output, "turn_plan", None)
        if tp is not None:
            turn_plan_goal = (getattr(tp, "goal", "") or "").strip()
        planner_guidance = (getattr(policy_output, "planner_guidance", "") or "").strip()
        pa = getattr(policy_output, "pedagogical_action", None)
        pedagogical_action = (pa.value if hasattr(pa, "value") else str(pa or "")).strip()

    # --- 1. Explicit query from retrieval_directives ---
    directive_query = (retrieval_directives.get("query") or "").strip()
    if directive_query:
        parts.append(directive_query)

    # --- 2. Turn plan goal ---
    if turn_plan_goal and turn_plan_goal not in parts:
        parts.append(turn_plan_goal)

    # --- 3. Planner guidance ---
    if planner_guidance and planner_guidance not in parts:
        parts.append(planner_guidance)

    # --- 4. Step goal from roadmap ---
    goal = (step_goal or "").strip()
    if goal and goal not in parts:
        parts.append(f"Step goal: {goal}")

    # --- 5. Objective context (fallback when nothing better exists) ---
    if not parts:
        obj_title = (objective_title or "").strip()
        obj_desc = (objective_description or "").strip()
        if obj_title:
            parts.append(obj_title)
        if obj_desc:
            parts.append(obj_desc)

    # --- Append target concepts for embedding enrichment ---
    if target_concepts:
        parts.append(f"Target concepts: {', '.join(target_concepts[:3])}")

    # --- Append pedagogical action qualifier ---
    if pedagogical_action:
        parts.append(f"Pedagogical focus: {pedagogical_action}")

    # --- Append student message only if substantive ---
    msg = student_message.strip()
    if msg and not _is_thin_message(msg):
        parts.append(f"Student question: {msg}")

    query = "\n".join(parts) if parts else msg
    return query


async def retrieve_knowledge(
    retriever: RetrieverProtocol,
    session: SessionWithResourceId,
    plan: dict[str, Any],
    student_message: str,
    target_concepts: list[str],
    step_type: str | None,
    step_goal: str | None,
    *,
    objective_title: str | None = None,
    objective_description: str | None = None,
    policy_output: Any | None = None,
    notebook_id: str | None = None,
    notebook_resource_ids: list[str] | None = None,
    lf: Any,
) -> list[RetrievedChunk]:
    """Retrieve knowledge chunks driven by policy context, not raw student text.

    The retrieval query is built from policy directives, turn plan, step
    goals, and objective context.  The raw student message is only used
    as a supplementary signal when it contains meaningful content.
    """
    pedagogy_roles = _roles_for_step(step_type)
    if notebook_id and notebook_resource_ids:
        session_resource_id = str(session.resource_id)
        if session_resource_id not in set(notebook_resource_ids):
            raise ValueError(
                f"Session resource {session_resource_id} is outside notebook scope {notebook_id}"
            )
    recent_chunk_ids = [
        str(cid)
        for cid in (plan.get("recent_evidence_chunk_ids") or [])
        if cid
    ]
    query = _build_retrieval_query(
        student_message=student_message,
        target_concepts=target_concepts,
        step_type=step_type,
        step_goal=step_goal,
        objective_title=objective_title,
        objective_description=objective_description,
        policy_output=policy_output,
    )
    logger.debug("Retrieval query built (len=%d): %s", len(query), query[:200])

    ret_meta = {
        "target_concepts": target_concepts,
        "step_type": step_type,
        "pedagogy_roles": pedagogy_roles,
    }
    ret_span_ctx = None
    ret_span = None
    chunks = []
    if lf:
        ret_span_ctx = lf.start_as_current_observation(
            as_type="span",
            name="agent.retrieval",
            metadata=ret_meta,
            input={"query": query[:160]},
        )
        ret_span = ret_span_ctx.__enter__()

    try:
        try:
            retrieved = await retriever.retrieve(
                resource_id=session.resource_id,
                query=query,
                target_concepts=target_concepts,
                pedagogy_roles=pedagogy_roles or None,
                exclude_chunk_ids=recent_chunk_ids,
                top_k=5,
            )
        except TypeError:
            retrieved = await retriever.retrieve(
                resource_id=session.resource_id,
                query=query,
                target_concepts=target_concepts,
                top_k=5,
            )
        chunks = retrieved.chunks if hasattr(retrieved, "chunks") else []
    finally:
        if ret_span_ctx:
            if ret_span:
                ret_span.update(
                    output={
                        "evidence_count": len(chunks),
                        "retrieval_diagnostics": {
                            "retrieved_count": len(chunks),
                            "roles_requested_count": len(pedagogy_roles),
                        },
                    }
                )
            ret_span_ctx.__exit__(None, None, None)

    return chunks
