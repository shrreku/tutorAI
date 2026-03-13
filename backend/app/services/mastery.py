"""
Mastery Service - TICKET-027

Handles mastery calculations and updates per REBUILD-04.
"""

ROLE_WEIGHTS = {
    "primary": 1.0,
    "support": 0.7,
    "prereq": 0.5,
}


def apply_mastery_deltas(
    current_mastery: dict[str, float],
    concept_deltas: dict[str, dict],
    alpha: float = 0.7,
) -> dict[str, float]:
    """
    Apply mastery deltas from evaluation.

    Formula: new = old + alpha * role_weight * weight * delta

    Args:
        current_mastery: Current mastery values by concept
        concept_deltas: Per-concept evaluation results with delta, weight, role
        alpha: Learning rate (default 0.7)

    Returns:
        Updated mastery dict (values clamped to [0, 1])
    """
    updated = dict(current_mastery)

    for concept, delta_info in concept_deltas.items():
        role_weight = delta_info.get("role_weight") or ROLE_WEIGHTS.get(
            delta_info.get("role", "support"), 0.7
        )
        weight = delta_info.get("weight", 1.0)
        delta = delta_info.get("delta", 0.0)

        change = alpha * role_weight * weight * delta
        old_value = updated.get(concept, 0.0)
        new_value = max(0.0, min(1.0, old_value + change))
        updated[concept] = new_value

    return updated


def compute_average_mastery(
    mastery: dict[str, float],
    concepts: list[str],
) -> float:
    """Compute average mastery for a set of concepts."""
    if not concepts:
        return 0.0
    values = [mastery.get(c, 0.0) for c in concepts]
    return sum(values) / len(values)


def check_success_criteria(
    progress: dict,
    criteria: dict,
    mastery: dict[str, float],
    primary_concepts: list[str],
) -> bool:
    """
    Check if success criteria for an objective are met.

    Args:
        progress: ObjectiveProgress with attempts, correct count
        criteria: SuccessCriteria with min_correct, min_mastery
        mastery: Current mastery values
        primary_concepts: Primary concepts for the objective

    Returns:
        True if criteria are met
    """
    if progress.get("correct", 0) < criteria.get("min_correct", 2):
        return False

    avg_mastery = compute_average_mastery(mastery, primary_concepts)
    return avg_mastery >= criteria.get("min_mastery", 0.7)


def check_prereq_gate(
    mastery: dict[str, float],
    prereq_concepts: list[str],
    threshold: float = 0.5,
) -> bool:
    """
    Check if prerequisite concepts have sufficient mastery to proceed.

    Args:
        mastery: Current mastery values
        prereq_concepts: List of prerequisite concept IDs
        threshold: Minimum average mastery required (default 0.5)

    Returns:
        True if prereq gate passes
    """
    if not prereq_concepts:
        return True

    avg_prereq_mastery = compute_average_mastery(mastery, prereq_concepts)
    return avg_prereq_mastery >= threshold


def compute_mastery_delta_from_score(
    score: float,
    current_mastery: float,
    correctness_label: str,
) -> float:
    """
    Compute mastery delta based on evaluation score.

    Args:
        score: Overall evaluation score (0-1)
        current_mastery: Current mastery value
        correctness_label: correct|partial|incorrect|unclear

    Returns:
        Delta value (can be negative for incorrect)
    """
    base_deltas = {
        "correct": 0.15,
        "partial": 0.05,
        "incorrect": -0.1,
        "unclear": 0.0,
    }

    base = base_deltas.get(correctness_label, 0.0)

    # Scale by score and current mastery
    # Higher mastery = smaller gains, larger losses
    if base > 0:
        # Diminishing returns at higher mastery
        scale = 1.0 - (current_mastery * 0.5)
    else:
        # Larger impact at lower mastery for incorrect
        scale = 1.0 + (current_mastery * 0.3)

    return base * scale * score
