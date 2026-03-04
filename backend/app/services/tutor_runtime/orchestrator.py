"""Tutor runtime orchestrator.

Objectives and step-plans are the primary working units.
Each turn is executed within the context of a current objective and its
step roadmap.
"""

import asyncio
import os
import time as _time
import uuid

from langfuse import propagate_attributes
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.agents.evaluator_agent import EvaluatorAgent
from app.agents.policy_agent import PolicyAgent
from app.agents.safety_critic import SafetyCritic
from app.agents.tutor_agent import TutorAgent
from app.models.session import UserSession
from app.services.retrieval.service import RetrievalService
from app.services.tutor_runtime.stage_handoffs import (
    apply_evaluation_plan_updates as _apply_evaluation_plan_updates,
)
from app.services.tutor_runtime.stage_handoffs import (
    run_policy_stage as _run_policy_stage_handoff,
)
from app.services.tutor_runtime.stage_handoffs import (
    run_response_stage as _run_response_stage_handoff,
)
from app.services.tutor_runtime.stage_handoffs import (
    run_retrieval_stage as _run_retrieval_stage_handoff,
)
from app.services.tracing import (
    flush_langfuse,
    get_langfuse_client,
    is_detailed_tracing_enabled,
    normalize_trace_metadata,
    redact_text_for_trace,
    should_sample_trace,
)
from app.services.tutor_runtime.events import (
    append_trace_event as _append_trace_event,
    consume_trace_events as _consume_trace_events,
    detect_question as _detect_question,
)
from app.services.tutor_runtime.delegation import (
    apply_delegation_override as _apply_delegation_override,
    decide_adaptive_delegation as _decide_adaptive_delegation,
    delegation_trace_payload as _delegation_trace_payload,
)
from app.services.tutor_runtime.evaluation_runner import (
    evaluate_response as _evaluate_response,
)
from app.services.tutor_runtime.persistence import (
    handle_session_complete as _handle_session_complete,
    persist_turn as _persist_turn,
)
from app.services.tutor_runtime.progression import apply_progression as _apply_progression
from app.services.tutor_runtime.scoring import emit_scores as _emit_scores
from app.services.tutor_runtime.telemetry_contract import (
    build_turn_telemetry_contract as _build_turn_telemetry_contract,
)
from app.services.tutor_runtime.state_loader import (
    get_session as _get_session,
    load_recent_turns as _load_recent_turns,
)
from app.services.tutor_runtime.step_state import (
    build_focus_concepts as _build_focus_concepts,
    get_step_index as _get_step_index,
    get_step_roadmap as _get_step_roadmap,
    get_step_type as _get_step_type,
    normalize_runtime_plan_state as _normalize_runtime_plan_state,
    obj_meta as _obj_meta,
    step_meta as _step_meta,
)
from app.services.tutor_runtime.types import (
    StageContext,
    TurnResult,
)


class TurnPipeline:
    """Orchestrates tutoring turns around objectives and step-plans."""

    # Maximum consecutive ad-hoc steps before forcing reconnection.
    MAX_AD_HOC_STEPS = 3

    def __init__(
        self,
        db_session: AsyncSession,
        policy_agent: PolicyAgent,
        tutor_agent: TutorAgent,
        evaluator_agent: EvaluatorAgent,
        safety_critic: SafetyCritic,
        retrieval_service: RetrievalService,
    ):
        self.db = db_session
        self.policy = policy_agent
        self.tutor = tutor_agent
        self.evaluator = evaluator_agent
        self.critic = safety_critic
        self.retriever = retrieval_service

    @staticmethod
    def _open_optional_span(
        lf,
        *,
        name: str,
        metadata: dict | None = None,
        input_data: dict | None = None,
    ):
        if not lf:
            return None, None

        kwargs = {
            "as_type": "span",
            "name": name,
        }
        if metadata is not None:
            kwargs["metadata"] = metadata
        if input_data is not None:
            kwargs["input"] = input_data

        ctx = lf.start_as_current_observation(**kwargs)
        span = ctx.__enter__()
        return ctx, span

    @staticmethod
    def _close_optional_span(ctx, *, span=None, output: dict | None = None) -> None:
        if ctx is None:
            return
        if span is not None and output is not None:
            span.update(output=output)
        ctx.__exit__(None, None, None)

    async def _run_safety_stage(
        self,
        *,
        lf,
        current_obj: dict,
        plan: dict,
        tutor_output,
        retrieved_chunks,
        student_message: str,
    ):
        """Run safety critic and apply safe fallback response when blocked."""
        degraded_mode = False
        critic_output = None
        safety_span_ctx, safety_span = self._open_optional_span(
            lf,
            name="agent.safety",
            metadata={
                "agent": "safety_critic",
                "objective_id": current_obj.get("objective_id", ""),
                "step_type": plan.get(
                    "effective_step_type",
                    plan.get("current_step", "unknown"),
                ),
            },
        )
        try:
            critic_output = await self.critic.evaluate(
                tutor_output.response_text,
                [{"text": c.text, "chunk_id": str(c.chunk_id)} for c in retrieved_chunks],
                current_obj,
                student_message,
                cited_evidence_chunk_ids=getattr(tutor_output, "evidence_chunk_ids", None),
            )
        finally:
            self._close_optional_span(
                safety_span_ctx,
                span=safety_span,
                output={
                    "blocked": bool(
                        getattr(critic_output, "should_block", False)
                    ),
                    "safety_decision": getattr(
                        critic_output,
                        "safety_decision",
                        "allow",
                    ),
                },
            )

        if critic_output and critic_output.should_block:
            safety_decision = getattr(critic_output, "safety_decision", "refuse_and_redirect")
            _append_trace_event(
                plan,
                "guard_override",
                {
                    "guard_name": "safety_block",
                    "decision_requested": "allow_response",
                    "decision_applied": safety_decision,
                    "reason": "safety_critic_block",
                    "guard_priority": 1,
                },
            )
            if safety_decision == "refuse":
                blocked_text = (
                    "I can't help with that request. We can continue with the learning topic instead."
                )
            else:
                blocked_text = (
                    "I can't help with that request. Let's stay on the learning topic. "
                    "Tell me which concept you want to review next."
                )
            tutor_output = type(tutor_output)(
                response_text=blocked_text,
                evidence_chunk_ids=getattr(tutor_output, "evidence_chunk_ids", None),
            )
            degraded_mode = True

        return tutor_output, degraded_mode

    @staticmethod
    def _sync_active_step_after_progression(
        plan: dict,
        objective_queue: list[dict],
        current_obj: dict,
    ) -> None:
        """Keep current step pointers aligned with post-progression objective state."""
        new_obj_idx = plan.get("current_objective_index", 0)
        new_obj = (
            objective_queue[new_obj_idx]
            if new_obj_idx < len(objective_queue)
            else current_obj
        )
        new_step_idx = _get_step_index(plan)
        new_roadmap = _get_step_roadmap(new_obj)
        if new_step_idx < len(new_roadmap):
            plan["current_step"] = _get_step_type(new_roadmap[new_step_idx])
            plan["effective_step_type"] = plan["current_step"]

    @staticmethod
    def _resolve_focus_concepts_after_progression(
        plan: dict,
        objective_queue: list[dict],
        current_obj: dict,
        session_complete: bool,
    ) -> list[str]:
        """Compute canonical focus concepts based on current post-progression objective."""
        if session_complete:
            return []

        result_obj_idx = int(plan.get("current_objective_index", 0) or 0)
        result_obj = (
            objective_queue[result_obj_idx]
            if 0 <= result_obj_idx < len(objective_queue)
            else current_obj
        )
        return _build_focus_concepts(result_obj.get("concept_scope", {}))

    @staticmethod
    def _update_recent_evidence_chunk_ids(
        plan: dict,
        evidence_chunk_ids: list[str] | None,
        max_items: int = 30,
    ) -> None:
        """Track recently cited evidence chunks for novelty-aware retrieval."""
        prior_recent = [
            str(cid)
            for cid in (plan.get("recent_evidence_chunk_ids") or [])
            if cid
        ]
        new_recent = [str(cid) for cid in (evidence_chunk_ids or []) if cid]
        merged_recent = prior_recent + new_recent
        if not merged_recent:
            return

        deduped_recent = []
        seen_recent = set()
        for cid in reversed(merged_recent):
            if cid in seen_recent:
                continue
            seen_recent.add(cid)
            deduped_recent.append(cid)
        plan["recent_evidence_chunk_ids"] = list(reversed(deduped_recent))[-max_items:]

    @staticmethod
    def _compute_uncertainty_after(
        plan: dict,
        focus_concepts: list[str],
        mastery_delta: dict,
        uncertainty_before: dict[str, float],
    ) -> dict[str, float]:
        student_concept_state_after = plan.get("student_concept_state") or {}
        return {
            concept: float(
                (student_concept_state_after.get(concept) or {}).get(
                    "mastery_uncertainty",
                    uncertainty_before.get(concept, 0.0),
                )
                or 0.0
            )
            for concept in set(focus_concepts)
            | set(mastery_delta.keys())
            | set(uncertainty_before.keys())
        }

    @staticmethod
    def _resolve_result_objective(
        plan: dict,
        objective_queue: list[dict],
        current_obj: dict,
    ) -> dict:
        result_obj_idx = int(plan.get("current_objective_index", 0) or 0)
        return (
            objective_queue[result_obj_idx]
            if 0 <= result_obj_idx < len(objective_queue)
            else current_obj
        )

    @staticmethod
    def _build_turn_result(
        *,
        turn_id: str,
        tutor_output,
        detected_question,
        policy_output,
        plan: dict,
        session,
        mastery_delta: dict,
        result_obj: dict,
        transition,
        retrieved_chunks,
        evidence_chunk_ids,
        degraded_mode: bool,
        trace_events,
        policy_metadata: dict,
        telemetry_contract: dict,
        session_complete: bool,
        session_summary: dict | None = None,
    ) -> TurnResult:
        result_focus_concepts = plan.get("focus_concepts") or []
        return TurnResult(
            turn_id=turn_id,
            tutor_response=tutor_output.response_text,
            tutor_question=detected_question,
            action=policy_output.pedagogical_action,
            current_step=plan.get("current_step", "explain"),
            current_step_index=_get_step_index(plan),
            concept=result_focus_concepts[0] if result_focus_concepts else "",
            focus_concepts=result_focus_concepts,
            mastery=dict(session.mastery),
            mastery_delta=mastery_delta,
            objective_progress=plan.get("objective_progress", {}).get(
                result_obj.get("objective_id", ""), {}
            ),
            session_complete=session_complete,
            awaiting_evaluation=plan.get("awaiting_evaluation", False),
            objective_id=result_obj.get("objective_id", ""),
            objective_title=result_obj.get("title", ""),
            step_transition=transition,
            retrieved_chunks=[
                {"chunk_id": str(c.chunk_id), "text": c.text[:200]}
                for c in retrieved_chunks
            ],
            evidence_chunk_ids=evidence_chunk_ids,
            degraded_mode=degraded_mode,
            guard_events=trace_events,
            decision_requested=policy_metadata.get("decision_requested"),
            decision_applied=policy_metadata.get("decision_applied"),
            delegated=bool(policy_metadata.get("delegated", False)),
            delegation_reason=policy_metadata.get("delegation_reason"),
            delegation_outcome=policy_metadata.get("delegation_outcome"),
            telemetry_contract=telemetry_contract,
            session_summary=session_summary,
        )

    async def execute_turn(
        self,
        session_id: uuid.UUID,
        student_message: str,
    ) -> TurnResult:
        turn_id = str(uuid.uuid4())
        turn_start = _time.time()
        lf = get_langfuse_client()

        sample_rate_raw = os.getenv("LANGFUSE_TRACE_SAMPLE_RATE", "1.0")
        try:
            sample_rate = float(sample_rate_raw)
        except ValueError:
            sample_rate = 1.0
        if lf and not should_sample_trace(f"{session_id}:{turn_id}", sample_rate):
            lf = None

        if not lf:
            return await self._execute_turn_core(
                session_id, student_message, turn_id, turn_start
            )

        detailed_tracing = is_detailed_tracing_enabled()

        with lf.start_as_current_observation(
            as_type="span",
            name="turn.execute",
            input=normalize_trace_metadata(
                {"student_message": redact_text_for_trace(student_message)}
            ),
            metadata=normalize_trace_metadata(
                {
                    "session_id": str(session_id),
                    "turn_id": turn_id,
                    "trace_style": "agent_turn_centric",
                }
            ),
        ) as root_span:
            with propagate_attributes(
                session_id=str(session_id),
                user_id=str(session_id),
                tags=["tutoring"],
            ):
                result = await self._execute_turn_core(
                    session_id,
                    student_message,
                    turn_id,
                    turn_start,
                    lf=lf if detailed_tracing else None,
                )

                latency = round((_time.time() - turn_start) * 1000)
                guard_override_count = sum(
                    1
                    for event in (result.guard_events or [])
                    if isinstance(event, dict)
                    and event.get("name") == "guard_override"
                )
                root_span.update(
                    output=normalize_trace_metadata({
                        "turn": {
                            "turn_id": turn_id,
                            "latency_ms": latency,
                            "session_complete": result.session_complete,
                            "degraded": result.degraded_mode,
                        },
                        "agent_outcome": {
                            "action": result.action,
                            "decision_requested": result.decision_requested,
                            "decision_applied": result.decision_applied,
                            "delegated": result.delegated,
                            "delegation_reason": result.delegation_reason,
                        },
                        "learning_state": {
                            "objective_id": result.objective_id,
                            "objective": result.objective_title,
                            "step": result.current_step,
                            "step_index": result.current_step_index,
                            "transition": result.step_transition,
                        },
                        "signals": {
                            "guard_override_count": guard_override_count,
                            "evidence_count": len(result.evidence_chunk_ids or []),
                            "score_contract_version": (
                                (result.telemetry_contract or {}).get("version")
                            ),
                        },
                    })
                )

                trace_id = getattr(root_span, "trace_id", None)
                if trace_id:
                    _emit_scores(trace_id, result, student_message)

        flush_langfuse()
        return result

    async def _execute_turn_core(
        self,
        session_id: uuid.UUID,
        student_message: str,
        turn_id: str,
        turn_start: float,
        lf=None,
    ) -> TurnResult:
        if lf is None:
            lf = get_langfuse_client() if is_detailed_tracing_enabled() else None

        load_span_ctx, _ = self._open_optional_span(
            lf,
            name="turn.load",
            metadata=normalize_trace_metadata(
                {"session_id": str(session_id), "phase": "load"}
            ),
        )
        try:
            session = await _get_session(self.db, session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            if not session.plan_state or "objective_queue" not in session.plan_state:
                raise ValueError(
                    f"Session {session_id} has no curriculum plan. "
                    "Ensure the session was created via the /sessions/resource endpoint."
                )
        finally:
            self._close_optional_span(load_span_ctx)

        plan = _normalize_runtime_plan_state(session.plan_state)
        obj_idx = plan.get("current_objective_index", 0)
        objective_queue = plan.get("objective_queue", [])

        if obj_idx >= len(objective_queue):
            return await _handle_session_complete(
                self.db, session, turn_id,
                llm_provider=self.tutor.llm,
            )

        current_obj = objective_queue[obj_idx]
        step_idx = _get_step_index(plan)
        plan["current_step_index"] = step_idx
        focus_concepts = _build_focus_concepts(current_obj.get("concept_scope", {}))
        mastery_snap = {c: session.mastery.get(c, 0.0) for c in focus_concepts}
        mastery_before = dict(session.mastery) if session.mastery else {}

        obj_span_ctx, _ = self._open_optional_span(
            lf,
            name="turn.context",
            metadata=normalize_trace_metadata(_obj_meta(current_obj, obj_idx)),
            input_data=normalize_trace_metadata(
                {
                    "mastery_snapshot": mastery_snap,
                    "objective_progress": plan.get("objective_progress", {}).get(
                        current_obj.get("objective_id", ""), {}
                    ),
                }
            ),
        )

        try:
            result = await self._run_step(
                session,
                plan,
                current_obj,
                obj_idx,
                step_idx,
                focus_concepts,
                mastery_snap,
                mastery_before,
                student_message,
                turn_id,
                turn_start,
                lf,
            )
        finally:
            self._close_optional_span(obj_span_ctx)

        return result

    async def _run_step(
        self,
        session: UserSession,
        plan: dict,
        current_obj: dict,
        obj_idx: int,
        step_idx: int,
        focus_concepts: list[str],
        mastery_snap: dict,
        mastery_before: dict,
        student_message: str,
        turn_id: str,
        turn_start: float,
        lf,
    ) -> TurnResult:
        roadmap = _get_step_roadmap(current_obj)
        current_step_data = roadmap[step_idx] if step_idx < len(roadmap) else {}
        step_type = _get_step_type(current_step_data) or plan.get("current_step", "explain")
        plan["effective_step_type"] = step_type
        objective_queue = plan.get("objective_queue", [])
        student_concept_state_before = plan.get("student_concept_state") or {}
        uncertainty_before = {
            concept: float((student_concept_state_before.get(concept) or {}).get("mastery_uncertainty", 0.0) or 0.0)
            for concept in focus_concepts
        }

        step_span_ctx, _ = self._open_optional_span(
            lf,
            name="turn.agent_flow",
            metadata=normalize_trace_metadata(_step_meta(current_obj, step_idx)),
            input_data=normalize_trace_metadata(
                {"student_message": redact_text_for_trace(student_message)}
            ),
        )

        try:
            evaluation_result = None
            mastery_delta = {}
            recent_turns_task = asyncio.create_task(
                _load_recent_turns(self.db, session.id, count=5)
            )

            try:
                if plan.get("awaiting_evaluation"):
                    evaluation_result, mastery_delta = await _evaluate_response(
                        self.evaluator,
                        session,
                        plan,
                        student_message,
                        focus_concepts,
                        mastery_snap,
                        current_obj,
                        lf=lf,
                    )
                    _apply_evaluation_plan_updates(plan, current_obj, evaluation_result)
                    mastery_snap = {c: session.mastery.get(c, 0.0) for c in focus_concepts}

                recent_turns = await recent_turns_task
            except Exception:
                if not recent_turns_task.done():
                    recent_turns_task.cancel()
                raise
            stage_ctx = StageContext(
                session=session,
                plan=plan,
                current_objective=current_obj,
                objective_index=obj_idx,
                step_index=step_idx,
                student_message=student_message,
                focus_concepts=focus_concepts,
                mastery_snapshot=mastery_snap,
            )

            policy_stage = await _run_policy_stage_handoff(
                self.policy,
                stage_ctx,
                evaluation_result,
                recent_turns,
                max_ad_hoc_default=self.MAX_AD_HOC_STEPS,
                lf=lf,
            )
            policy_output = policy_stage.policy_output
            policy_metadata = dict(policy_stage.policy_metadata or {})
            policy_metadata["objective_id"] = current_obj.get("objective_id", "")
            policy_metadata["step_type"] = plan.get("current_step", "explain")
            plan["effective_step_type"] = policy_stage.effective_step_type

            retrieval_stage = await _run_retrieval_stage_handoff(
                self.retriever,
                stage_ctx,
                policy_stage.target_concepts,
                policy_output=policy_output,
                lf=lf,
            )
            retrieved_chunks = retrieval_stage.retrieved_chunks
            evidence_chunk_ids = retrieval_stage.evidence_chunk_ids

            delegation_decision = _decide_adaptive_delegation(
                plan=plan,
                recent_turns=recent_turns,
                evaluation_result=evaluation_result,
                focus_concepts=focus_concepts,
                retrieved_chunks=retrieved_chunks,
                evidence_chunk_ids=evidence_chunk_ids,
            )
            _append_trace_event(
                plan,
                "delegation_decision",
                _delegation_trace_payload(delegation_decision),
            )
            if delegation_decision.delegated:
                policy_output = _apply_delegation_override(
                    policy_output,
                    delegation_decision,
                )
            policy_metadata["decision_applied"] = (
                policy_output.progression_decision.name
                if hasattr(policy_output.progression_decision, "name")
                else str(policy_output.progression_decision)
            )
            policy_metadata["delegated"] = delegation_decision.delegated
            policy_metadata["delegation_reason"] = delegation_decision.reason
            policy_metadata["delegation_outcome"] = delegation_decision.outcome

            response_stage = await _run_response_stage_handoff(
                self.tutor,
                stage_ctx,
                policy_output,
                retrieved_chunks,
                lf=lf,
            )
            tutor_output = response_stage.tutor_output
            tutor_output, degraded_mode = await self._run_safety_stage(
                lf=lf,
                current_obj=current_obj,
                plan=plan,
                tutor_output=tutor_output,
                retrieved_chunks=retrieved_chunks,
                student_message=student_message,
            )

            evidence_chunk_ids = (
                getattr(tutor_output, "evidence_chunk_ids", None)
                or evidence_chunk_ids
            )

            has_question, detected_question = _detect_question(tutor_output.response_text)
            if has_question:
                plan["awaiting_evaluation"] = True
                plan["awaiting_turn_id"] = turn_id
                plan["last_tutor_question"] = detected_question
                plan["last_tutor_response"] = tutor_output.response_text[:1000]

            session_complete, plan, transition = _apply_progression(
                session,
                plan,
                policy_output,
                current_obj,
                lf=lf,
                max_ad_hoc_default=self.MAX_AD_HOC_STEPS,
            )

            if not session_complete:
                self._sync_active_step_after_progression(
                    plan,
                    objective_queue,
                    current_obj,
                )

            result_focus_concepts = self._resolve_focus_concepts_after_progression(
                plan,
                objective_queue,
                current_obj,
                session_complete,
            )
            self._update_recent_evidence_chunk_ids(plan, evidence_chunk_ids)
            plan["focus_concepts"] = result_focus_concepts

        finally:
            self._close_optional_span(step_span_ctx)

        latency_ms = round((_time.time() - turn_start) * 1000)
        persist_span_ctx, _ = self._open_optional_span(
            lf,
            name="turn.persist",
            metadata={
                "phase": "persist",
                "decision_applied": policy_metadata.get("decision_applied"),
                "step_type": plan.get("current_step", "unknown"),
            },
        )
        try:
            await _persist_turn(
                db=self.db,
                turn_id=turn_id,
                session=session,
                student_message=student_message,
                tutor_output=tutor_output,
                policy_output=policy_output,
                evaluation_result=evaluation_result,
                retrieved_chunks=retrieved_chunks,
                evidence_chunk_ids=evidence_chunk_ids,
                plan=plan,
                latency_ms=latency_ms,
                mastery_before=mastery_before,
                policy_metadata=policy_metadata,
            )
        finally:
            self._close_optional_span(persist_span_ctx)

        uncertainty_after = self._compute_uncertainty_after(
            plan,
            focus_concepts,
            mastery_delta,
            uncertainty_before,
        )
        telemetry_contract = _build_turn_telemetry_contract(
            decision_requested=policy_metadata.get("decision_requested"),
            decision_applied=policy_metadata.get("decision_applied"),
            student_intent=policy_metadata.get("student_intent"),
            guard_events=plan.get("__trace_events", []),
            evidence_chunk_ids=evidence_chunk_ids or [],
            mastery_delta=mastery_delta,
            uncertainty_before=uncertainty_before,
            uncertainty_after=uncertainty_after,
            forgetting_supported=False,
        )
        trace_events = _consume_trace_events(plan)

        session.plan_state = plan
        flag_modified(session, "plan_state")
        flag_modified(session, "mastery")

        # Generate session summary when completing
        session_summary_data = None
        if session_complete:
            session.status = "completed"
            try:
                from app.agents.summary_agent import SummaryAgent, SummaryState
                mastery_dict = dict(session.mastery) if session.mastery else {}
                summary_state = SummaryState(
                    objectives=objective_queue,
                    objective_progress=plan.get("objective_progress", {}),
                    mastery=mastery_dict,
                    initial_mastery={c: 0.0 for c in mastery_dict},
                    turn_count=plan.get("turn_count", 0),
                    topic=plan.get("active_topic"),
                )
                summary_agent = SummaryAgent(self.tutor.llm)
                summary_output = await summary_agent.run(summary_state)
                session_summary_data = {
                    "summary_text": summary_output.summary_text,
                    "concepts_strong": summary_output.concepts_strong,
                    "concepts_developing": summary_output.concepts_developing,
                    "concepts_to_revisit": summary_output.concepts_to_revisit,
                    "objectives": [
                        {
                            "objective_id": obj.get("objective_id", ""),
                            "title": obj.get("title", ""),
                            "primary_concepts": obj.get("concept_scope", {}).get("primary", []),
                            "progress": plan.get("objective_progress", {}).get(obj.get("objective_id", ""), {}),
                        }
                        for obj in objective_queue
                    ],
                    "mastery_snapshot": mastery_dict,
                    "turn_count": plan.get("turn_count", 0),
                    "topic": plan.get("active_topic"),
                }
                plan["session_summary"] = session_summary_data
                session.plan_state = plan
                flag_modified(session, "plan_state")
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).warning(f"Summary generation failed in orchestrator: {e}")

        await self.db.commit()

        result_obj = self._resolve_result_objective(plan, objective_queue, current_obj)
        return self._build_turn_result(
            turn_id=turn_id,
            tutor_output=tutor_output,
            detected_question=detected_question,
            policy_output=policy_output,
            plan=plan,
            session=session,
            mastery_delta=mastery_delta,
            result_obj=result_obj,
            transition=transition,
            retrieved_chunks=retrieved_chunks,
            evidence_chunk_ids=evidence_chunk_ids,
            degraded_mode=degraded_mode,
            trace_events=trace_events,
            policy_metadata=policy_metadata,
            telemetry_contract=telemetry_contract,
            session_complete=session_complete,
            session_summary=session_summary_data,
        )
