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


class KnowledgeBaseConceptOverride(BaseModel):
    """Editable concept-level override for a resource KB."""
    model_config = ConfigDict(extra="forbid")

    concept_id: str = Field(min_length=1)
    concept_type: Optional[str] = None
    bloom_level: Optional[str] = None
    importance_score: Optional[float] = None
    topo_order: Optional[int] = None


class KnowledgeBaseEdgeUpdate(BaseModel):
    """Edge payload used for graph edit operations."""
    model_config = ConfigDict(extra="forbid")

    source_concept_id: str = Field(min_length=1)
    target_concept_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    assoc_weight: Optional[float] = None
    confidence: Optional[float] = None


class KnowledgeBaseConceptRename(BaseModel):
    """Rename operation for concept ids."""
    model_config = ConfigDict(extra="forbid")

    from_concept_id: str = Field(min_length=1)
    to_concept_id: str = Field(min_length=1)


class KnowledgeBaseGraphOps(BaseModel):
    """Operation-based graph editing payload."""
    model_config = ConfigDict(extra="forbid")

    add_concepts: List[str] = Field(default_factory=list)
    remove_concepts: List[str] = Field(default_factory=list)
    rename_concepts: List[KnowledgeBaseConceptRename] = Field(default_factory=list)
    add_edges: List[KnowledgeBaseEdgeUpdate] = Field(default_factory=list)
    remove_edges: List[KnowledgeBaseEdgeUpdate] = Field(default_factory=list)


class KnowledgeBaseTopicBundleUpdate(BaseModel):
    """Editable topic bundle payload for KB curation."""
    model_config = ConfigDict(extra="forbid")

    topic_id: str = Field(min_length=1)
    topic_name: str = Field(min_length=1)
    primary_concepts: List[str] = Field(default_factory=list)
    support_concepts: List[str] = Field(default_factory=list)
    prereq_topic_ids: List[str] = Field(default_factory=list)


class KnowledgeBaseUpdateRequest(BaseModel):
    """Request payload for updating curated KB metadata."""
    model_config = ConfigDict(extra="forbid")

    topic: Optional[str] = None
    concept_overrides: List[KnowledgeBaseConceptOverride] = Field(default_factory=list)
    topic_bundles: Optional[List[KnowledgeBaseTopicBundleUpdate]] = None
    graph_ops: Optional[KnowledgeBaseGraphOps] = None


class KnowledgeBaseConceptResponse(BaseModel):
    """Concept row returned to KB management UI."""
    model_config = ConfigDict(extra="forbid")

    concept_id: str
    teach_count: int
    mention_count: int
    importance_score: Optional[float] = None
    concept_type: Optional[str] = None
    bloom_level: Optional[str] = None
    topo_order: Optional[int] = None


class KnowledgeBaseEdgeResponse(BaseModel):
    """Concept graph edge returned to KB editor."""
    model_config = ConfigDict(extra="forbid")

    source_concept_id: str
    target_concept_id: str
    relation_type: str
    assoc_weight: float
    confidence: float


class KnowledgeBaseTopicBundleResponse(BaseModel):
    """Topic bundle row returned to KB management UI."""
    model_config = ConfigDict(extra="forbid")

    topic_id: str
    topic_name: str
    primary_concepts: List[str] = Field(default_factory=list)
    support_concepts: List[str] = Field(default_factory=list)
    prereq_topic_ids: List[str] = Field(default_factory=list)


class ResourceKnowledgeBaseResponse(BaseModel):
    """Detailed, editable KB snapshot for a resource."""
    model_config = ConfigDict(extra="forbid")

    resource_id: UUID
    resource_name: str
    topic: Optional[str] = None
    status: str
    chunk_count: int
    concept_count: int
    graph_edge_count: int
    concepts: List[KnowledgeBaseConceptResponse] = Field(default_factory=list)
    edges: List[KnowledgeBaseEdgeResponse] = Field(default_factory=list)
    topic_bundles: List[KnowledgeBaseTopicBundleResponse] = Field(default_factory=list)
    latest_job: Optional[IngestionStatusResponse] = None


# Session API schemas
class SessionCreate(BaseModel):
    """Request to create a session."""
    model_config = ConfigDict(extra="forbid")
    
    resource_id: UUID
    topic: Optional[str] = None
    selected_topics: Optional[List[str]] = None
    consent_training: Optional[bool] = Field(
        default=None,
        description="Explicit opt-in for training data collection. Must be true for session data to be eligible for model improvement.",
    )


class UserSettingsResponse(BaseModel):
    """Current settings for the authenticated user."""
    model_config = ConfigDict(extra="forbid")

    consent_training_global: bool = False
    consent_preference_set: bool = False


class UserSettingsUpdateRequest(BaseModel):
    """Partial update for user settings."""
    model_config = ConfigDict(extra="forbid")

    consent_training_global: Optional[bool] = None


class CreditEstimateRequest(BaseModel):
    """Estimate request for token-based credit charging."""
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    uses_ocr: bool = False
    uses_web_search: bool = False


class CreditEstimateResponse(BaseModel):
    """Estimated credit charge and breakdown."""
    model_config = ConfigDict(extra="forbid")

    credits_enabled: bool
    estimated_credits: int
    input_component: int
    output_component: int
    ocr_surcharge: int
    web_search_surcharge: int


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
    consent_training: bool = False
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
    session_summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Session summary data when session_complete=True. Contains summary_text, concepts_strong/developing/to_revisit, objectives, mastery_snapshot.",
    )


class SessionSummaryResponse(BaseModel):
    """Standalone session summary retrieved after completion."""
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    status: str
    topic: Optional[str] = None
    turn_count: int = 0
    summary_text: Optional[str] = None
    concepts_strong: List[str] = Field(default_factory=list)
    concepts_developing: List[str] = Field(default_factory=list)
    concepts_to_revisit: List[str] = Field(default_factory=list)
    objectives: List[Dict[str, Any]] = Field(default_factory=list)
    mastery_snapshot: Dict[str, float] = Field(default_factory=dict)


# ── Quiz schemas ───────────────────────────────────────────────────────

class QuizQuestionResponse(BaseModel):
    """A single quiz question (without the correct answer — sent to frontend)."""
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_text: str
    question_type: str = "multiple_choice"
    options: List[str] = Field(default_factory=list)
    concept: str = ""
    difficulty: str = "medium"


class QuizGenerateRequest(BaseModel):
    """Request to generate a quiz from a session."""
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    num_questions: int = Field(default=5, ge=1, le=15)


class QuizGenerateResponse(BaseModel):
    """Response with generated quiz questions."""
    model_config = ConfigDict(extra="forbid")

    quiz_id: str
    session_id: UUID
    topic: Optional[str] = None
    quiz_focus: str = ""
    questions: List[QuizQuestionResponse] = Field(default_factory=list)
    total_questions: int = 0


class QuizAnswerRequest(BaseModel):
    """Submit an answer to a single quiz question."""
    model_config = ConfigDict(extra="forbid")

    quiz_id: str
    question_id: str
    answer: str = Field(..., min_length=1)


class QuizAnswerResponse(BaseModel):
    """Grading result for a single answer."""
    model_config = ConfigDict(extra="forbid")

    question_id: str
    is_correct: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str = ""
    correct_answer: str = ""
    explanation: str = ""


class QuizResultsResponse(BaseModel):
    """Full quiz results after all questions answered."""
    model_config = ConfigDict(extra="forbid")

    quiz_id: str
    session_id: UUID
    total_questions: int = 0
    answered: int = 0
    correct: int = 0
    score_percent: float = 0.0
    per_question: List[Dict[str, Any]] = Field(default_factory=list)
    concept_scores: Dict[str, float] = Field(default_factory=dict)
    summary: str = ""
