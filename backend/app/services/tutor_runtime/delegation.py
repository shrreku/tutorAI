from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from app.config import settings
from app.schemas.agent_output import (
    PedagogicalAction,
    PolicyOrchestratorOutput,
    ProgressionDecision,
)


COOLDOWN_TURNS = 2
HIGH_UNCERTAINTY_THRESHOLD = 0.75
LOW_EVIDENCE_CONFIDENCE_THRESHOLD = 0.4


@dataclass
class DelegationDecision:
    delegated: bool
    reason: str | None
    outcome: str
    signals: dict[str, Any] = field(default_factory=dict)


def _evaluation_label_from_turn(turn: dict[str, Any]) -> str | None:
    evaluator_output = (turn or {}).get("evaluator_output") or {}
    label = evaluator_output.get("label") or evaluator_output.get("correctness_label")
    if not label:
        return None
    return str(label).lower()


def _current_eval_label(evaluation_result: Any) -> str | None:
    if evaluation_result is None:
        return None
    if isinstance(evaluation_result, dict):
        value = evaluation_result.get("correctness_label")
    else:
        value = getattr(evaluation_result, "correctness_label", None)
    if not value:
        return None
    return str(value).lower()


def _detect_repeated_confusion(
    recent_turns: Sequence[dict[str, Any]],
    evaluation_result: Any,
) -> bool:
    labels = [
        label
        for label in (_evaluation_label_from_turn(t) for t in recent_turns[-3:])
        if label is not None
    ]
    current_label = _current_eval_label(evaluation_result)
    if current_label:
        labels.append(current_label)

    if len(labels) < 2:
        return False
    tail = labels[-2:]
    return all(label in {"incorrect", "unclear"} for label in tail)


def _compute_avg_uncertainty(plan: dict[str, Any], focus_concepts: list[str]) -> float:
    concept_state = plan.get("student_concept_state") or {}
    values = []
    for concept in focus_concepts:
        state = concept_state.get(concept)
        if isinstance(state, dict):
            try:
                values.append(float(state.get("mastery_uncertainty", 0.0) or 0.0))
            except (TypeError, ValueError):
                continue

    if not values:
        return 0.0
    return sum(values) / len(values)


def _compute_evidence_confidence(
    retrieved_chunks: Sequence[Any], evidence_chunk_ids: list[str]
) -> float:
    total = len(retrieved_chunks)
    if total <= 0:
        return 0.0

    cited = len(set(evidence_chunk_ids or []))
    if cited <= 0:
        return 0.0
    return min(1.0, cited / total)


def _last_delegation_reason(recent_turns: Sequence[dict[str, Any]]) -> str | None:
    if not recent_turns:
        return None
    last_turn = recent_turns[-1] or {}
    policy_output = last_turn.get("policy_output") or {}
    reason = policy_output.get("delegation_reason")
    return str(reason) if reason else None


def decide_adaptive_delegation(
    *,
    plan: dict[str, Any],
    recent_turns: Sequence[dict[str, Any]],
    evaluation_result: Any,
    focus_concepts: list[str],
    retrieved_chunks: Sequence[Any],
    evidence_chunk_ids: list[str],
) -> DelegationDecision:
    """Choose whether to route through specialist path under explicit conditions only."""
    if not settings.ADAPTIVE_DELEGATION_ENABLED:
        return DelegationDecision(
            delegated=False,
            reason=None,
            outcome="disabled",
            signals={"adaptive_delegation_enabled": False},
        )

    cooldown = int(plan.get("delegation_cooldown_turns", 0) or 0)
    if cooldown > 0:
        plan["delegation_cooldown_turns"] = cooldown - 1
        return DelegationDecision(
            delegated=False,
            reason=None,
            outcome="cooldown_active",
            signals={"cooldown_remaining": plan.get("delegation_cooldown_turns", 0)},
        )

    repeated_confusion = _detect_repeated_confusion(recent_turns, evaluation_result)
    avg_uncertainty = _compute_avg_uncertainty(plan, focus_concepts)
    high_uncertainty = avg_uncertainty >= HIGH_UNCERTAINTY_THRESHOLD
    evidence_confidence = _compute_evidence_confidence(
        retrieved_chunks, evidence_chunk_ids
    )
    low_evidence_confidence = evidence_confidence < LOW_EVIDENCE_CONFIDENCE_THRESHOLD

    signals = {
        "repeated_confusion": repeated_confusion,
        "avg_uncertainty": round(avg_uncertainty, 4),
        "high_uncertainty": high_uncertainty,
        "evidence_confidence": round(evidence_confidence, 4),
        "low_evidence_confidence": low_evidence_confidence,
    }

    reason = None
    if repeated_confusion:
        reason = "repeated_confusion"
    elif high_uncertainty:
        reason = "high_uncertainty"
    elif low_evidence_confidence:
        reason = "low_evidence_confidence"

    if reason is None:
        return DelegationDecision(
            delegated=False,
            reason=None,
            outcome="single_path_default",
            signals=signals,
        )

    if _last_delegation_reason(recent_turns) == reason:
        plan["delegation_cooldown_turns"] = max(
            int(plan.get("delegation_cooldown_turns", 0) or 0),
            1,
        )
        return DelegationDecision(
            delegated=False,
            reason=reason,
            outcome="recently_delegated_same_reason",
            signals=signals,
        )

    plan["delegation_cooldown_turns"] = COOLDOWN_TURNS
    return DelegationDecision(
        delegated=True,
        reason=reason,
        outcome="specialist_path_selected",
        signals=signals,
    )


def apply_delegation_override(
    policy_output: PolicyOrchestratorOutput,
    decision: DelegationDecision,
) -> PolicyOrchestratorOutput:
    """Map delegation reasons to specialist strategy without overriding progression."""
    if not decision.delegated or not decision.reason:
        return policy_output

    action_map = {
        "repeated_confusion": PedagogicalAction.CORRECT,
        "high_uncertainty": PedagogicalAction.HINT,
        "low_evidence_confidence": PedagogicalAction.CLARIFY,
    }
    chosen_action = action_map.get(decision.reason, policy_output.pedagogical_action)
    guidance = f"adaptive_delegation:{decision.reason}"
    prior_guidance = (policy_output.planner_guidance or "").strip()
    if prior_guidance:
        guidance = f"{prior_guidance} | {guidance}"

    return policy_output.model_copy(
        update={
            "pedagogical_action": chosen_action,
            "planner_guidance": guidance,
            "ad_hoc_step_type": "probe"
            if decision.reason != "low_evidence_confidence"
            else None,
        }
    )


def delegation_trace_payload(decision: DelegationDecision) -> dict[str, Any]:
    return {
        "delegated": decision.delegated,
        "reason": decision.reason,
        "outcome": decision.outcome,
        "signals": decision.signals,
    }
