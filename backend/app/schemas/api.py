from typing import List, Optional, Dict, Any, Generic, TypeVar
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""
    model_config = ConfigDict(extra="forbid")
    
    items: List[T]
    total: int
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    """Error detail for validation errors."""
    model_config = ConfigDict(extra="forbid")
    
    field: Optional[str] = None
    message: str


class ErrorResponse(BaseModel):
    """Canonical error response shape."""
    model_config = ConfigDict(extra="forbid")
    
    code: str
    message: str
    details: Optional[List[ErrorDetail]] = None
    request_id: Optional[str] = None


# Resource API schemas
class ResourceCreate(BaseModel):
    """Request to create/upload a resource."""
    model_config = ConfigDict(extra="forbid")
    
    filename: str
    topic: Optional[str] = None


class ResourceResponse(BaseModel):
    """Resource response."""
    model_config = ConfigDict(extra="forbid")
    
    id: UUID
    filename: str
    topic: Optional[str]
    status: str
    uploaded_at: datetime
    processed_at: Optional[datetime]


class ResourceDetailResponse(ResourceResponse):
    """Detailed resource response with KB info."""
    model_config = ConfigDict(extra="forbid")
    
    chunk_count: int = 0
    concept_count: int = 0
    topic_bundles: List[Dict[str, Any]] = Field(default_factory=list)


# Ingestion API schemas
class IngestionStatusResponse(BaseModel):
    """Ingestion job status response."""
    model_config = ConfigDict(extra="forbid")
    
    job_id: UUID
    resource_id: UUID
    status: str
    current_stage: Optional[str]
    progress_percent: int
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


# Session API schemas
class SessionCreate(BaseModel):
    """Request to create a session."""
    model_config = ConfigDict(extra="forbid")
    
    resource_id: UUID
    topic: Optional[str] = None
    selected_topics: Optional[List[str]] = None


class ObjectiveSummary(BaseModel):
    """Brief summary of a learning objective for the frontend."""
    model_config = ConfigDict(extra="forbid")

    objective_id: str
    title: str
    description: Optional[str] = None
    primary_concepts: List[str] = Field(default_factory=list)
    estimated_turns: int = 5


class CurriculumOverview(BaseModel):
    """Overview of the curriculum plan returned at session creation."""
    model_config = ConfigDict(extra="forbid")

    active_topic: Optional[str] = None
    total_objectives: int = 0
    objectives: List[ObjectiveSummary] = Field(default_factory=list)
    session_overview: Optional[str] = None


class SessionResponse(BaseModel):
    """Session response."""
    model_config = ConfigDict(extra="forbid")
    
    id: UUID
    user_id: Optional[UUID] = None
    resource_id: Optional[UUID] = None
    topic: Optional[str] = None
    status: str
    current_step: Optional[str] = None
    current_concept_id: Optional[str] = None
    mastery: Optional[Dict[str, float]] = None
    curriculum_overview: Optional[CurriculumOverview] = None
    created_at: datetime


class SessionDetailResponse(SessionResponse):
    """Detailed session response with plan state."""
    model_config = ConfigDict(extra="forbid")
    
    plan_state: Optional[Dict[str, Any]] = None
    turn_count: int = 0


# Tutor API schemas
class TutorTurnRequest(BaseModel):
    """Request for a tutoring turn."""
    model_config = ConfigDict(extra="forbid")
    
    session_id: UUID
    message: str = Field(..., min_length=1)


class TutorTurnResponse(BaseModel):
    """Response from a tutoring turn."""
    model_config = ConfigDict(extra="forbid")
    
    turn_id: UUID
    response: str
    tutor_question: Optional[str] = None
    current_step: Optional[str] = None
    current_step_index: int = 0
    objective_id: Optional[str] = None
    objective_title: Optional[str] = None
    step_transition: Optional[str] = None
    focus_concepts: List[str] = Field(default_factory=list)
    mastery_update: Optional[Dict[str, float]] = None
    evaluation: Optional[Dict[str, Any]] = None
    session_complete: bool = False
    awaiting_evaluation: bool = False
