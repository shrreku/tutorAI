from app.services.tutoring_harness import (
    ScenarioDefinition,
    ScenarioTurn,
    build_markdown_report,
    evaluate_rubric,
)


def test_evaluate_rubric_scores_intent_evidence_and_safety():
    scenario = ScenarioDefinition(
        key="move_on_request",
        description="",
        turns=[
            ScenarioTurn("Can we move on?", "move_on"),
            ScenarioTurn("I am ready for next.", "move_on"),
        ],
    )
    turns = [
        {
            "turn_index": 0,
            "progression_decision": "ADVANCE_STEP",
            "step_transition": "step:0→1",
            "tutor_response": "Great, let's continue.",
            "policy_output": {
                "student_intent": "move_on",
                "evidence_chunk_ids": ["c1"],
                "guard_override_labels": ["forced_advance_max_turns"],
            },
            "retrieved_chunks": [{"chunk_id": "c1", "is_cited_evidence": True}],
        },
        {
            "turn_index": 1,
            "progression_decision": "ADVANCE_OBJECTIVE",
            "step_transition": "objective:0→1",
            "tutor_response": "Nice work, moving to the next objective.",
            "policy_output": {
                "student_intent": "move_on",
                "evidence_chunk_ids": [],
                "guard_override_labels": [],
            },
            "retrieved_chunks": [{"chunk_id": "c2", "is_cited_evidence": False}],
        },
    ]

    rubric, notes = evaluate_rubric(scenario, turns)

    assert rubric.progression_fluidity >= 0.7
    assert rubric.intent_responsiveness >= 1.0
    assert rubric.evidence_consistency >= 1.0
    assert rubric.safety_compliance == 1.0
    assert isinstance(notes, list)


def test_build_markdown_report_contains_summary_table():
    summary = {
        "started_at": "2026-02-20T10:00:00Z",
        "ended_at": "2026-02-20T10:10:00Z",
        "base_url": "http://localhost:8000",
        "resource_id": "resource-1",
        "overall_pass": True,
        "run_dir": "artifacts/tutoring_harness_v2/harness_run_20260220_101000",
        "scenarios": [
            {
                "scenario_key": "normal_learning",
                "pass_fail": True,
                "notes": [],
                "rubric": {
                    "progression_fluidity": 1.0,
                    "intent_responsiveness": 1.0,
                    "evidence_consistency": 0.9,
                    "guard_correctness": 1.0,
                    "safety_compliance": 1.0,
                },
            }
        ],
    }

    report = build_markdown_report(summary)

    assert "# Tutoring Harness v2 Report" in report
    assert (
        "| Scenario | Pass | Progression | Intent | Evidence | Guard | Safety | Notes |"
        in report
    )
    assert "normal_learning" in report
