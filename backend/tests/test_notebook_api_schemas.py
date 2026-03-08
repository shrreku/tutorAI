import pytest
from pydantic import ValidationError

from app.schemas.api import (
    NotebookCreate,
    NotebookUpdate,
    NotebookResourceAttachRequest,
    NotebookSessionCreateRequest,
    NotebookProgressResponse,
    NotebookArtifactGenerateRequest,
    NotebookArtifactResponse,
)


def test_notebook_create_validates_required_title():
    payload = NotebookCreate(title="Physics 101", goal="Prepare for midterm")

    assert payload.title == "Physics 101"
    assert payload.goal == "Prepare for midterm"


def test_notebook_create_rejects_blank_title():
    with pytest.raises(ValidationError):
        NotebookCreate(title="")


def test_notebook_update_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        NotebookUpdate(title="Updated", unknown_field=True)


def test_notebook_resource_attach_defaults():
    payload = NotebookResourceAttachRequest(resource_id="123e4567-e89b-12d3-a456-426614174000")

    assert payload.role == "supplemental"
    assert payload.is_active is True


def test_notebook_session_create_defaults_mode():
    payload = NotebookSessionCreateRequest(resource_id="123e4567-e89b-12d3-a456-426614174000")

    assert payload.mode == "learn"
    assert payload.selected_resource_ids == []
    assert payload.notebook_wide is False


def test_notebook_progress_response_defaults():
    payload = NotebookProgressResponse(notebook_id="123e4567-e89b-12d3-a456-426614174000")

    assert payload.mastery_snapshot == {}
    assert payload.objective_progress_snapshot == {}
    assert payload.weak_concepts_snapshot == []
    assert payload.sessions_count == 0


def test_notebook_artifact_generate_request_requires_type():
    payload = NotebookArtifactGenerateRequest(artifact_type="notes")

    assert payload.artifact_type == "notes"
    assert payload.source_session_ids == []
    assert payload.options == {}


def test_notebook_artifact_response_round_trip():
    payload = NotebookArtifactResponse(
        id="123e4567-e89b-12d3-a456-426614174010",
        notebook_id="123e4567-e89b-12d3-a456-426614174000",
        artifact_type="flashcards",
        payload_json={"summary": "generated"},
        source_session_ids=["123e4567-e89b-12d3-a456-426614174011"],
        source_resource_ids=["123e4567-e89b-12d3-a456-426614174012"],
        created_at="2026-03-04T10:00:00Z",
        updated_at="2026-03-04T10:00:00Z",
    )

    assert payload.artifact_type == "flashcards"
    assert payload.payload_json["summary"] == "generated"
