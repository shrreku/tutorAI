from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.tutor import _serialize_turn


def test_serialize_turn_includes_retrieved_chunks_and_evidence_payloads():
    turn = SimpleNamespace(
        id=uuid4(),
        turn_index=2,
        student_message="Explain Bayes theorem",
        tutor_response="Bayes updates prior beliefs with evidence.",
        tutor_question="What is a prior probability?",
        pedagogical_action="explain",
        progression_decision=1,
        current_step="define",
        current_step_index=1,
        latency_ms=421,
        policy_output={"evidence_chunk_ids": ["chunk-1", "chunk-2"]},
        evaluator_output={"overall_score": 0.6},
        retrieved_chunks=[
            {
                "chunk_id": "chunk-1",
                "text": "Bayes theorem relates prior and posterior probabilities.",
                "is_cited_evidence": True,
            }
        ],
        created_at="2026-02-20T00:00:00Z",
    )

    payload = _serialize_turn(turn)

    assert payload["retrieved_chunks"] == turn.retrieved_chunks
    assert payload["policy_output"] == turn.policy_output
    assert payload["turn_index"] == 2
    assert payload["current_step_index"] == 1
