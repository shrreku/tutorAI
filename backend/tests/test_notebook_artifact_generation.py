import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.notebooks import (
    SUPPORTED_ARTIFACT_TYPES,
    _build_artifact_payload,
)
from app.schemas.api import NotebookProgressResponse


def _sample_sessions():
    return [
        SimpleNamespace(
            id=uuid4(),
            plan_state={"active_topic": "Thermodynamics"},
            mastery={"entropy": 0.32, "enthalpy": 0.61},
        ),
        SimpleNamespace(
            id=uuid4(),
            plan_state={"active_topic": "Kinematics"},
            mastery={"velocity": 0.45},
        ),
    ]


def _sample_turns(sessions):
    return {
        str(sessions[0].id): [SimpleNamespace(tutor_response="Entropy measures disorder in a system.")],
        str(sessions[1].id): [SimpleNamespace(tutor_response="Velocity is displacement over time.")],
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
    payload = asyncio.run(
        _build_artifact_payload(
            artifact_type=artifact_type,
            sessions=sessions,
            turns_by_session=_sample_turns(sessions),
            progress=_sample_progress(),
            options={"difficulty": "medium"},
        )
    )

    assert payload["artifact_type"] == artifact_type
    assert "generated_at" in payload
    assert payload["options"]["difficulty"] == "medium"
    assert "progress_context" in payload


def test_build_artifact_payload_rejects_unsupported_type():
    with pytest.raises(ValueError, match="Unsupported artifact_type"):
        asyncio.run(
            _build_artifact_payload(
                artifact_type="mind_map",
                sessions=_sample_sessions(),
                turns_by_session={},
                progress=_sample_progress(),
                options={},
            )
        )
