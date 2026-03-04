"""
Quiz Agent — generates and grades quiz questions for post-session assessment.

Takes session mastery data and concept information to produce targeted quiz
questions that reinforce learning, with heavier focus on concepts the student
found challenging.
"""

import logging
import json
import random
from typing import Optional, List, Dict, Any

from langfuse import observe
from pydantic import BaseModel, Field, ConfigDict

from app.agents.base import BaseAgent
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────

class QuizQuestion(BaseModel):
    """A single quiz question."""
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(..., description="Unique question identifier")
    question_text: str = Field(..., description="The question")
    question_type: str = Field(
        default="multiple_choice",
        description="Type: multiple_choice or short_answer",
    )
    options: List[str] = Field(
        default_factory=list,
        description="Answer options for MCQ (4 options, A-D)",
    )
    correct_answer: str = Field(
        ..., description="Correct answer: option letter (A/B/C/D) or short text",
    )
    explanation: str = Field(
        default="", description="Brief explanation of the correct answer",
    )
    concept: str = Field(..., description="Primary concept being tested")
    difficulty: str = Field(
        default="medium",
        description="easy / medium / hard",
    )


class QuizGenerateState(BaseModel):
    """Input to the Quiz Agent for generating questions."""
    model_config = ConfigDict(extra="ignore")

    concepts: List[str] = Field(
        default_factory=list,
        description="All concepts from the session",
    )
    mastery: Dict[str, float] = Field(
        default_factory=dict,
        description="Concept mastery values (0-1)",
    )
    topic: Optional[str] = Field(default=None, description="Session topic")
    objectives: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Objective queue with titles",
    )
    num_questions: int = Field(
        default=5, ge=1, le=15,
        description="Number of questions to generate",
    )


class QuizGenerateOutput(BaseModel):
    """Output: a batch of quiz questions."""
    model_config = ConfigDict(extra="forbid")

    questions: List[QuizQuestion] = Field(default_factory=list)
    quiz_focus: str = Field(
        default="",
        description="Brief description of what the quiz targets",
    )


class QuizGradeState(BaseModel):
    """Input to grade a single answer."""
    model_config = ConfigDict(extra="ignore")

    question: QuizQuestion
    student_answer: str = Field(..., description="The student's answer")


class QuizGradeOutput(BaseModel):
    """Output: grade for a single answer."""
    model_config = ConfigDict(extra="forbid")

    is_correct: bool = Field(..., description="Whether the answer is correct")
    score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Score: 1.0 correct, 0.5 partial, 0.0 incorrect",
    )
    feedback: str = Field(
        default="", description="Feedback on the answer",
    )
    correct_answer: str = Field(
        default="", description="The correct answer",
    )
    explanation: str = Field(
        default="", description="Explanation of the correct answer",
    )


# ── System prompts ────────────────────────────────────────────────────

QUIZ_GENERATE_SYSTEM_PROMPT = """You are a quiz generator for an adaptive tutoring system. 
Generate quiz questions to reinforce learning after a tutoring session.

# Rules
1. Focus MORE questions on concepts where mastery is LOW (< 0.5) — the student needs practice there.
2. Include some questions on stronger concepts too, to build confidence.
3. For multiple-choice questions, always provide exactly 4 options (A, B, C, D).
4. Make distractors (wrong options) plausible but clearly distinguishable from the correct answer.
5. Vary difficulty: include a mix of easy, medium, and hard questions.
6. Write clear, unambiguous questions.
7. Keep explanations concise (1-2 sentences).

# Output Format
Return ONLY valid JSON matching this exact schema — no markdown, no backticks:
{
  "questions": [
    {
      "question_id": "q1",
      "question_text": "...",
      "question_type": "multiple_choice",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "correct_answer": "A",
      "explanation": "...",
      "concept": "...",
      "difficulty": "medium"
    }
  ],
  "quiz_focus": "Brief description of topics covered"
}"""

QUIZ_GRADE_SYSTEM_PROMPT = """You are a quiz grader for an adaptive tutoring system.
Grade the student's answer to a quiz question.

# Rules
1. For multiple-choice: the answer should match the correct option letter (A/B/C/D). Be lenient — accept the letter alone, the full option text, or a close paraphrase.
2. For short-answer: accept reasonable paraphrases of the correct answer. Be generous with partial credit.
3. Score: 1.0 = correct, 0.5 = partially correct, 0.0 = incorrect.
4. Give brief, encouraging feedback (1-2 sentences). If wrong, explain why gently.

# Output Format
Return ONLY valid JSON:
{
  "is_correct": true/false,
  "score": 0.0-1.0,
  "feedback": "Your feedback here",
  "correct_answer": "The correct answer",
  "explanation": "Brief explanation"
}"""


class QuizAgent(BaseAgent[QuizGenerateState, QuizGenerateOutput]):
    """Generates quiz questions based on session mastery data."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        super().__init__("Quiz")
        self.llm = llm_provider

    @property
    def system_prompt(self) -> str:
        return QUIZ_GENERATE_SYSTEM_PROMPT

    @observe(name="agent.quiz.generate", capture_input=False)
    async def run(self, state: QuizGenerateState) -> QuizGenerateOutput:
        logger.info(
            "QuizAgent: generating %d questions for topic=%s, concepts=%d",
            state.num_questions, state.topic, len(state.concepts),
        )

        if self.llm:
            try:
                prompt = self._build_generate_prompt(state)
                text = await self.llm.generate(
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=3000,
                )

                if text and text.strip():
                    # Strip markdown code fences if present
                    cleaned = text.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.split("\n", 1)[-1]
                    if cleaned.endswith("```"):
                        cleaned = cleaned.rsplit("```", 1)[0]
                    cleaned = cleaned.strip()

                    data = json.loads(cleaned)
                    questions = [
                        QuizQuestion(**q) for q in data.get("questions", [])
                    ]
                    return QuizGenerateOutput(
                        questions=questions[:state.num_questions],
                        quiz_focus=data.get("quiz_focus", ""),
                    )
            except Exception as e:
                logger.warning(f"LLM quiz generation failed: {e}, using fallback")

        return self._fallback_generate(state)

    @observe(name="agent.quiz.grade", capture_input=False)
    async def grade(self, state: QuizGradeState) -> QuizGradeOutput:
        """Grade a student's answer to a quiz question."""
        logger.info("QuizAgent: grading answer for %s", state.question.question_id)

        # For MCQ, try deterministic grading first
        if state.question.question_type == "multiple_choice":
            result = self._deterministic_grade_mcq(state)
            if result is not None:
                return result

        # Fall back to LLM grading for short answers or ambiguous MCQ
        if self.llm:
            try:
                prompt = self._build_grade_prompt(state)
                text = await self.llm.generate(
                    messages=[
                        {"role": "system", "content": QUIZ_GRADE_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=500,
                )

                if text and text.strip():
                    cleaned = text.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.split("\n", 1)[-1]
                    if cleaned.endswith("```"):
                        cleaned = cleaned.rsplit("```", 1)[0]
                    cleaned = cleaned.strip()

                    data = json.loads(cleaned)
                    return QuizGradeOutput(
                        is_correct=data.get("is_correct", False),
                        score=float(data.get("score", 0.0)),
                        feedback=data.get("feedback", ""),
                        correct_answer=data.get("correct_answer", state.question.correct_answer),
                        explanation=data.get("explanation", state.question.explanation),
                    )
            except Exception as e:
                logger.warning(f"LLM grading failed: {e}, using fallback")

        return self._fallback_grade(state)

    # ── Private helpers ───────────────────────────────────────────────

    def _build_generate_prompt(self, state: QuizGenerateState) -> str:
        mastery_lines = []
        for concept in state.concepts:
            val = state.mastery.get(concept, 0.0)
            label = "strong" if val >= 0.5 else "developing" if val >= 0.15 else "weak"
            mastery_lines.append(f"  - {concept.replace('_', ' ')}: {val:.0%} ({label})")

        obj_lines = []
        for i, obj in enumerate(state.objectives, 1):
            title = obj.get("title", f"Objective {i}")
            obj_lines.append(f"  {i}. {title}")

        return f"""Generate exactly {state.num_questions} quiz questions.

TOPIC: {state.topic or 'General'}

OBJECTIVES COVERED:
{chr(10).join(obj_lines) if obj_lines else '  (no specific objectives)'}

CONCEPT MASTERY (session results):
{chr(10).join(mastery_lines) if mastery_lines else '  (no mastery data)'}

IMPORTANT: Generate MORE questions for weaker concepts. Mix in some confidence-building questions for stronger concepts too.
All questions should be multiple_choice with 4 options (A, B, C, D).

Generate the questions now as JSON."""

    def _build_grade_prompt(self, state: QuizGradeState) -> str:
        q = state.question
        options_text = "\n".join(q.options) if q.options else "(no options)"
        return f"""QUESTION ({q.question_type}): {q.question_text}

OPTIONS:
{options_text}

CORRECT ANSWER: {q.correct_answer}
EXPLANATION: {q.explanation}

STUDENT'S ANSWER: {state.student_answer}

Grade this answer now as JSON."""

    def _deterministic_grade_mcq(self, state: QuizGradeState) -> Optional[QuizGradeOutput]:
        """Deterministic MCQ grading — works for clear A/B/C/D answers."""
        answer = state.student_answer.strip().upper()
        correct = state.question.correct_answer.strip().upper()

        # Extract just the letter if they typed "A" or "A." or "A) ..."
        if answer and answer[0] in "ABCD":
            answer_letter = answer[0]
        else:
            return None  # Can't deterministically grade, use LLM

        if correct and correct[0] in "ABCD":
            correct_letter = correct[0]
        else:
            return None

        is_correct = answer_letter == correct_letter
        return QuizGradeOutput(
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            feedback=(
                "Correct! Well done."
                if is_correct
                else f"Not quite. The correct answer is {correct_letter}."
            ),
            correct_answer=state.question.correct_answer,
            explanation=state.question.explanation,
        )

    def _fallback_generate(self, state: QuizGenerateState) -> QuizGenerateOutput:
        """Deterministic fallback when LLM is unavailable."""
        questions = []
        concepts = state.concepts or list(state.mastery.keys())
        if not concepts:
            concepts = ["general knowledge"]

        for i in range(min(state.num_questions, len(concepts) * 2)):
            concept = concepts[i % len(concepts)]
            readable = concept.replace("_", " ").title()
            questions.append(
                QuizQuestion(
                    question_id=f"q{i + 1}",
                    question_text=f"Which of the following best describes {readable}?",
                    question_type="multiple_choice",
                    options=[
                        f"A. A core concept in {state.topic or 'this subject'}",
                        f"B. An unrelated topic",
                        f"C. A derived concept only",
                        f"D. None of the above",
                    ],
                    correct_answer="A",
                    explanation=f"{readable} is a core concept covered in this session.",
                    concept=concept,
                    difficulty="easy",
                )
            )

        return QuizGenerateOutput(
            questions=questions,
            quiz_focus=f"Review of {state.topic or 'session concepts'}",
        )

    def _fallback_grade(self, state: QuizGradeState) -> QuizGradeOutput:
        """Deterministic fallback grading."""
        answer = state.student_answer.strip().upper()
        correct = state.question.correct_answer.strip().upper()
        is_correct = answer == correct or (
            len(answer) > 0 and len(correct) > 0 and answer[0] == correct[0]
        )
        return QuizGradeOutput(
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            feedback="Correct!" if is_correct else f"The correct answer was: {state.question.correct_answer}",
            correct_answer=state.question.correct_answer,
            explanation=state.question.explanation,
        )
