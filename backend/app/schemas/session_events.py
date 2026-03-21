"""Typed live session event contracts (PROD-012).

Canonical event families for the study workspace. Frontend and backend
share these shapes so the workspace UI can render structured state
changes instead of parsing raw tutor text.

Events are grouped into families:
  - session.*      – session lifecycle
  - tutor.*        – tutor message streaming
  - objective.*    – learning objective updates
  - mastery.*      – concept mastery changes
  - artifact.*     – generated artifact lifecycle
  - checkpoint.*   – understanding checkpoints
  - source.*       – citation / source metadata
  - warning.*      – operational warnings
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Event type enum
# ---------------------------------------------------------------------------


class SessionEventType(str, Enum):
    # Session lifecycle
    SESSION_STARTED = "session.started"
    SESSION_RESUMED = "session.resumed"
    SESSION_COMPLETED = "session.completed"
    SESSION_BRIEF = "session.brief"

    # Tutor message
    TUTOR_MESSAGE_DELTA = "tutor.message.delta"
    TUTOR_MESSAGE_COMPLETED = "tutor.message.completed"

    # Objectives
    OBJECTIVE_UPDATED = "session.objective.updated"
    OBJECTIVE_COMPLETED = "session.objective.completed"

    # Mastery
    MASTERY_UPDATED = "session.mastery.updated"

    # Artifacts
    ARTIFACT_STARTED = "artifact.started"
    ARTIFACT_UPDATED = "artifact.updated"
    ARTIFACT_COMPLETED = "artifact.completed"

    # Checkpoints
    CHECKPOINT_REQUESTED = "checkpoint.requested"
    CHECKPOINT_RESPONSE_RECEIVED = "checkpoint.response.received"

    # Sources / citations
    SOURCE_CITATION_AVAILABLE = "source.citation.available"

    # Warnings
    WARNING_MODEL_REROUTED = "warning.model_rerouted"
    WARNING_RATE_LIMITED = "warning.rate_limited"


# ---------------------------------------------------------------------------
# Payload shapes
# ---------------------------------------------------------------------------


class SessionBriefPayload(BaseModel):
    """Sent at session start with context summary."""

    notebook_id: UUID
    session_id: UUID
    mode: str
    scope_type: str = "notebook"
    resource_count: int = 0
    objectives_count: int = 0
    objectives: List[ObjectiveSnapshot] = Field(default_factory=list)
    mastery_snapshot: Dict[str, float] = Field(default_factory=dict)
    weak_concepts: List[str] = Field(default_factory=list)
    session_overview: Optional[str] = None


class ObjectiveSnapshot(BaseModel):
    """Snapshot of a learning objective."""

    objective_id: str
    title: str
    description: Optional[str] = None
    primary_concepts: List[str] = Field(default_factory=list)
    support_concepts: List[str] = Field(default_factory=list)
    prereq_concepts: List[str] = Field(default_factory=list)
    step_count: int = 0
    status: str = "pending"  # pending | active | completed | skipped
    progress_pct: float = 0.0


class TutorMessageDeltaPayload(BaseModel):
    """Incremental tutor text chunk for streaming."""

    turn_id: str
    delta: str
    content_type: str = "text"  # text | markdown | latex | concept_card | quiz_card


class TutorMessageCompletedPayload(BaseModel):
    """Final tutor message with structured metadata."""

    turn_id: str
    response: str
    tutor_question: Optional[str] = None
    content_type: str = "text"
    current_step: Optional[str] = None
    current_step_index: int = 0
    objective_id: Optional[str] = None
    objective_title: Optional[str] = None
    step_transition: Optional[str] = None
    focus_concepts: List[str] = Field(default_factory=list)
    pedagogical_action: Optional[str] = None
    structured_content: Optional[List[StructuredContentBlock]] = None


class StructuredContentBlock(BaseModel):
    """A block of structured content within a tutor message."""

    block_type: (
        str  # text | concept_card | quiz_card | checkpoint | latex | diagram | code
    )
    content: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ObjectiveUpdatedPayload(BaseModel):
    """Objective progress changed."""

    objective_id: str
    title: str
    status: str  # pending | active | completed | skipped
    progress_pct: float = 0.0
    attempts: int = 0
    correct: int = 0


class MasteryUpdatedPayload(BaseModel):
    """Concept mastery changed."""

    concept_id: str
    previous_score: float = 0.0
    new_score: float = 0.0
    delta: float = 0.0


class ArtifactEventPayload(BaseModel):
    """Artifact lifecycle event."""

    artifact_id: str
    artifact_type: str  # notes | flashcards | quiz | revision_plan | concept_card
    status: str  # generating | ready | error
    payload_json: Optional[Dict[str, Any]] = None
    source_session_ids: List[str] = Field(default_factory=list)
    source_resource_ids: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class CheckpointRequestedPayload(BaseModel):
    """Tutor requests understanding check from student."""

    checkpoint_id: str
    checkpoint_type: str = "understanding"  # understanding | recall | application
    question: str
    concept_id: Optional[str] = None
    options: List[str] = Field(default_factory=list)
    allow_freeform: bool = True


class CheckpointResponsePayload(BaseModel):
    """Student responded to a checkpoint."""

    checkpoint_id: str
    response: str
    is_correct: Optional[bool] = None
    score: Optional[float] = None
    feedback: Optional[str] = None


class SourceCitationPayload(BaseModel):
    """Source reference attached to tutor content."""

    citation_id: str
    resource_id: str
    resource_name: Optional[str] = None
    chunk_ids: List[str] = Field(default_factory=list)
    page_numbers: List[int] = Field(default_factory=list)
    snippet: Optional[str] = None


class WarningPayload(BaseModel):
    """Operational warning surfaced to UI."""

    warning_type: str
    message: str
    selected_model_id: Optional[str] = None
    routed_model_id: Optional[str] = None
    reroute_reason: Optional[str] = None


class SessionCompletedPayload(BaseModel):
    """Session completion summary."""

    session_id: UUID
    summary_text: Optional[str] = None
    concepts_strong: List[str] = Field(default_factory=list)
    concepts_developing: List[str] = Field(default_factory=list)
    concepts_to_revisit: List[str] = Field(default_factory=list)
    objectives: List[ObjectiveSnapshot] = Field(default_factory=list)
    mastery_snapshot: Dict[str, float] = Field(default_factory=dict)
    turn_count: int = 0
    recommended_next: Optional[str] = None


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


class SessionEvent(BaseModel):
    """Canonical event envelope for the live study workspace."""

    event_type: SessionEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    session_id: UUID
    notebook_id: Optional[UUID] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    is_persistent: bool = False  # True = stored in DB, False = transient


# ---------------------------------------------------------------------------
# Helper to construct events
# ---------------------------------------------------------------------------


def make_event(
    event_type: SessionEventType,
    session_id: UUID,
    payload: BaseModel | Dict[str, Any],
    *,
    notebook_id: UUID | None = None,
    is_persistent: bool = False,
) -> SessionEvent:
    payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload
    return SessionEvent(
        event_type=event_type,
        session_id=session_id,
        notebook_id=notebook_id,
        payload=payload_dict,
        is_persistent=is_persistent,
    )
