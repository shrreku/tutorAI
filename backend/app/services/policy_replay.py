from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_policy_replay_row(turn: Any) -> dict[str, Any]:
    policy_output = _to_dict(getattr(turn, "policy_output", None))
    evaluator_output = _to_dict(getattr(turn, "evaluator_output", None))
    retrieved_chunks = getattr(turn, "retrieved_chunks", None) or []

    evidence_count = len(retrieved_chunks)
    cited_count = sum(
        1
        for chunk in retrieved_chunks
        if isinstance(chunk, dict) and chunk.get("is_cited_evidence")
    )
    evidence_coverage = (cited_count / evidence_count) if evidence_count else 0.0

    guard_override_labels = policy_output.get("guard_override_labels") or []
    if not isinstance(guard_override_labels, list):
        guard_override_labels = []

    requested = policy_output.get("decision_requested") or policy_output.get("progression")
    applied = policy_output.get("decision_applied") or policy_output.get("progression_applied") or requested

    return {
        "session_id": str(getattr(turn, "session_id", "")),
        "turn_id": str(getattr(turn, "id", "")),
        "turn_index": getattr(turn, "turn_index", None),
        "objective_id": policy_output.get("objective_id") or "",
        "step_type": getattr(turn, "current_step", None),
        "policy_state": {
            "current_step_index": getattr(turn, "current_step_index", None),
            "target_concepts": getattr(turn, "target_concepts", None),
            "mastery_before": getattr(turn, "mastery_before", None),
            "mastery_after": getattr(turn, "mastery_after", None),
        },
        "policy_action": policy_output.get("action") or getattr(turn, "pedagogical_action", None),
        "decision_requested": requested,
        "decision_applied": applied,
        "student_intent": policy_output.get("student_intent"),
        "guard_override_labels": guard_override_labels,
        "evidence_metrics": {
            "retrieved_count": evidence_count,
            "cited_count": cited_count,
            "coverage": round(evidence_coverage, 6),
        },
        "outcome": {
            "overall_score": evaluator_output.get("score"),
            "correctness_label": evaluator_output.get("label"),
            "turn_reward": _safe_float(getattr(turn, "rl_reward", None), 0.0),
            "session_complete": False,
        },
        "delegation": {
            "delegated": bool(policy_output.get("delegated", False)),
            "reason": policy_output.get("delegation_reason"),
            "outcome": policy_output.get("delegation_outcome"),
        },
    }


def build_policy_replay_rows(turns: Sequence[Any]) -> list[dict[str, Any]]:
    return [build_policy_replay_row(turn) for turn in turns]


def summarize_policy_replay(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    total = len(rows)
    if total == 0:
        return {
            "total_turns": 0,
            "guard_override_rate": 0.0,
            "delegation_rate": 0.0,
            "average_evidence_coverage": 0.0,
            "decision_alignment_rate": 0.0,
        }

    guard_override_turns = sum(1 for row in rows if row.get("guard_override_labels"))
    delegated_turns = sum(1 for row in rows if (row.get("delegation") or {}).get("delegated"))
    aligned_turns = sum(
        1
        for row in rows
        if row.get("decision_requested") == row.get("decision_applied")
    )
    avg_coverage = sum(
        _safe_float((row.get("evidence_metrics") or {}).get("coverage"), 0.0)
        for row in rows
    ) / total

    return {
        "total_turns": total,
        "guard_override_rate": round(guard_override_turns / total, 6),
        "delegation_rate": round(delegated_turns / total, 6),
        "average_evidence_coverage": round(avg_coverage, 6),
        "decision_alignment_rate": round(aligned_turns / total, 6),
    }


def export_policy_replay_jsonl(rows: Sequence[dict[str, Any]], output_path: str | Path) -> int:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")
    return len(rows)
