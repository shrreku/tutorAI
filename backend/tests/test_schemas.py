import pytest
from pydantic import ValidationError
from app.schemas.concept import ConceptScope
from app.schemas.objective import CurriculumStep, StepType
from app.schemas.agent_output import (
    PolicyOrchestratorOutput,
    ProgressionDecision,
    PedagogicalAction,
    TutorOutput,
    EvaluatorOutput,
)


class TestConceptScope:
    """Tests for ConceptScope schema."""

    def test_valid_concept_scope(self):
        """Test valid concept scope."""
        scope = ConceptScope(
            primary=["heat_transfer"],
            support=["conduction", "convection"],
            prereq=["thermodynamics"],
        )
        assert scope.primary == ["heat_transfer"]
        assert len(scope.support) == 2

    def test_primary_required(self):
        """Test primary is required and must have at least one element."""
        with pytest.raises(ValidationError):
            ConceptScope(primary=[])

    def test_defaults(self):
        """Test support and prereq default to empty lists."""
        scope = ConceptScope(primary=["heat_transfer"])
        assert scope.support == []
        assert scope.prereq == []

    def test_extra_fields_forbidden(self):
        """Test extra fields are rejected."""
        with pytest.raises(ValidationError):
            ConceptScope(primary=["x"], extra_field="not allowed")


class TestCurriculumStep:
    """Tests for CurriculumStep schema."""

    def test_valid_step(self):
        """Test valid curriculum step."""
        step = CurriculumStep(
            type=StepType.MOTIVATE,
            target_concepts=["heat_transfer"],
            goal="Connect heat transfer to real-world systems.",
        )
        assert step.type == StepType.MOTIVATE

    def test_legacy_step_type_field_rejected(self):
        """Legacy step_type alias should be rejected by strict schema."""
        with pytest.raises(ValidationError):
            CurriculumStep(
                step_type="explain",
                target_concepts=["heat_transfer"],
                goal="Explain the concept.",
            )

    def test_legacy_step_value_rejected(self):
        """Legacy step values should be rejected by strict step enum."""
        with pytest.raises(ValidationError):
            CurriculumStep(
                type="introduce",
                target_concepts=["heat_transfer"],
                goal="Introduce the concept.",
            )

    def test_step_type_enum(self):
        """Test type must be valid enum."""
        with pytest.raises(ValidationError):
            CurriculumStep(
                type="invalid",
                target_concepts=["x"],
                goal="y",
            )

    def test_phase_evidence_alias_rejected(self):
        """Deprecated phase-era evidence alias should be rejected."""
        with pytest.raises(ValidationError):
            CurriculumStep(
                type=StepType.EXPLAIN,
                target_concepts=["heat_transfer"],
                goal="Explain heat transfer.",
                phase_evidence_chunk_ids_topk=["chunk_1"],
            )


class TestPolicyOrchestratorOutput:
    """Tests for PolicyOrchestratorOutput schema."""

    def test_valid_output(self):
        """Test valid policy output."""
        output = PolicyOrchestratorOutput(
            pedagogical_action=PedagogicalAction.EXPLAIN,
            progression_decision=ProgressionDecision.CONTINUE_STEP,
            confidence=0.85,
            reasoning="Student shows understanding, advancing.",
            student_intent="engaged",
            ad_hoc_step_type="correct",
            skip_target_index=2,
        )
        assert output.confidence == 0.85

    def test_confidence_bounds(self):
        """Test confidence must be between 0 and 1."""
        with pytest.raises(ValidationError):
            PolicyOrchestratorOutput(
                pedagogical_action=PedagogicalAction.EXPLAIN,
                progression_decision=ProgressionDecision.ADVANCE_STEP,
                confidence=1.5,  # Invalid
                reasoning="x",
            )

    def test_reasoning_required(self):
        """Test reasoning is required and non-empty."""
        with pytest.raises(ValidationError):
            PolicyOrchestratorOutput(
                pedagogical_action=PedagogicalAction.EXPLAIN,
                progression_decision=ProgressionDecision.SKIP_TO_STEP,
                confidence=0.5,
                reasoning="",  # Empty not allowed
            )

    def test_deprecated_policy_field_rejected(self):
        """Deprecated fields should fail strict policy schema validation."""
        with pytest.raises(ValidationError):
            PolicyOrchestratorOutput(
                pedagogical_action=PedagogicalAction.EXPLAIN,
                progression_decision=ProgressionDecision.CONTINUE_STEP,
                confidence=0.7,
                reasoning="continue",
                phase_skeleton=["define", "explain"],
            )


class TestTutorOutput:
    """Tests for TutorOutput schema."""

    def test_valid_output(self):
        """Test valid tutor output."""
        output = TutorOutput(
            response_text="Let me explain heat transfer...",
            tutor_question="Can you describe the three modes?",
        )
        assert output.response_text.startswith("Let me")

    def test_response_required(self):
        """Test response_text is required."""
        with pytest.raises(ValidationError):
            TutorOutput(response_text="")

    def test_unknown_tutor_field_rejected(self):
        """Unknown tutor output fields should be rejected."""
        with pytest.raises(ValidationError):
            TutorOutput(response_text="ok", unsupported_field="x")


class TestEvaluatorOutput:
    """Tests for EvaluatorOutput schema."""

    def test_valid_output(self):
        """Test valid evaluator output."""
        output = EvaluatorOutput(
            overall_score=0.75,
            correctness_label="partial",
            multi_concept=False,
            misconceptions=["confused conduction with convection"],
        )
        assert output.overall_score == 0.75

    def test_correctness_label_literal(self):
        """Test correctness_label must be valid literal."""
        with pytest.raises(ValidationError):
            EvaluatorOutput(
                overall_score=0.5,
                correctness_label="invalid",
                multi_concept=False,
            )

    def test_score_bounds(self):
        """Test overall_score must be between 0 and 1."""
        with pytest.raises(ValidationError):
            EvaluatorOutput(
                overall_score=-0.1,
                correctness_label="correct",
                multi_concept=False,
            )

    def test_unknown_evaluator_field_rejected(self):
        """Unknown evaluator output fields should be rejected."""
        with pytest.raises(ValidationError):
            EvaluatorOutput(
                overall_score=0.6,
                correctness_label="partial",
                multi_concept=False,
                phase_feedback="legacy",
            )
