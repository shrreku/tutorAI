from app.services.tracing import score_trace, score_trace_categorical
from app.services.tutor_runtime.types import TurnResult


def emit_scores(trace_id: str, result: TurnResult, student_message: str) -> None:
    """Emit meaningful Langfuse scores for a tutoring turn."""
    if result.mastery_delta:
        delta_sum = sum(result.mastery_delta.values())
        score_trace(trace_id, "mastery_delta", round(delta_sum, 3), comment=f"obj={result.objective_id}")

    engagement = min(1.0, len(student_message.split()) / 25)
    score_trace(trace_id, "student_engagement", round(engagement, 2))

    focus_n = max(len(result.focus_concepts), 1)
    progressed = sum(1 for v in result.mastery_delta.values() if v > 0) if result.mastery_delta else 0
    score_trace(trace_id, "learning_efficiency", round(min(1.0, progressed / focus_n), 2))

    score_trace(trace_id, "guardrail_violation", 1.0 if result.degraded_mode else 0.0)
    telemetry = result.telemetry_contract or {}
    score_trace(trace_id, "evidence_count", float(telemetry.get("evidence_count", 0.0) or 0.0))

    mastery_abs_sum = telemetry.get("mastery_delta_abs_sum")
    if mastery_abs_sum is None:
        mastery_summary = telemetry.get("mastery_delta_summary") or {}
        mastery_abs_sum = mastery_summary.get("delta_abs_sum", 0.0)
    score_trace(
        trace_id,
        "mastery_delta_abs_sum",
        float(mastery_abs_sum or 0.0),
    )

    uncertainty_abs_sum = telemetry.get("uncertainty_delta_abs_sum")
    if uncertainty_abs_sum is None:
        uncertainty_summary = telemetry.get("uncertainty_delta_summary") or {}
        uncertainty_abs_sum = uncertainty_summary.get("delta_abs_sum", 0.0)
    score_trace(
        trace_id,
        "uncertainty_delta_abs_sum",
        float(uncertainty_abs_sum or 0.0),
    )

    forgetting_delta_sum = telemetry.get("forgetting_risk_delta_sum")
    if forgetting_delta_sum is None:
        forgetting_summary = telemetry.get("forgetting_risk_changes") or {}
        forgetting_delta_sum = forgetting_summary.get("delta_sum", 0.0)
    score_trace(
        trace_id,
        "forgetting_risk_delta_sum",
        float(forgetting_delta_sum or 0.0),
    )

    if result.decision_requested:
        score_trace_categorical(trace_id, "decision_requested", result.decision_requested)
    if result.decision_applied:
        score_trace_categorical(trace_id, "decision_applied", result.decision_applied)
    if result.decision_requested and result.decision_applied:
        score_trace(
            trace_id,
            "decision_alignment",
            1.0 if result.decision_requested == result.decision_applied else 0.0,
        )

    score_trace(trace_id, "delegation_rate", 1.0 if result.delegated else 0.0)
    if result.delegation_reason:
        score_trace_categorical(trace_id, "delegation_reason", result.delegation_reason)
    if result.delegation_outcome:
        score_trace_categorical(trace_id, "delegation_outcome", result.delegation_outcome)

    score_trace_categorical(trace_id, "objective_id", result.objective_id)
    score_trace_categorical(trace_id, "step_type", result.current_step)
    score_trace_categorical(
        trace_id,
        "session_status",
        "completed" if result.session_complete else "active",
    )

    reward = round(
        0.4 * engagement
        + 0.3 * (0.0 if result.degraded_mode else 1.0)
        + 0.3 * min(1.0, progressed / focus_n),
        2,
    )
    score_trace(trace_id, "turn_reward", reward)

    guard_events = result.guard_events or []
    guard_override_events = [
        e
        for e in guard_events
        if (e or {}).get("name") == "guard_override"
        and (e or {}).get("guard_name")
    ]
    has_guard_override = bool(guard_override_events)
    decision_validity = 0.75 if has_guard_override else 1.0
    score_trace(trace_id, "decision_validity", decision_validity)
    score_trace(trace_id, "guard_name_count", float(len(guard_override_events)))

    guard_intervention_rate = min(1.0, len(guard_override_events) / 3.0)
    score_trace(trace_id, "guard_intervention_rate", round(guard_intervention_rate, 2))

    ad_hoc_ratio = 1.0 if (result.step_transition and "ad_hoc" in result.step_transition) else 0.0
    score_trace(trace_id, "ad_hoc_ratio", ad_hoc_ratio)

    step_progress_velocity = 1.0 if (result.step_transition and "→" in result.step_transition) else 0.0
    score_trace(trace_id, "step_progress_velocity", step_progress_velocity)

    trace_completeness = 1.0
    if not result.objective_id or not result.current_step or result.step_transition is None:
        trace_completeness = 0.8
    if result.guard_events is None:
        trace_completeness = 0.6
    score_trace(trace_id, "trace_completeness", trace_completeness)
