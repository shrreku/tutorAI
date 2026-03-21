from typing import List, Optional, Dict, Literal, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class ProgressionDecision(int, Enum):
    CONTINUE_STEP = 1
    ADVANCE_STEP = 2
    SKIP_TO_STEP = 3
    INSERT_AD_HOC = 4
    ADVANCE_OBJECTIVE = 5
    END_SESSION = 6


class PedagogicalAction(str, Enum):
    INTRODUCE = "introduce"
    EXPLAIN = "explain"
    EXAMPLE = "example"
    HINT = "hint"
    QUESTION = "question"
    ASSESS = "assess"
    CORRECT = "correct"
    SUMMARIZE = "summarize"
    CLARIFY = "clarify"
    MOTIVATE = "motivate"


class InteractionType(str, Enum):
    ASK_QUESTION = "ask_question"
    GIVE_HINT = "give_hint"
    WORKED_EXAMPLE = "worked_example"
    EXPLAIN_CONCEPT = "explain_concept"
    CHECK_UNDERSTANDING = "check_understanding"
    REFLECT_PROMPT = "reflect_prompt"
    CORRECT_MISTAKE = "correct_mistake"


class TurnPlan(BaseModel):
    """Plan for the current turn."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., min_length=1)
    interaction_type: InteractionType
    expected_student_action: Optional[
        Literal["reflect", "solve", "answer", "explain", "ask"]
    ] = None
    tutor_question: Optional[str] = None
    constraints: Optional[List[str]] = None


class PolicyOrchestratorOutput(BaseModel):
    """Output from the Policy Agent."""

    model_config = ConfigDict(extra="forbid")

    pedagogical_action: PedagogicalAction
    progression_decision: ProgressionDecision
    confidence: float = Field(..., ge=0, le=1)
    reasoning: str = Field(..., min_length=1)
    intent: Optional[
        Literal["question", "answer", "statement", "confusion", "request_hint"]
    ] = None
    student_intent: Optional[
        Literal[
            "engaged",
            "confused",
            "bored",
            "move_on",
            "asking_question",
            "answer_attempt",
            "off_topic",
            "frustrated",
        ]
    ] = None
    recommended_strategy: Optional[
        Literal["direct", "socratic", "scaffolded", "assessment", "review"]
    ] = None
    ad_hoc_step_type: Optional[str] = None
    skip_target_index: Optional[int] = Field(default=None, ge=0)
    next_objective_index: Optional[int] = Field(default=None, ge=0)
    target_concepts: Optional[List[str]] = Field(default=None, min_length=1)
    retrieval_directives: Optional[Dict[str, Any]] = None
    turn_plan: Optional[TurnPlan] = None
    planner_guidance: Optional[str] = None
    replan_required: bool = False
    replan_reason: Optional[str] = None
    scope_shift_request: Optional[Dict[str, Any]] = None


class TutorOutput(BaseModel):
    """Output from the Tutor Agent."""

    model_config = ConfigDict(extra="forbid")

    response_text: str = Field(..., min_length=1)
    tutor_question: Optional[str] = None
    evidence_chunk_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional stable evidence IDs backing the response",
    )


class ConceptDelta(BaseModel):
    """Delta for a single concept."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(..., ge=0, le=1)
    delta: float
    weight: float = Field(..., ge=0, le=1)
    role: Literal["primary", "support", "prereq"]
    role_weight: Optional[float] = Field(default=None, ge=0, le=1)


class EvaluatorOutput(BaseModel):
    """Output from the Evaluator Agent."""

    model_config = ConfigDict(extra="forbid")

    overall_score: float = Field(..., ge=0, le=1)
    correctness_label: Literal["correct", "partial", "incorrect", "unclear"]
    multi_concept: bool = False
    overall_feedback: Optional[str] = None
    misconceptions: List[str] = Field(default_factory=list)
    concept_deltas: Optional[Dict[str, ConceptDelta]] = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    uncertainty: float = Field(default=0.5, ge=0, le=1)
    uncertainty_hints: List[str] = Field(default_factory=list)
    ready_to_advance: bool = False
    recommended_intervention: Optional[
        Literal[
            "reteach",
            "worked_example",
            "guided_practice",
            "quick_check",
            "advance",
        ]
    ] = None


class CurriculumPlanOutput(BaseModel):
    """Output from the Curriculum Agent."""

    model_config = ConfigDict(extra="forbid")

    objective_queue: List[Dict[str, Any]] = Field(..., min_length=1)
    active_topic: Optional[str] = None
    plan_horizon: Optional[Dict[str, Any]] = None
    curriculum_planner: Optional[Dict[str, Any]] = None
