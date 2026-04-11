from __future__ import annotations

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
    lifecycle_status: Optional[str] = None
    processing_profile: Optional[str] = None
    capabilities: Dict[str, bool | int] = Field(default_factory=dict)
    uploaded_at: datetime
    processed_at: Optional[datetime]
    latest_job: Optional[IngestionStatusResponse] = None


class ResourceArtifactResponse(BaseModel):
    """Internal preparation artifact metadata for a resource."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    resource_id: Optional[UUID] = None
    notebook_id: Optional[UUID] = None
    scope_type: str
    scope_key: str
    artifact_kind: str
    status: str
    version: str
    payload_json: Optional[Dict[str, Any]] = None
    source_chunk_ids: Optional[List[str]] = None
    content_hash: Optional[str] = None
    generated_at: datetime
    error_message: Optional[str] = None


class ResourceDetailResponse(ResourceResponse):
    """Detailed resource response with KB info."""

    model_config = ConfigDict(extra="forbid")

    chunk_count: int = 0
    concept_count: int = 0
    topic_bundles: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts: List[ResourceArtifactResponse] = Field(default_factory=list)


class IngestionBillingStatusResponse(BaseModel):
    """Billing lifecycle details attached to an ingestion job."""

    model_config = ConfigDict(extra="forbid")

    uses_platform_credits: bool = False
    estimated_credits: int = 0
    reserved_credits: int = 0
    actual_credits: Optional[int] = None
    status: str = "not_applicable"
    release_reason: Optional[str] = None
    file_size_bytes: int = 0


class IngestionCurriculumBillingStatusResponse(BaseModel):
    """Deferred curriculum-preparation billing attached to an ingestion job."""

    model_config = ConfigDict(extra="forbid")

    estimated_credits_low: int = 0
    estimated_credits_high: int = 0
    reserved_credits: int = 0
    actual_credits: Optional[int] = None
    status: str = "pending"
    operation_id: Optional[UUID] = None
    release_reason: Optional[str] = None


class IngestionAsyncByokStatusResponse(BaseModel):
    """Async BYOK escrow details attached to an ingestion job."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    escrow_id: Optional[UUID] = None
    provider_name: Optional[str] = None
    status: str = "disabled"
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class IngestionDocumentMetricsResponse(BaseModel):
    """Actual document metrics discovered during ingestion."""

    model_config = ConfigDict(extra="forbid")

    page_count_actual: int = 0
    section_count: int = 0
    chunk_count_actual: int = 0
    token_count_actual: int = 0


class IngestionBatchProgressResponse(BaseModel):
    """Per-batch processing progress for phased ingestion."""

    model_config = ConfigDict(extra="forbid")

    batch_index: int = 0
    status: str = "pending"
    ontology_status: str = "pending"
    enrichment_status: str = "pending"
    kb_merge_status: str = "pending"
    is_study_ready: bool = False
    concepts_admitted: int = 0
    graph_edges_created: int = 0


class IngestionCapabilityProgressResponse(BaseModel):
    """Session capability readiness unlocked by staged ingestion."""

    model_config = ConfigDict(extra="forbid")

    search_ready: bool = False
    doubt_ready: bool = False
    learn_ready: bool = False
    # Progressive batch readiness
    ready_batch_count: int = 0
    total_batch_count: int = 0
    progressive_study_ready: bool = False
    batches: List[IngestionBatchProgressResponse] = Field(default_factory=list)


class IngestionStatusResponse(BaseModel):
    """Ingestion job status response."""

    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    resource_id: UUID
    status: str
    job_kind: str = "core_ingest"
    requested_capability: Optional[str] = None
    scope_type: Optional[str] = None
    scope_key: Optional[str] = None
    current_stage: Optional[str]
    progress_percent: int
    error_message: Optional[str]
    error_stage: Optional[str] = None
    resumable: bool = False
    resume_hint: Optional[str] = None
    last_completed_stage: Optional[str] = None
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    document_metrics: Optional[IngestionDocumentMetricsResponse] = None
    capability_progress: Optional[IngestionCapabilityProgressResponse] = None
    billing: Optional[IngestionBillingStatusResponse] = None
    curriculum_billing: Optional[IngestionCurriculumBillingStatusResponse] = None
    async_byok: Optional[IngestionAsyncByokStatusResponse] = None


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


# Learner personalization schemas
class LearnerPreferences(BaseModel):
    """Account-level learner preference defaults."""

    model_config = ConfigDict(extra="forbid")

    pace: Optional[str] = None
    depth: Optional[str] = None
    tutoring_style: Optional[str] = None
    hint_level: Optional[str] = None
    language: Optional[str] = None
    accessibility: Optional[Dict[str, Any]] = None


class NotebookPersonalization(BaseModel):
    """Notebook-scoped personalization preferences."""

    model_config = ConfigDict(extra="forbid")

    purpose: Optional[str] = None
    urgency: Optional[bool] = None
    study_pace: Optional[str] = None
    study_depth: Optional[str] = None
    practice_intensity: Optional[str] = None
    exam_context: Optional[str] = None


class SessionPersonalization(BaseModel):
    """Session-scoped personalization overrides."""

    model_config = ConfigDict(extra="forbid")

    time_budget_minutes: Optional[int] = None
    today_goal: Optional[str] = None
    interaction_style: Optional[str] = None
    confidence: Optional[str] = None
    want_hints: Optional[bool] = None
    want_examples: Optional[bool] = None


# Notebook API schemas
class NotebookCreate(BaseModel):
    """Request to create a notebook."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=256)
    goal: Optional[str] = None
    target_date: Optional[datetime] = None
    settings_json: Optional[Dict[str, Any]] = None
    personalization: Optional[NotebookPersonalization] = None


class NotebookUpdate(BaseModel):
    """Partial update for notebook metadata."""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, min_length=1, max_length=256)
    goal: Optional[str] = None
    target_date: Optional[datetime] = None
    status: Optional[str] = None
    settings_json: Optional[Dict[str, Any]] = None
    personalization: Optional[NotebookPersonalization] = None


class NotebookResponse(BaseModel):
    """Notebook response."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    student_id: UUID
    title: str
    goal: Optional[str] = None
    target_date: Optional[datetime] = None
    status: str
    settings_json: Optional[Dict[str, Any]] = None
    personalization: Optional[NotebookPersonalization] = None
    created_at: datetime
    updated_at: datetime


class NotebookResourceAttachRequest(BaseModel):
    """Request to attach resource to notebook."""

    model_config = ConfigDict(extra="forbid")

    resource_id: UUID
    role: str = "supplemental"
    is_active: bool = True


class NotebookResourceResponse(BaseModel):
    """Notebook-resource link response."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    notebook_id: UUID
    resource_id: UUID
    role: str
    is_active: bool
    added_at: datetime
    created_at: datetime
    updated_at: datetime
    resource: Optional[ResourceResponse] = None


class NotebookSessionCreateRequest(BaseModel):
    """Request to create a notebook-scoped tutoring session."""

    model_config = ConfigDict(extra="forbid")

    resource_id: UUID
    selected_resource_ids: List[UUID] = Field(default_factory=list)
    notebook_wide: bool = False
    topic: Optional[str] = None
    selected_topics: Optional[List[str]] = None
    mode: str = "learn"
    consent_training: Optional[bool] = Field(default=None)
    personalization: Optional[SessionPersonalization] = None
    curriculum_model_id: Optional[str] = None
    resume_existing: bool = Field(
        default=True,
        description="Resume the latest active session for this resource when available.",
    )


class NotebookSessionResponse(BaseModel):
    """Notebook-session mapping response."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    notebook_id: UUID
    session_id: UUID
    mode: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    mastery_avg: Optional[float] = None
    concepts_count: int = 0
    topic: Optional[str] = None

class NotebookSessionDetailResponse(BaseModel):
    """Notebook session detail with nested session metadata."""

    model_config = ConfigDict(extra="forbid")

    notebook_session: NotebookSessionResponse
    session: "SessionResponse"
    reused_existing: bool = False
    preparation_summary: Dict[str, Any] = Field(default_factory=dict)
    notebook_planning_state: Optional["NotebookPlanningStateResponse"] = None


class NotebookArtifactGenerateRequest(BaseModel):
    """Request to generate a notebook artifact from sessions/resources."""

    model_config = ConfigDict(extra="forbid")

    artifact_type: str = Field(min_length=1)
    source_session_ids: List[UUID] = Field(default_factory=list)
    source_resource_ids: List[UUID] = Field(default_factory=list)
    options: Optional[Dict[str, Any]] = None


class NotebookPlanningStateResponse(BaseModel):
    """Durable notebook-global planning, learner, and coverage state."""

    model_config = ConfigDict(extra="forbid")

    notebook_id: UUID
    revision: int = 1
    knowledge_state: Dict[str, Any] = Field(default_factory=dict)
    learner_state: Dict[str, Any] = Field(default_factory=dict)
    planner_state: Dict[str, Any] = Field(default_factory=dict)
    coverage_snapshot: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class NotebookArtifactResponse(BaseModel):
    """Notebook artifact payload returned by notebook artifact endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    notebook_id: UUID
    artifact_type: str
    payload_json: Dict[str, Any] = Field(default_factory=dict)
    source_session_ids: List[str] = Field(default_factory=list)
    source_resource_ids: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AsyncByokEscrowResponse(BaseModel):
    """Metadata describing an async BYOK escrow record."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    purpose_type: str
    purpose_id: Optional[UUID] = None
    scope_type: str
    scope_key: str
    provider_name: Optional[str] = None
    status: str
    expires_at: Optional[datetime] = None
    hard_delete_after: Optional[datetime] = None
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    deletion_reason: Optional[str] = None


class NotebookProgressResponse(BaseModel):
    """Notebook-level progress summary."""

    model_config = ConfigDict(extra="forbid")

    notebook_id: UUID
    mastery_snapshot: Dict[str, float] = Field(default_factory=dict)
    objective_progress_snapshot: Dict[str, Any] = Field(default_factory=dict)
    weak_concepts_snapshot: List[str] = Field(default_factory=list)
    sessions_count: int = 0
    completed_sessions_count: int = 0
    coverage_snapshot: Dict[str, Any] = Field(default_factory=dict)
    notebook_planning_state: Optional["NotebookPlanningStateResponse"] = None
    updated_at: Optional[datetime] = None


class ObjectiveSummary(BaseModel):
    """Summary of a curriculum objective exposed in session responses."""

    model_config = ConfigDict(extra="forbid")

    objective_id: str
    title: str
    description: Optional[str] = None
    primary_concepts: List[str] = Field(default_factory=list)
    support_concepts: List[str] = Field(default_factory=list)
    prereq_concepts: List[str] = Field(default_factory=list)
    step_count: int = 0
    estimated_turns: int = 5


class CurriculumOverview(BaseModel):
    """High-level curriculum overview for a session."""

    model_config = ConfigDict(extra="forbid")

    active_topic: Optional[str] = None
    total_objectives: int = 0
    objectives: List[ObjectiveSummary] = Field(default_factory=list)
    session_overview: Optional[str] = None


class SessionCreate(BaseModel):
    """Legacy resource-first session create payload."""

    model_config = ConfigDict(extra="forbid")

    resource_id: UUID
    topic: Optional[str] = None
    selected_topics: Optional[List[str]] = None
    consent_training: Optional[bool] = None


class UserSettingsResponse(BaseModel):
    """User-level settings exposed to the frontend."""

    model_config = ConfigDict(extra="forbid")

    consent_training_global: bool
    consent_preference_set: bool
    consent_personalization: bool = True
    is_admin: bool = False
    async_byok_escrow_enabled: bool = False
    async_byok_escrow_backend: Optional[str] = None
    async_byok_escrow_ttl_minutes: int = 0
    parse_page_limit: int = 0
    parse_page_used: int = 0
    parse_page_reserved: int = 0
    parse_page_remaining: int = 0
    byok_api_key_set: Optional[bool] = None
    byok_api_base_url: Optional[str] = None
    learning_preferences: Optional[LearnerPreferences | Dict[str, Any]] = None


class UserSettingsUpdateRequest(BaseModel):
    """Patch payload for mutable user-level settings."""

    model_config = ConfigDict(extra="forbid")

    consent_training_global: Optional[bool] = None
    consent_personalization: Optional[bool] = None
    learning_preferences: Optional[LearnerPreferences] = None


class CreditEstimateRequest(BaseModel):
    """Estimate credit cost for a request based on token usage flags."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    uses_ocr: bool = False
    uses_web_search: bool = False


class CreditEstimateResponse(BaseModel):
    """Credit estimate breakdown."""

    model_config = ConfigDict(extra="forbid")

    credits_enabled: bool
    estimated_credits: int = 0
    input_component: int = 0
    output_component: int = 0
    ocr_surcharge: int = 0
    web_search_surcharge: int = 0


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
    plan_state: Optional[Dict[str, Any]] = None
    notebook_planning_state: Optional["NotebookPlanningStateResponse"] = None
    created_at: datetime


class CitationData(BaseModel):
    """Evidence citation attached to a tutor turn response."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str
    resource_id: Optional[str] = None
    chunk_id: str
    sub_chunk_id: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section_heading: Optional[str] = None
    snippet: str
    relevance_score: float
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class SessionDetailResponse(SessionResponse):
    """Detailed session response with plan state."""

    model_config = ConfigDict(extra="forbid")

    plan_state: Optional[Dict[str, Any]] = None
    turn_count: int = 0


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
    notebook_planning_state: Optional["NotebookPlanningStateResponse"] = None


class TutorTurnRequest(BaseModel):
    """Request payload for a tutor turn."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    message: str = Field(min_length=1)


class TutorTurnResponse(BaseModel):
    """Response payload for a tutor turn."""

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
    session_summary: Optional[Dict[str, Any]] = None
    progression_contract: Dict[str, Any] = Field(default_factory=dict)
    retrieval_contract: Dict[str, Any] = Field(default_factory=dict)
    response_contract: Dict[str, Any] = Field(default_factory=dict)
    structured_content: Optional[List[Dict[str, Any]]] = None
    study_map_delta: Optional[Dict[str, Any]] = None
    study_map_snapshot: Optional[Dict[str, Any]] = None
    citations: List[CitationData] = Field(default_factory=list)
    selected_model_id: Optional[str] = None
    routed_model_id: Optional[str] = None
    reroute_reason: Optional[str] = None


SessionResponse.model_rebuild()
NotebookSessionDetailResponse.model_rebuild()

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
