from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TurnResult:
    """Result of executing a tutoring turn."""

    turn_id: str
    tutor_response: str
    tutor_question: Optional[str]
    action: str
    current_step: str
    current_step_index: int
    concept: str
    focus_concepts: list[str]
    mastery: dict[str, float]
    mastery_delta: dict[str, float]
    objective_progress: dict
    session_complete: bool
    awaiting_evaluation: bool
    objective_id: str = ""
    objective_title: str = ""
    step_transition: Optional[str] = None  # e.g. "step:1→2", "objective:0→1"
    retrieved_chunks: list[dict] = field(default_factory=list)
    evidence_chunk_ids: list[str] = field(default_factory=list)
    degraded_mode: bool = False
    guard_events: list[dict] = field(default_factory=list)
    decision_requested: Optional[str] = None
    decision_applied: Optional[str] = None
    delegated: bool = False
    delegation_reason: Optional[str] = None
    delegation_outcome: Optional[str] = None
    telemetry_contract: dict[str, Any] = field(default_factory=dict)
    progression_contract: dict[str, Any] = field(default_factory=dict)
    retrieval_contract: dict[str, Any] = field(default_factory=dict)
    response_contract: dict[str, Any] = field(default_factory=dict)
    study_map_delta: Optional[dict[str, Any]] = None
    # Live study map snapshot (populated every turn)
    study_map_snapshot: Optional[dict[str, Any]] = None
    # Structured citations from retrieved chunks
    citations: list[dict[str, Any]] = field(default_factory=list)
    # Session summary data (populated on session_complete)
    session_summary: Optional[dict[str, Any]] = None
    # Token usage tracking (CM-005)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    stage_token_usage: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class StageContext:
    """Canonical context shared across runtime stages within a turn."""

    session: Any
    plan: dict[str, Any]
    current_objective: dict[str, Any]
    objective_index: int
    step_index: int
    student_message: str
    focus_concepts: list[str]
    mastery_snapshot: dict[str, float]
    notebook_id: Optional[str] = None
    notebook_resource_ids: list[str] = field(default_factory=list)
    scope_type: Optional[str] = None
    scope_resource_ids: list[str] = field(default_factory=list)


@dataclass
class PolicyStageResult:
    """Typed handoff payload emitted by policy stage."""

    policy_output: Any
    effective_step_type: str
    target_concepts: list[str]
    policy_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalStageResult:
    """Typed handoff payload emitted by retrieval stage."""

    retrieved_chunks: list[Any]
    evidence_chunk_ids: list[str]
    retrieval_contract: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResponseStageResult:
    """Typed handoff payload emitted by response generation stage."""

    tutor_output: Any
