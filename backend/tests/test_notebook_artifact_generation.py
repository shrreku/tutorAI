import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.notebooks import SUPPORTED_ARTIFACT_TYPES
from app.schemas.api import NotebookProgressResponse
from app.services.notebook_artifacts import NotebookArtifactService


def _sample_sessions():
    return [
        SimpleNamespace(
            id=uuid4(),
            status="active",
            plan_state={
                "active_topic": "Thermodynamics",
                "mode": "learn",
                "session_overview": "Studied entropy and enthalpy tradeoffs.",
                "focus_concepts": ["entropy", "enthalpy"],
            },
            mastery={"entropy": 0.32, "enthalpy": 0.61},
        ),
        SimpleNamespace(
            id=uuid4(),
            status="completed",
            plan_state={
                "active_topic": "Kinematics",
                "mode": "practice",
                "session_overview": "Reviewed velocity using simple motion questions.",
                "focus_concepts": ["velocity"],
            },
            mastery={"velocity": 0.45},
        ),
    ]


def _sample_turns(sessions):
    return {
        str(sessions[0].id): [
            SimpleNamespace(tutor_response="Entropy measures disorder in a system.")
        ],
        str(sessions[1].id): [
            SimpleNamespace(tutor_response="Velocity is displacement over time.")
        ],
    }


def _sample_progress():
    return NotebookProgressResponse(
        notebook_id=uuid4(),
        mastery_snapshot={"entropy": 0.32, "velocity": 0.45},
        objective_progress_snapshot={},
        weak_concepts_snapshot=["entropy", "velocity"],
        sessions_count=2,
        completed_sessions_count=1,
    )


@pytest.mark.parametrize("artifact_type", sorted(SUPPORTED_ARTIFACT_TYPES))
def test_build_artifact_payload_supported_types(artifact_type: str):
    sessions = _sample_sessions()
    service = NotebookArtifactService()
    payload = asyncio.run(
        service.generate_payload(
            artifact_type=artifact_type,
            notebook=SimpleNamespace(title="Physics Notebook", goal="Prepare for exam"),
            sessions=sessions,
            turns_by_session=_sample_turns(sessions),
            progress=_sample_progress(),
            source_resource_names=["thermo.pdf", "kinematics.md"],
            options={"difficulty": "medium"},
        )
    )

    assert payload["artifact_type"] == artifact_type
    assert "generated_at" in payload
    assert payload["options"]["difficulty"] == "medium"
    assert "progress_context" in payload


def test_build_artifact_payload_rejects_unsupported_type():
    service = NotebookArtifactService()
    with pytest.raises(ValueError, match="Unsupported artifact_type"):
        asyncio.run(
            service.generate_payload(
                artifact_type="mind_map",
                notebook=SimpleNamespace(
                    title="Physics Notebook", goal="Prepare for exam"
                ),
                sessions=_sample_sessions(),
                turns_by_session={},
                progress=_sample_progress(),
                source_resource_names=["thermo.pdf"],
                options={},
            )
        )


def test_build_artifact_payload_skips_llm_when_no_sessions():
    called = {"llm": 0}

    class _LLM:
        model_id = "test-model"

        async def generate_json(self, **_kwargs):
            called["llm"] += 1
            raise AssertionError("LLM path should not run without session context")

    service = NotebookArtifactService(_LLM())
    payload = asyncio.run(
        service.generate_payload(
            artifact_type="notes",
            notebook=SimpleNamespace(title="Physics Notebook", goal="Prepare for exam"),
            sessions=[],
            turns_by_session={},
            progress=NotebookProgressResponse(
                notebook_id=uuid4(),
                mastery_snapshot={},
                objective_progress_snapshot={},
                weak_concepts_snapshot=[],
                sessions_count=0,
                completed_sessions_count=0,
            ),
            source_resource_names=["thermo.pdf"],
            options={},
        )
    )

    assert called["llm"] == 0
    assert payload["generation"]["strategy"] == "deterministic_fallback"
    assert payload["generation"]["fallback_reason"] == "insufficient_session_context"
    assert "No tutoring sessions" in payload["summary"]
