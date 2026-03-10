from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class PolicyState(BaseModel):
    """Input to the Policy Agent."""
    model_config = ConfigDict(extra="ignore")

    student_message: str
    session_mode: str = Field(default="learn", description="Requested session mode: learn, doubt, practice, revision")
    current_step_index: int = Field(
        default=0,
        ge=0,
        serialization_alias="current_step_index",
        description="Canonical progression pointer into step_roadmap",
    )
    current_step: str = Field(default="explain", description="Human-readable step type derived from step_roadmap[current_step_index].type")
    curriculum_slice: Dict[str, Any] = Field(default_factory=dict)
    concept_scope: Dict[str, Any] = Field(default_factory=dict)
    focus_concepts: List[str] = Field(default_factory=list)
    mastery_snapshot: Dict[str, float] = Field(default_factory=dict, description="Concept → mastery mapping (0-1)")
    recent_turns: List[Dict[str, Any]] = Field(default_factory=list)
    latest_evaluation: Optional[Dict[str, Any]] = None
    # Full plan context so policy can navigate objectives fluently
    current_objective_index: int = Field(default=0, ge=0)
    total_objectives: int = Field(default=1, ge=1)
    objective_queue_summary: List[Dict[str, Any]] = Field(default_factory=list, description="Brief summary of all objectives [{id, title, primary_concepts}]")
    turns_at_step: int = Field(default=0, ge=0)
    ad_hoc_count: int = Field(
        default=0,
        ge=0,
        serialization_alias="ad_hoc_count",
    )
    max_ad_hoc_per_objective: int = Field(
        default=4,
        ge=1,
        serialization_alias="max_ad_hoc_per_objective",
    )
    last_decision: Optional[str] = None


class TutorState(BaseModel):
    """Input to the Tutor Agent."""
    model_config = ConfigDict(extra="ignore")

    student_message: str
    session_mode: str = Field(default="learn", description="Requested session mode: learn, doubt, practice, revision")
    current_step_index: int = Field(
        default=0,
        ge=0,
        serialization_alias="current_step_index",
        description="Canonical progression pointer into step_roadmap",
    )
    current_step: str = Field(default="explain", description="Human-readable step type derived from step_roadmap[current_step_index].type")
    effective_step_type: Optional[str] = Field(
        default=None,
        description="Runtime-effective step type after policy ad-hoc overrides",
    )
    curriculum_slice: Dict[str, Any] = Field(default_factory=dict)
    retrieved_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_chunk_ids: Optional[List[str]] = None
    ad_hoc_step_type: Optional[str] = Field(
        default=None,
        serialization_alias="ad_hoc_step_type",
    )
    target_concepts: Optional[List[str]] = None
    turn_plan: Optional[Dict[str, Any]] = None
    planner_guidance: Optional[str] = None
    recommended_strategy: Optional[str] = Field(default=None, description="Pedagogical strategy: direct, socratic, scaffolded, assessment, review")


class EvaluatorState(BaseModel):
    """Input to the Evaluator Agent."""
    model_config = ConfigDict(extra="ignore")
    
    student_message: str
    current_step: Optional[str] = Field(default=None, description="Canonical roadmap step type")
    effective_step_type: Optional[str] = Field(default=None, description="Runtime-effective step type after ad-hoc overrides")
    current_objective: Dict[str, Any] = Field(default_factory=dict)
    concept_scope: Dict[str, Any] = Field(default_factory=dict)
    focus_concepts: List[str] = Field(default_factory=list)
    mastery_snapshot: Dict[str, float] = Field(default_factory=dict, description="Concept → mastery mapping (0-1)")
    tutor_question: Optional[str] = None
    tutor_response: Optional[str] = None
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None
