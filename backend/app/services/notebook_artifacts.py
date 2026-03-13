from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.session import UserSession
from app.schemas.api import NotebookProgressResponse
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


def _truncate(value: str | None, limit: int = 320) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _clean_concepts(concepts: list[str], *, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for concept in concepts:
        normalized = (concept or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
        if len(cleaned) >= limit:
            break
    return cleaned


class ArtifactNoteSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1)
    bullets: list[str] = Field(default_factory=list)
    key_takeaway: str = Field(min_length=1)
    source_session_ids: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)


class NotesArtifactOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    sections: list[ArtifactNoteSection] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    coverage_concepts: list[str] = Field(default_factory=list)


class FlashcardArtifactItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    front: str = Field(min_length=1)
    back: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    difficulty: str = Field(default="medium")
    source_session_ids: list[str] = Field(default_factory=list)
    study_hint: str = Field(default="")


class FlashcardsArtifactOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    deck_strategy: str = Field(min_length=1)
    cards: list[FlashcardArtifactItem] = Field(default_factory=list)
    coverage_concepts: list[str] = Field(default_factory=list)


class QuizArtifactQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    question_type: str = Field(default="multiple_choice")
    options: list[str] = Field(default_factory=list)
    correct_answer: str = Field(min_length=1)
    explanation: str = Field(default="")
    concept: str = Field(min_length=1)
    difficulty: str = Field(default="medium")
    source_session_ids: list[str] = Field(default_factory=list)


class QuizArtifactOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    quiz_focus: str = Field(min_length=1)
    questions: list[QuizArtifactQuestion] = Field(default_factory=list)
    recommended_follow_up: str = Field(default="")


class RevisionPlanDay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_label: str = Field(min_length=1)
    scheduled_for: str = Field(min_length=1)
    focus_concepts: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    source_session_ids: list[str] = Field(default_factory=list)


class RevisionPlanArtifactOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    horizon_days: int = Field(default=7, ge=1, le=30)
    days: list[RevisionPlanDay] = Field(default_factory=list)


class NotebookArtifactService:
    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self.llm = llm_provider

    async def generate_payload(
        self,
        *,
        artifact_type: str,
        notebook: Any,
        sessions: list[UserSession],
        turns_by_session: dict[str, list[Any]],
        progress: NotebookProgressResponse,
        source_resource_names: list[str],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._build_context(
            notebook=notebook,
            sessions=sessions,
            turns_by_session=turns_by_session,
            progress=progress,
            source_resource_names=source_resource_names,
        )

        strategy = "deterministic_fallback"
        fallback_reason: str | None = None
        has_grounded_session_context = self._has_grounded_session_context(
            sessions=sessions,
            turns_by_session=turns_by_session,
        )

        if self.llm and has_grounded_session_context:
            try:
                payload = await self._generate_with_llm(
                    artifact_type=artifact_type,
                    context=context,
                    options=options,
                )
                strategy = "llm"
            except Exception as exc:
                fallback_reason = str(exc)
                logger.warning(
                    "Notebook artifact LLM generation failed for %s: %s",
                    artifact_type,
                    exc,
                )
                payload = self._generate_fallback(
                    artifact_type=artifact_type,
                    sessions=sessions,
                    turns_by_session=turns_by_session,
                    progress=progress,
                    options=options,
                    notebook=notebook,
                    source_resource_names=source_resource_names,
                )
        else:
            fallback_reason = (
                "insufficient_session_context" if self.llm else "llm_unavailable"
            )
            payload = self._generate_fallback(
                artifact_type=artifact_type,
                sessions=sessions,
                turns_by_session=turns_by_session,
                progress=progress,
                options=options,
                notebook=notebook,
                source_resource_names=source_resource_names,
            )

        payload["artifact_type"] = artifact_type
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        payload["options"] = options or {}
        payload["progress_context"] = {
            "sessions_count": progress.sessions_count,
            "completed_sessions_count": progress.completed_sessions_count,
            "weak_concepts": progress.weak_concepts_snapshot,
        }
        payload["generation"] = {
            "strategy": strategy,
            "model": self.llm.model_id if self.llm and strategy == "llm" else None,
            "fallback_reason": fallback_reason,
        }
        payload["notebook_context"] = {
            "title": getattr(notebook, "title", None),
            "goal": getattr(notebook, "goal", None),
            "resources": source_resource_names,
        }
        return payload

    def _has_grounded_session_context(
        self,
        *,
        sessions: list[UserSession],
        turns_by_session: dict[str, list[Any]],
    ) -> bool:
        for session in sessions:
            if turns_by_session.get(str(session.id)):
                return True
            plan_state = session.plan_state or {}
            if plan_state.get("session_overview") or plan_state.get("focus_concepts"):
                return True
        return False

    def _build_context(
        self,
        *,
        notebook: Any,
        sessions: list[UserSession],
        turns_by_session: dict[str, list[Any]],
        progress: NotebookProgressResponse,
        source_resource_names: list[str],
    ) -> dict[str, Any]:
        session_contexts: list[dict[str, Any]] = []
        for session in sessions[:10]:
            plan_state = session.plan_state or {}
            objective_queue = plan_state.get("objective_queue", [])
            focus_concepts = _clean_concepts(
                plan_state.get("focus_concepts", []), limit=6
            )
            mastery_items = sorted(
                (
                    (concept, float(score))
                    for concept, score in (session.mastery or {}).items()
                    if score is not None
                ),
                key=lambda item: item[1],
            )
            weak_concepts = [concept for concept, _ in mastery_items[:4]]
            turns = turns_by_session.get(str(session.id), [])[-3:]
            transcript = [
                {
                    "student": _truncate(getattr(turn, "student_message", None), 220),
                    "tutor": _truncate(getattr(turn, "tutor_response", None), 280),
                }
                for turn in turns
            ]
            session_contexts.append(
                {
                    "session_id": str(session.id),
                    "status": session.status,
                    "topic": plan_state.get("active_topic"),
                    "mode": plan_state.get("mode") or "unknown",
                    "overview": _truncate(plan_state.get("session_overview"), 240),
                    "focus_concepts": focus_concepts,
                    "weakest_concepts": _clean_concepts(weak_concepts, limit=4),
                    "objectives": [
                        {
                            "objective_id": obj.get("objective_id"),
                            "title": obj.get("title"),
                            "primary_concepts": obj.get("concept_scope", {}).get(
                                "primary", []
                            )[:3],
                        }
                        for obj in objective_queue[:5]
                    ],
                    "recent_turns": transcript,
                }
            )

        mastery_snapshot = sorted(
            progress.mastery_snapshot.items(),
            key=lambda item: item[1],
        )

        return {
            "notebook": {
                "title": getattr(notebook, "title", "Notebook"),
                "goal": getattr(notebook, "goal", None),
                "target_date": getattr(notebook, "target_date", None).isoformat()
                if getattr(notebook, "target_date", None)
                else None,
            },
            "resources": source_resource_names,
            "progress": {
                "weak_concepts": progress.weak_concepts_snapshot[:10],
                "lowest_mastery": [
                    {"concept": concept, "score": round(float(score), 3)}
                    for concept, score in mastery_snapshot[:8]
                ],
                "sessions_count": progress.sessions_count,
                "completed_sessions_count": progress.completed_sessions_count,
            },
            "sessions": session_contexts,
        }

    async def _generate_with_llm(
        self,
        *,
        artifact_type: str,
        context: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        if artifact_type == "notes":
            schema: type[BaseModel] = NotesArtifactOutput
        elif artifact_type == "flashcards":
            schema = FlashcardsArtifactOutput
        elif artifact_type == "quiz":
            schema = QuizArtifactOutput
        elif artifact_type == "revision_plan":
            schema = RevisionPlanArtifactOutput
        else:
            raise ValueError(f"Unsupported artifact_type: {artifact_type}")

        response = await self.llm.generate_json(
            messages=[
                {"role": "system", "content": self._system_prompt(artifact_type)},
                {
                    "role": "user",
                    "content": self._user_prompt(
                        artifact_type=artifact_type,
                        context=context,
                        options=options,
                    ),
                },
            ],
            schema=schema,
            temperature=0.35,
            max_tokens=2800,
            trace_name=f"notebook_artifact.{artifact_type}",
            trace_metadata={
                "artifact_type": artifact_type,
                "session_count": len(context.get("sessions", [])),
                "resource_count": len(context.get("resources", [])),
            },
        )
        return response.model_dump()

    def _system_prompt(self, artifact_type: str) -> str:
        return (
            "You generate high-value study artifacts for a notebook-based tutoring product. "
            "Ground every output in the supplied notebook, progress, session, and transcript context. "
            "Do not invent concepts or claims that are not supported by the provided context. "
            "Prefer concise, learner-facing language that is specific and actionable. "
            "Every section, card, question, or plan day must include relevant source_session_ids drawn only from the provided session ids. "
            f"You are generating a {artifact_type} artifact."
        )

    def _user_prompt(
        self, *, artifact_type: str, context: dict[str, Any], options: dict[str, Any]
    ) -> str:
        option_summary = options or {}
        guidance = {
            "notes": "Produce concise notes by objective or theme, not a transcript dump. Emphasize what matters most and what to revisit.",
            "flashcards": "Create flashcards that target weak or important concepts, with compact but useful backs.",
            "quiz": "Generate a balanced quiz with plausible options and explanations. Focus more on lower-mastery concepts.",
            "revision_plan": "Build a short revision plan sequenced by urgency and dependency, with concrete activities each day.",
        }[artifact_type]
        return (
            f"Artifact options: {option_summary}\n"
            f"Artifact guidance: {guidance}\n\n"
            "Use this notebook context:\n"
            f"{context}\n\n"
            "Return only data that fits the schema."
        )

    def _generate_fallback(
        self,
        *,
        artifact_type: str,
        sessions: list[UserSession],
        turns_by_session: dict[str, list[Any]],
        progress: NotebookProgressResponse,
        options: dict[str, Any],
        notebook: Any,
        source_resource_names: list[str],
    ) -> dict[str, Any]:
        if not sessions:
            return self._fallback_without_sessions(
                artifact_type=artifact_type,
                notebook=notebook,
                progress=progress,
                source_resource_names=source_resource_names,
                options=options,
            )
        if artifact_type == "notes":
            return self._fallback_notes(sessions, turns_by_session, progress)
        if artifact_type == "flashcards":
            return self._fallback_flashcards(sessions)
        if artifact_type == "quiz":
            return self._fallback_quiz(sessions, options)
        if artifact_type == "revision_plan":
            return self._fallback_revision_plan(progress, sessions, options)
        raise ValueError(f"Unsupported artifact_type: {artifact_type}")

    def _fallback_without_sessions(
        self,
        *,
        artifact_type: str,
        notebook: Any,
        progress: NotebookProgressResponse,
        source_resource_names: list[str],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        notebook_title = getattr(notebook, "title", None) or "Notebook"
        notebook_goal = getattr(notebook, "goal", None)
        resources = source_resource_names[:6]
        weak_concepts = progress.weak_concepts_snapshot[:6]

        if artifact_type == "notes":
            sections = []
            if notebook_goal:
                sections.append(
                    {
                        "heading": "Notebook Goal",
                        "bullets": [notebook_goal],
                        "key_takeaway": notebook_goal,
                        "source_session_ids": [],
                        "concepts": [],
                    }
                )
            if resources:
                sections.append(
                    {
                        "heading": "Attached Resources",
                        "bullets": [f"Study source: {name}" for name in resources],
                        "key_takeaway": "Complete at least one tutoring session to generate session-grounded notes.",
                        "source_session_ids": [],
                        "concepts": weak_concepts,
                    }
                )
            return {
                "title": f"{notebook_title} Notes Scaffold",
                "summary": "No tutoring sessions have been completed for this notebook yet, so these notes are limited to notebook metadata and attached resources.",
                "sections": sections,
                "next_actions": [
                    "Start a tutoring session for this notebook.",
                    "Return after the first session to generate evidence-grounded notes.",
                ],
                "coverage_concepts": weak_concepts,
            }

        if artifact_type == "flashcards":
            return {
                "title": f"{notebook_title} Flashcards",
                "deck_strategy": "No session evidence is available yet; generate flashcards after at least one tutoring session for grounded cards.",
                "cards": [],
                "coverage_concepts": weak_concepts,
            }

        if artifact_type == "quiz":
            return {
                "title": f"{notebook_title} Quiz",
                "quiz_focus": "No session evidence is available yet.",
                "questions": [],
                "recommended_follow_up": "Complete at least one tutoring session before generating a quiz.",
            }

        if artifact_type == "revision_plan":
            horizon_days = max(3, min(int(options.get("horizon_days", 5) or 5), 14))
            now = datetime.now(timezone.utc)
            days = [
                {
                    "day_label": f"Day {index + 1}",
                    "scheduled_for": (now + timedelta(days=index + 1))
                    .date()
                    .isoformat(),
                    "focus_concepts": weak_concepts[:2],
                    "activities": [
                        "Complete a notebook tutoring session.",
                        "Review the attached source material.",
                    ],
                    "rationale": "A grounded revision plan requires completed session evidence.",
                    "source_session_ids": [],
                }
                for index in range(horizon_days)
            ]
            return {
                "title": f"{notebook_title} Revision Plan",
                "summary": "This is a bootstrap revision plan based only on notebook metadata because no tutoring sessions exist yet.",
                "horizon_days": horizon_days,
                "days": days,
            }

        raise ValueError(f"Unsupported artifact_type: {artifact_type}")

    def _fallback_notes(
        self,
        sessions: list[UserSession],
        turns_by_session: dict[str, list[Any]],
        progress: NotebookProgressResponse,
    ) -> dict[str, Any]:
        sections: list[dict[str, Any]] = []
        coverage_concepts: list[str] = []
        next_actions: list[str] = []
        for session in sessions[:4]:
            plan_state = session.plan_state or {}
            turns = turns_by_session.get(str(session.id), [])
            latest_turn = turns[-1] if turns else None
            concepts = _clean_concepts(plan_state.get("focus_concepts", []), limit=4)
            coverage_concepts.extend(concepts)
            heading = plan_state.get("active_topic") or f"Session {str(session.id)[:8]}"
            bullets = []
            if plan_state.get("session_overview"):
                bullets.append(_truncate(plan_state.get("session_overview"), 180))
            if latest_turn is not None:
                bullets.append(
                    _truncate(getattr(latest_turn, "tutor_response", None), 180)
                )
            if concepts:
                bullets.append("Focus concepts: " + ", ".join(concepts))
            weak = [
                concept
                for concept in concepts
                if concept in progress.weak_concepts_snapshot
            ]
            if weak:
                next_actions.append(
                    f"Revisit {', '.join(weak[:2])} with one self-test question."
                )
            sections.append(
                {
                    "heading": heading,
                    "bullets": bullets
                    or [
                        "Review the core explanation and summarize it in your own words."
                    ],
                    "key_takeaway": bullets[0]
                    if bullets
                    else "Capture the main idea and one supporting example.",
                    "source_session_ids": [str(session.id)],
                    "concepts": concepts,
                }
            )
        return {
            "title": "Notebook Study Notes",
            "summary": "A concise recap of the most recent notebook sessions, focused on what was taught and what still needs reinforcement.",
            "sections": sections,
            "next_actions": list(dict.fromkeys(next_actions))[:4],
            "coverage_concepts": _clean_concepts(coverage_concepts, limit=12),
        }

    def _fallback_flashcards(self, sessions: list[UserSession]) -> dict[str, Any]:
        concept_scores: dict[str, list[float]] = {}
        for session in sessions:
            for concept, score in (session.mastery or {}).items():
                try:
                    concept_scores.setdefault(concept, []).append(float(score))
                except (TypeError, ValueError):
                    continue

        cards: list[dict[str, Any]] = []
        for concept, scores in sorted(
            concept_scores.items(), key=lambda item: min(item[1])
        )[:10]:
            avg_score = sum(scores) / len(scores)
            difficulty = (
                "hard" if avg_score < 0.25 else "medium" if avg_score < 0.55 else "easy"
            )
            cards.append(
                {
                    "front": f"What is the core idea behind {concept.replace('_', ' ')}?",
                    "back": "Define it clearly, connect it to one example, and explain why it matters in the wider topic.",
                    "concept": concept,
                    "difficulty": difficulty,
                    "source_session_ids": [str(session.id) for session in sessions[:2]],
                    "study_hint": f"Mastery trend: {avg_score:.0%}. Say the answer aloud before checking the back.",
                }
            )
        return {
            "title": "Notebook Flashcards",
            "deck_strategy": "Prioritize concepts with lower mastery while keeping some reinforcement for stronger concepts.",
            "cards": cards,
            "coverage_concepts": [card["concept"] for card in cards],
        }

    def _fallback_quiz(
        self, sessions: list[UserSession], options: dict[str, Any]
    ) -> dict[str, Any]:
        concept_scores: dict[str, float] = {}
        for session in sessions:
            for concept, score in (session.mastery or {}).items():
                try:
                    value = float(score)
                except (TypeError, ValueError):
                    continue
                concept_scores[concept] = min(concept_scores.get(concept, value), value)

        question_count = max(3, min(int(options.get("question_count", 5) or 5), 10))
        prioritized = [
            concept
            for concept, _ in sorted(concept_scores.items(), key=lambda item: item[1])
        ][:question_count]
        questions = []
        for index, concept in enumerate(prioritized, start=1):
            questions.append(
                {
                    "question_id": f"q{index}",
                    "question": f"In your own words, explain {concept.replace('_', ' ')} and give one example.",
                    "question_type": "short_answer",
                    "options": [],
                    "correct_answer": f"A correct answer should define {concept.replace('_', ' ')} accurately and include a relevant example.",
                    "explanation": "Use the definition, why it matters, and one worked or real example.",
                    "concept": concept,
                    "difficulty": "hard"
                    if concept_scores.get(concept, 0.0) < 0.3
                    else "medium",
                    "source_session_ids": [str(session.id) for session in sessions[:2]],
                }
            )
        return {
            "title": "Notebook Quiz",
            "quiz_focus": "Short-answer recall on the notebook's weakest or least secure concepts.",
            "questions": questions,
            "recommended_follow_up": "Review any answer you could not explain cleanly, then retry the question from memory.",
        }

    def _fallback_revision_plan(
        self,
        progress: NotebookProgressResponse,
        sessions: list[UserSession],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        horizon_days = max(3, min(int(options.get("horizon_days", 5) or 5), 14))
        weak_concepts = progress.weak_concepts_snapshot[: max(horizon_days * 2, 4)]
        session_ids = [str(session.id) for session in sessions[:3]]
        now = datetime.now(timezone.utc)
        days: list[dict[str, Any]] = []
        for index in range(horizon_days):
            start = index * 2
            focus = weak_concepts[start : start + 2] or weak_concepts[:2]
            days.append(
                {
                    "day_label": f"Day {index + 1}",
                    "scheduled_for": (now + timedelta(days=index + 1))
                    .date()
                    .isoformat(),
                    "focus_concepts": focus,
                    "activities": [
                        "Read your notes aloud and explain the idea without looking.",
                        "Do one self-test question or one worked example.",
                        "Write one sentence on what still feels uncertain.",
                    ],
                    "rationale": "These concepts are the least secure in recent notebook progress and should be revisited soon.",
                    "source_session_ids": session_ids,
                }
            )
        return {
            "title": "Notebook Revision Plan",
            "summary": "A short revision sequence that prioritizes weak concepts while mixing explanation and retrieval practice.",
            "horizon_days": horizon_days,
            "days": days,
        }
