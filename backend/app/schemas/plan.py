from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.concept import ConceptScope
from app.schemas.objective import Objective, ObjectiveProgress, StepType


class CurriculumObjectiveSummary(BaseModel):
    """Summary of an objective for curriculum slice."""
    model_config = ConfigDict(extra="forbid")
    
    objective_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    concept_scope: ConceptScope
    objective_evidence_chunk_ids_topk: Optional[List[str]] = None
    success_criteria: Optional[Dict[str, Any]] = None


class CurriculumStepView(BaseModel):
    """A step within the curriculum for agent consumption."""
    model_config = ConfigDict(extra="forbid")

    type: StepType = Field(...)
    target_concepts: List[str] = Field(..., min_length=1)
    can_skip: bool = False
    max_turns: int = Field(default=3, ge=1, le=4)
    goal: str = Field(default="Drive understanding for this step.", min_length=1)
    expected_student_action: Optional[str] = None
    step_evidence_chunk_ids_topk: Optional[List[str]] = None


class CurriculumSlice(BaseModel):
    """A compact view of the current curriculum state for agent consumption."""
    model_config = ConfigDict(extra="forbid")

    current_objective: CurriculumObjectiveSummary
    current_step_index: int = Field(
        ...,
        ge=0,
        serialization_alias="current_step_index",
        description="Canonical progression pointer",
    )
    current_step: CurriculumStepView = Field(
        ...,
        serialization_alias="current_step",
    )
    lookahead_steps: Optional[List[CurriculumStepView]] = Field(
        default=None,
        serialization_alias="lookahead_steps",
    )
    upcoming_objectives: Optional[List[CurriculumObjectiveSummary]] = None


class PlanState(BaseModel):
    """The canonical session plan state."""
    model_config = ConfigDict(extra="forbid")
    
    version: Literal[3] = 3
    resource_id: str = Field(..., min_length=1)
    objective_queue: List[Objective] = Field(..., min_length=1)
    current_objective_index: int = Field(default=0, ge=0)
    current_step_index: int = Field(
        default=0,
        ge=0,
        serialization_alias="current_step_index",
        description="Canonical progression pointer into step_roadmap",
    )
    current_step: StepType = Field(..., description="Human-readable step type derived from step_roadmap[current_step_index].type")
    turns_at_step: int = Field(default=0, ge=0)
    step_status: Dict[str, str] = Field(default_factory=dict)
    ad_hoc_count: int = Field(
        default=0,
        ge=0,
        serialization_alias="ad_hoc_count",
    )
    max_ad_hoc_per_objective: int = Field(default=4, ge=1)
    last_decision: Optional[str] = None
    last_ad_hoc_type: Optional[str] = None
    objective_progress: Dict[str, ObjectiveProgress] = Field(default_factory=dict)
    active_topic: Optional[str] = None
    focus_concepts: Optional[List[str]] = None
    session_overview: Optional[str] = None
    plan_horizon: Optional[Dict[str, Any]] = None
    curriculum_planner: Optional[Dict[str, Any]] = None
