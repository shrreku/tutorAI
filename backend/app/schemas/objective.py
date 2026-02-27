from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.concept import ConceptScope


class StepType(str, Enum):
    MOTIVATE = "motivate"
    ACTIVATE_PRIOR = "activate_prior"
    DEFINE = "define"
    EXPLAIN = "explain"
    WORKED_EXAMPLE = "worked_example"
    DERIVE = "derive"
    COMPARE_CONTRAST = "compare_contrast"
    PROBE = "probe"
    PRACTICE = "practice"
    ASSESS = "assess"
    CORRECT = "correct"
    REFLECT = "reflect"
    CONNECT = "connect"
    SUMMARIZE = "summarize"


class ExpectedStudentAction(str, Enum):
    REFLECT = "reflect"
    SOLVE = "solve"
    ANSWER = "answer"
    EXPLAIN = "explain"
    ASK = "ask"


class CurriculumStep(BaseModel):
    """A single step within an objective roadmap."""
    model_config = ConfigDict(extra="forbid")

    type: StepType = Field(...)
    target_concepts: List[str] = Field(..., min_length=1, description="Concepts to focus on in this step")
    can_skip: bool = False
    max_turns: int = Field(default=3, ge=1, le=4)
    goal: str = Field(default="Drive understanding for this step.", min_length=1, description="Short completion goal for this step")
    expected_student_action: Optional[ExpectedStudentAction] = None
    step_evidence_chunk_ids_topk: Optional[List[str]] = Field(default=None, description="Top-k chunk IDs grounding this step")


class SuccessCriteria(BaseModel):
    """Success criteria for an objective."""
    model_config = ConfigDict(extra="forbid")
    
    min_correct: int = Field(..., ge=0)
    min_mastery: float = Field(..., ge=0, le=1)
    max_uncertainty: Optional[float] = Field(default=None, ge=0, le=1)


class Objective(BaseModel):
    """A learning objective with concept scope, success criteria, and step roadmap."""
    model_config = ConfigDict(extra="forbid")
    
    objective_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    concept_scope: ConceptScope
    objective_evidence_chunk_ids_topk: List[str] = Field(..., min_length=1, description="Chunk IDs grounding this objective")
    success_criteria: SuccessCriteria
    estimated_turns: int = Field(..., ge=1)
    step_roadmap: List[CurriculumStep] = Field(
        ...,
        min_length=1,
    )
    prereq_objective_ids: Optional[List[str]] = Field(default=None, description="Objectives that should precede this one")
    bloom_level: Optional[str] = None
    performance: Optional[str] = None


class ObjectiveProgress(BaseModel):
    """Tracks progress within an objective."""
    model_config = ConfigDict(extra="forbid")
    
    attempts: int = Field(default=0, ge=0)
    correct: int = Field(default=0, ge=0)
    steps_completed: int = Field(default=0, ge=0)
    steps_skipped: int = Field(default=0, ge=0)
    last_assessed_at: Optional[datetime] = None
    mastery_snapshot: Optional[Dict[str, float]] = Field(default=None, description="Concept → mastery mapping")

