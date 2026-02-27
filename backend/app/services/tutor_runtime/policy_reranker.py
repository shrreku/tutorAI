from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.schemas.agent_output import PolicyOrchestratorOutput, ProgressionDecision


@dataclass
class RerankResult:
    policy_output: PolicyOrchestratorOutput
    enabled: bool
    changed: bool
    requested_decision: str
    applied_decision: str
    reason: str
    candidate_scores: dict[str, float]


def _as_eval_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _to_progression_name(value: Any) -> str:
    if isinstance(value, ProgressionDecision):
        return value.name
    if hasattr(value, "name"):
        return str(value.name)
    if isinstance(value, int):
        try:
            return ProgressionDecision(value).name
        except ValueError:
            return str(value)
    return str(value)


def _preferred_decision(plan: dict[str, Any], eval_payload: dict[str, Any]) -> ProgressionDecision:
    score = float(eval_payload.get("overall_score", 0.5) or 0.5)
    label = str(eval_payload.get("correctness_label", "partial") or "partial").lower()
    uncertainty = float(eval_payload.get("uncertainty", 0.5) or 0.5)
    turns_at_step = int(plan.get("turns_at_step", 0) or 0)

    if label in {"incorrect", "unclear"} or uncertainty >= 0.7:
        return ProgressionDecision.INSERT_AD_HOC
    if score >= 0.78 and uncertainty <= 0.45:
        return ProgressionDecision.ADVANCE_STEP
    if turns_at_step >= 2 and score >= 0.65:
        return ProgressionDecision.ADVANCE_STEP
    return ProgressionDecision.CONTINUE_STEP


def _score_candidate(
    candidate_decision: ProgressionDecision,
    preferred_decision: ProgressionDecision,
    base_confidence: float,
) -> float:
    match_bonus = 1.0 if candidate_decision == preferred_decision else 0.0
    distance_penalty = abs(candidate_decision.value - preferred_decision.value) * 0.03
    return round((0.6 * match_bonus) + (0.4 * base_confidence) - distance_penalty, 6)


def rerank_policy_output(
    policy_output: PolicyOrchestratorOutput,
    *,
    plan: dict[str, Any],
    evaluation_result: Any,
) -> RerankResult:
    requested_decision = _to_progression_name(policy_output.progression_decision)

    if not settings.LLM_RERANKER_ENABLED:
        return RerankResult(
            policy_output=policy_output,
            enabled=False,
            changed=False,
            requested_decision=requested_decision,
            applied_decision=requested_decision,
            reason="reranker_disabled",
            candidate_scores={requested_decision: round(float(policy_output.confidence), 6)},
        )

    eval_payload = _as_eval_dict(evaluation_result)
    preferred = _preferred_decision(plan, eval_payload)
    base_confidence = float(getattr(policy_output, "confidence", 0.5) or 0.5)

    candidates = {policy_output.progression_decision}
    candidates.add(preferred)
    candidates.add(ProgressionDecision.CONTINUE_STEP)
    if preferred == ProgressionDecision.INSERT_AD_HOC:
        candidates.add(ProgressionDecision.ADVANCE_STEP)

    candidate_scores = {
        decision.name: _score_candidate(decision, preferred, base_confidence)
        for decision in sorted(candidates, key=lambda d: d.value)
    }
    best_decision_name, _best_score = max(candidate_scores.items(), key=lambda item: item[1])
    best_decision = ProgressionDecision[best_decision_name]

    changed = best_decision != policy_output.progression_decision
    if not changed:
        return RerankResult(
            policy_output=policy_output,
            enabled=True,
            changed=False,
            requested_decision=requested_decision,
            applied_decision=requested_decision,
            reason="baseline_selected",
            candidate_scores=candidate_scores,
        )

    guidance_bits = [
        f"reranked_by=offline_linear_v2",
        f"requested={requested_decision}",
        f"applied={best_decision.name}",
        f"preferred={preferred.name}",
    ]
    prior_guidance = (policy_output.planner_guidance or "").strip()
    guidance = " | ".join(guidance_bits)
    if prior_guidance:
        guidance = f"{prior_guidance} | {guidance}"

    updated_output = policy_output.model_copy(
        update={
            "progression_decision": best_decision,
            "planner_guidance": guidance,
            "confidence": max(0.0, min(1.0, base_confidence * 0.98)),
            "ad_hoc_step_type": (
                policy_output.ad_hoc_step_type
                if best_decision == ProgressionDecision.INSERT_AD_HOC
                else None
            ),
        }
    )

    return RerankResult(
        policy_output=updated_output,
        enabled=True,
        changed=True,
        requested_decision=requested_decision,
        applied_decision=best_decision.name,
        reason="reranked_offline_linear_v2",
        candidate_scores=candidate_scores,
    )
