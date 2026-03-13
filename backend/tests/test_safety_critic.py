import asyncio
import time

from app.agents.safety_critic import SafetyCritic


class _SlowLLM:
    async def generate(self, **_kwargs):
        await asyncio.sleep(0.5)
        return "{}"


class _FailingLLM:
    async def generate(self, **_kwargs):
        raise RuntimeError("llm unavailable")


def test_safety_critic_times_out_and_falls_back():
    critic = SafetyCritic(_SlowLLM(), llm_timeout_seconds=0.1)

    started = time.time()
    result = asyncio.run(
        critic.evaluate(
            response_text="Probability is between 0 and 1. What does that imply?",
            retrieved_chunks=[
                {"chunk_id": "c1", "text": "Probability ranges from 0 to 1."}
            ],
            current_objective={
                "title": "Basics",
                "concept_scope": {"primary": ["probability"]},
            },
            student_message="I am not sure",
            cited_evidence_chunk_ids=["c1"],
        )
    )
    elapsed = time.time() - started

    assert elapsed < 0.4
    assert result.should_block is False
    assert result.contains_question is True
    assert result.safety_decision == "allow"


def test_safety_critic_exception_path_uses_heuristic_fallback():
    critic = SafetyCritic(_FailingLLM(), llm_timeout_seconds=0.1)

    result = asyncio.run(
        critic.evaluate(
            response_text="This is grounded content.",
            retrieved_chunks=[{"chunk_id": "c1", "text": "This is grounded content."}],
            current_objective={
                "title": "Basics",
                "concept_scope": {"primary": ["probability"]},
            },
            cited_evidence_chunk_ids=["c1"],
        )
    )

    assert result.is_safe is True
    assert result.should_block is False
    assert result.grounding_assessment in {"partial", "grounded", "ungrounded"}
    assert result.safety_decision == "allow"
