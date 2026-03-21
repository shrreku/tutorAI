"""
Session Service - TICKET-028

Handles session creation and management.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.session import UserSession, UserProfile, TutorTurn
from app.models.resource import Resource
from app.models.knowledge_base import ResourceConceptStats
from app.agents.curriculum_agent import CurriculumAgent
from app.services.student_state import build_student_concept_state
from app.services.tutor_runtime.step_state import (
    build_step_status,
    get_step_roadmap,
    get_step_type,
)
from app.services.tutor_runtime.runtime_contracts import (
    build_curriculum_scope,
    sync_runtime_contract_views,
)

logger = logging.getLogger(__name__)

SUPPORTED_SESSION_MODES = {"learn", "doubt", "practice", "revision"}


def _normalize_session_mode(mode: Optional[str]) -> str:
    normalized = (mode or "learn").strip().lower()
    return normalized if normalized in SUPPORTED_SESSION_MODES else "learn"


def _mode_session_contract(mode: str) -> dict:
    normalized = _normalize_session_mode(mode)
    contracts = {
        "learn": {
            "opening_step_type": "motivate",
            "max_ad_hoc_per_objective": 4,
            "objective_window": "broad",
            "tutor_contract": "teach-first",
            "policy_contract": "concept_building",
            "allow_fluid_objective_progression": False,
        },
        "doubt": {
            "opening_step_type": "clarify",
            "max_ad_hoc_per_objective": 2,
            "objective_window": "narrow",
            "tutor_contract": "clarify-first",
            "policy_contract": "resolve_question",
            "allow_fluid_objective_progression": True,
        },
        "practice": {
            "opening_step_type": "practice",
            "max_ad_hoc_per_objective": 3,
            "objective_window": "medium",
            "tutor_contract": "attempt-first",
            "policy_contract": "retrieval_and_feedback",
            "allow_fluid_objective_progression": False,
        },
        "revision": {
            "opening_step_type": "summarize",
            "max_ad_hoc_per_objective": 2,
            "objective_window": "targeted",
            "tutor_contract": "recall-first",
            "policy_contract": "consolidate_and_test",
            "allow_fluid_objective_progression": True,
        },
    }
    return contracts[normalized]


def _build_session_overview(objective_queue: list[dict]) -> str:
    """Build a short human-readable overview for session start."""
    if not objective_queue:
        return "Let's begin exploring this material!"

    titles = [obj.get("title", "Untitled") for obj in objective_queue]
    return (
        f"Welcome! In this session we will cover {len(objective_queue)} learning objective(s): "
        + "; ".join(f"{i + 1}) {title}" for i, title in enumerate(titles))
        + ". Let's get started!"
    )


def _build_doubt_fallback_plan(*, topic_label: str) -> dict:
    title = topic_label or "Document clarification"
    objective = {
        "objective_id": "obj_doubt_clarify",
        "title": f"Clarify {title}",
        "description": "Resolve the current confusion directly from the indexed material, then verify understanding.",
        "concept_scope": {
            "primary": [],
            "support": [],
            "prereq": [],
        },
        "success_criteria": {
            "min_correct": 1,
            "min_mastery": 0.5,
        },
        "estimated_turns": 2,
        "step_roadmap": [
            {
                "type": "clarify",
                "target_concepts": [],
                "can_skip": False,
                "max_turns": 1,
                "goal": f"Surface the exact confusion about {title}.",
            },
            {
                "type": "explain",
                "target_concepts": [],
                "can_skip": False,
                "max_turns": 2,
                "goal": "Answer the question directly and ground it in the attached resource.",
            },
            {
                "type": "probe",
                "target_concepts": [],
                "can_skip": True,
                "max_turns": 1,
                "goal": "Check whether the confusion is resolved.",
            },
            {
                "type": "summarize",
                "target_concepts": [],
                "can_skip": True,
                "max_turns": 1,
                "goal": "Leave the learner with a concise final takeaway.",
            },
        ],
    }
    return {
        "active_topic": title,
        "objective_queue": [objective],
    }


def _mode_session_overview(
    mode: str, objective_queue: list[dict], active_topic: Optional[str]
) -> str:
    normalized = _normalize_session_mode(mode)
    topic_label = active_topic or "this material"
    if normalized == "doubt":
        return (
            f"This is a doubt-clearing session for {topic_label}. "
            "We will answer the specific confusion directly, verify it against the material, and stop once the point is clear."
        )
    if normalized == "practice":
        return (
            f"This is a practice session for {topic_label}. "
            "Expect more questions, fewer long explanations, and rapid feedback on your attempts."
        )
    if normalized == "revision":
        return (
            f"This is a revision session for {topic_label}. "
            "We will compress the core ideas, target weak spots, and use recall checks to consolidate memory."
        )
    return _build_session_overview(objective_queue)


def _align_roadmap_to_mode(mode: str, roadmap: list[dict]) -> list[dict]:
    normalized = _normalize_session_mode(mode)
    if not roadmap:
        return roadmap

    aligned: list[dict] = []
    for index, step in enumerate(roadmap):
        current = dict(step or {})
        step_type = str(current.get("type") or "explain")

        if normalized == "doubt":
            replacements = {
                "motivate": "explain",
                "activate_prior": "probe",
                "worked_example": "explain",
                "practice": "probe",
                "summarize": "summarize",
            }
            step_type = replacements.get(step_type, step_type)
            current["max_turns"] = min(int(current.get("max_turns", 2) or 2), 2)
            current["can_skip"] = True
        elif normalized == "practice":
            replacements = {
                "motivate": "probe",
                "define": "probe",
                "explain": "practice",
                "worked_example": "practice",
                "summarize": "reflect",
            }
            step_type = replacements.get(step_type, step_type)
            if step_type in {"practice", "probe", "assess"}:
                current["max_turns"] = min(int(current.get("max_turns", 2) or 2), 2)
        elif normalized == "revision":
            replacements = {
                "motivate": "summarize",
                "activate_prior": "probe",
                "define": "summarize",
                "worked_example": "compare_contrast",
                "practice": "assess",
            }
            step_type = replacements.get(step_type, step_type)
            current["max_turns"] = min(int(current.get("max_turns", 2) or 2), 2)

        current["type"] = step_type
        if (
            index == 0
            and normalized in {"practice", "revision"}
            and step_type == "assess"
        ):
            current["can_skip"] = False
        aligned.append(current)

    return aligned


def _opening_step_goal(step_type: str, topic_label: str) -> str:
    goals = {
        "motivate": f"Frame why {topic_label} matters and what the learner should focus on first.",
        "clarify": f"Surface the main confusion about {topic_label} and define the question to resolve.",
        "practice": f"Get the learner attempting a task on {topic_label} immediately.",
        "summarize": f"Condense the key ideas in {topic_label} before testing recall.",
    }
    return goals.get(
        step_type, f"Open the session with a focused step on {topic_label}."
    )


def _ensure_opening_step(
    roadmap: list[dict],
    opening_step_type: str,
    topic_label: Optional[str],
    target_concepts: list[str],
) -> list[dict]:
    if not roadmap:
        return roadmap

    for index, step in enumerate(roadmap):
        if get_step_type(step) == opening_step_type:
            if index == 0:
                return roadmap
            return [step, *roadmap[:index], *roadmap[index + 1 :]]

    first_step = dict(roadmap[0] or {})
    first_step["type"] = opening_step_type
    first_step["target_concepts"] = target_concepts or first_step.get(
        "target_concepts", []
    )
    first_step["can_skip"] = False
    first_step["max_turns"] = 1
    first_step["goal"] = _opening_step_goal(
        opening_step_type, topic_label or "this topic"
    )
    return [first_step, *roadmap]


def _rolling_objective_limit(
    mode: str,
    *,
    concept_count: int,
    resource_count: int,
) -> Optional[int]:
    normalized = _normalize_session_mode(mode)
    if concept_count <= 6 and resource_count <= 1:
        return None
    if normalized in {"doubt", "revision"}:
        return 2
    return 3


def _build_objective_progress_seed(
    objective_queue: list[dict],
) -> dict[str, dict[str, int]]:
    return {
        obj.get("objective_id", f"obj_{index}"): {
            "attempts": 0,
            "correct": 0,
            "steps_completed": 0,
            "steps_skipped": 0,
        }
        for index, obj in enumerate(objective_queue)
    }


class SessionService:
    """Manages tutoring session lifecycle."""

    def __init__(
        self,
        db_session: AsyncSession,
        curriculum_agent: CurriculumAgent,
    ):
        self.db = db_session
        self.curriculum = curriculum_agent

    async def create_session(
        self,
        resource_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        topic: Optional[str] = None,
        selected_topics: Optional[list[str]] = None,
        scope_type: Optional[str] = None,
        scope_resource_ids: Optional[list[uuid.UUID | str]] = None,
        notebook_id: Optional[uuid.UUID | str] = None,
        mode: Optional[str] = None,
        consent_training: bool = False,
        resume_existing: bool = True,
    ) -> UserSession:
        """
        Create a new tutoring session.

        Args:
            resource_id: UUID of the ingested resource
            user_id: Optional user ID
            topic: Optional topic focus

        Returns:
            Created UserSession
        """
        # Get resource
        resource = await self._get_resource(resource_id)
        if not resource:
            raise ValueError(f"Resource {resource_id} not found")

        if resource.status not in ("ready", "completed", "processing"):
            raise ValueError(
                f"Resource {resource_id} is not ready (status: {resource.status})"
            )
        # Allow processing resources that have progressive batch readiness
        if resource.status == "processing":
            capabilities = resource.capabilities_json or {}
            if not (
                capabilities.get("progressive_study_ready")
                or capabilities.get("has_partial_curriculum")
                or int(capabilities.get("ready_batch_count", 0)) > 0
            ):
                raise ValueError(
                    f"Resource {resource_id} is still processing and has no ready batches yet"
                )

        # Get or create user
        if user_id:
            user = await self._get_user(user_id)
        else:
            user = await self._get_or_create_default_user()

        session_mode = _normalize_session_mode(mode)
        mode_contract = _mode_session_contract(session_mode)
        curriculum_scope = build_curriculum_scope(
            anchor_resource_id=resource_id,
            scope_type=scope_type,
            scope_resource_ids=scope_resource_ids,
            notebook_id=notebook_id,
            topic=topic or resource.topic,
            selected_topics=selected_topics,
        )
        planning_resource_ids = list(
            curriculum_scope.get("resource_ids") or [str(resource_id)]
        )

        # Check for existing active session
        existing = None
        if resume_existing:
            existing = await self._get_active_session(
                user.id,
                resource_id,
                scope_type=scope_type,
                scope_resource_ids=scope_resource_ids,
                notebook_id=notebook_id,
            )
        if existing:
            existing_version = (existing.plan_state or {}).get("version")
            existing_mode = _normalize_session_mode(
                (existing.plan_state or {}).get("mode")
            )
            if existing_version in (None, 3) and existing_mode == session_mode:
                await self.db.refresh(existing)
                setattr(existing, "_reused_existing", True)
                return existing

            # Track E cutover is v3-only. Retire legacy active sessions so new
            # turn traffic is routed to a clean v3 bootstrap path.
            existing.status = "completed"
            await self.db.commit()
            logger.info(
                "Retired legacy active session %s with plan_state.version=%s",
                existing.id,
                existing_version,
            )

        if len(planning_resource_ids) > 1:
            concepts = await self._get_scope_concepts(planning_resource_ids)
        else:
            concepts = await self._get_concepts(resource_id)
        is_provisional = False
        if not concepts and session_mode != "doubt":
            # Check if resource has progressive readiness — allow provisional session
            capabilities = getattr(resource, "capabilities_json", None) or {}
            if (
                capabilities.get("progressive_study_ready")
                or capabilities.get("has_partial_curriculum")
                or int(capabilities.get("ready_batch_count", 0)) > 0
            ):
                is_provisional = True
                logger.info(
                    "Creating provisional session for resource %s (progressive readiness, no concepts yet)",
                    resource_id,
                )
            else:
                raise ValueError(
                    f"Resource {resource_id} is marked {resource.status} but has no admitted concepts yet. "
                    "Tutoring sessions cannot start until concept extraction/enrichment succeeds."
                )

        objective_limit = _rolling_objective_limit(
            session_mode,
            concept_count=len(concepts),
            resource_count=len(planning_resource_ids),
        )

        if concepts:
            plan_output = await self.curriculum.generate_plan(
                resource_id=resource_id,
                topic=topic or resource.topic,
                selected_topics=selected_topics,
                mode=session_mode,
                scope_resource_ids=planning_resource_ids,
                scope_type=curriculum_scope.get("scope_type"),
                notebook_id=curriculum_scope.get("notebook_id"),
                objective_limit=objective_limit,
            )
        elif is_provisional:
            # Provisional: use doubt-style fallback until concepts arrive
            plan_output = _build_doubt_fallback_plan(
                topic_label=topic or resource.topic or "this document"
            )
        else:
            plan_output = _build_doubt_fallback_plan(
                topic_label=topic or resource.topic or "this document"
            )

        # Build initial plan state
        objective_queue = list(plan_output.get("objective_queue", []))
        for index, obj in enumerate(objective_queue):
            roadmap = obj.get("step_roadmap") or []
            aligned_roadmap = _align_roadmap_to_mode(session_mode, roadmap)
            if index == 0 and aligned_roadmap:
                scope = obj.get("concept_scope", {})
                opening_targets = (
                    scope.get("primary", [])
                    + scope.get("support", [])
                    + scope.get("prereq", [])
                )[:5]
                aligned_roadmap = _ensure_opening_step(
                    aligned_roadmap,
                    mode_contract["opening_step_type"],
                    topic or resource.topic,
                    opening_targets,
                )
            obj["step_roadmap"] = aligned_roadmap
        first_obj = objective_queue[0] if objective_queue else {}
        first_roadmap = get_step_roadmap(first_obj)
        first_step = first_roadmap[0] if first_roadmap else {}
        active_topic = plan_output.get("active_topic", topic or resource.topic)
        curriculum_scope["topic"] = active_topic
        plan_horizon = dict(plan_output.get("plan_horizon") or {})
        curriculum_planner = dict(plan_output.get("curriculum_planner") or {})
        if objective_limit and not plan_horizon:
            plan_horizon = {
                "version": 1,
                "strategy": "rolling",
                "visible_objectives": len(objective_queue),
                "objective_limit": objective_limit,
                "remaining_concepts_estimate": max(
                    0, len(concepts) - len(objective_queue)
                ),
                "remaining_concepts_sample": [],
            }
        if objective_limit and not curriculum_planner:
            curriculum_planner = {
                "version": 1,
                "scope_type": curriculum_scope.get("scope_type"),
                "notebook_id": curriculum_scope.get("notebook_id"),
                "resource_ids": list(curriculum_scope.get("resource_ids") or []),
                "resource_count": len(planning_resource_ids),
                "rolling_enabled": True,
                "exhausted": False,
                "objective_batch_size": objective_limit,
                "extend_when_remaining": 1,
                "extension_count": 0,
                "remaining_concepts_estimate": max(
                    0, len(concepts) - len(objective_queue)
                ),
                "total_concepts": len(concepts),
                "last_planning_mode": "initial",
            }
        session_overview = _mode_session_overview(
            session_mode, objective_queue, active_topic
        )

        plan_state = {
            "version": 3,
            "mode": session_mode,
            "mode_contract": mode_contract,
            "resource_id": str(resource_id),
            "active_topic": active_topic,
            "curriculum_scope": curriculum_scope,
            "objective_queue": objective_queue,
            "current_objective_index": 0,
            "current_step_index": 0,
            "current_step": get_step_type(first_step) if first_step else "explain",
            "turns_at_step": 0,
            "step_status": build_step_status(first_roadmap, 0),
            "ad_hoc_count": 0,
            "max_ad_hoc_per_objective": mode_contract["max_ad_hoc_per_objective"],
            "last_decision": None,
            "last_ad_hoc_type": None,
            "plan_provisional": is_provisional,
            "replan_required": is_provisional,
            "objective_progress": _build_objective_progress_seed(objective_queue),
            "focus_concepts": (
                first_obj.get("concept_scope", {}).get("primary", [])
                + first_obj.get("concept_scope", {}).get("support", [])
            )[:5],
            "session_overview": session_overview,
            "plan_horizon": plan_horizon,
            "curriculum_planner": curriculum_planner,
        }

        # Initialize mastery (all discovered concepts at 0)
        initial_mastery = {c: 0.0 for c in concepts}

        # Ensure all objective concepts are tracked even if not in concept stats yet.
        for obj in objective_queue:
            scope = obj.get("concept_scope", {})
            for concept_id in (
                scope.get("primary", [])
                + scope.get("support", [])
                + scope.get("prereq", [])
            ):
                initial_mastery.setdefault(concept_id, 0.0)

        plan_state["student_concept_state"] = build_student_concept_state(
            initial_mastery
        )

        sync_runtime_contract_views(
            plan_state,
            mastery_snapshot=initial_mastery,
        )

        # Create session
        session = UserSession(
            user_id=user.id,
            resource_id=resource_id,
            status="active",
            consent_training=consent_training,
            mastery=initial_mastery,
            plan_state=plan_state,
        )

        self.db.add(session)
        flush = getattr(self.db, "flush", None)
        if callable(flush):
            await flush()
        if session.id is None:
            session.id = uuid.uuid4()

        # Persist a tutor-only bootstrap turn so the UI can immediately render
        # a mode-aware opening message right after session creation.
        bootstrap_turn = TutorTurn(
            session_id=session.id,
            turn_index=0,
            student_message="",
            tutor_response=session_overview,
            tutor_question=None,
            current_step_index=0,
            current_step=plan_state.get("current_step"),
            target_concepts=plan_state.get("focus_concepts", []),
            pedagogical_action="session_bootstrap",
            progression_decision=None,
            policy_output={"source": "session_create", "mode": session_mode},
            evaluator_output=None,
            retrieved_chunks=None,
            mastery_before=initial_mastery,
            mastery_after=initial_mastery,
            token_count=0,
            latency_ms=0,
        )
        self.db.add(bootstrap_turn)

        await self.db.commit()
        await self.db.refresh(session)

        logger.info(f"Created session {session.id} for resource {resource_id}")
        setattr(session, "_reused_existing", False)
        return session

    async def get_session(self, session_id: uuid.UUID) -> Optional[UserSession]:
        """Get session by ID."""
        result = await self.db.execute(
            select(UserSession).where(UserSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def end_session(self, session_id: uuid.UUID) -> UserSession:
        """End an active session."""
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.status = "completed"
        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def _get_resource(self, resource_id: uuid.UUID) -> Optional[Resource]:
        """Get resource by ID."""
        result = await self.db.execute(
            select(Resource).where(Resource.id == resource_id)
        )
        return result.scalar_one_or_none()

    async def _get_user(self, user_id: uuid.UUID) -> Optional[UserProfile]:
        """Get user by ID."""
        result = await self.db.execute(
            select(UserProfile).where(UserProfile.id == user_id)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_default_user(self) -> UserProfile:
        """Get or create default anonymous user."""
        result = await self.db.execute(
            select(UserProfile).where(UserProfile.email == "default@studyagent.local")
        )
        user = result.scalar_one_or_none()

        if not user:
            user = UserProfile(
                email="default@studyagent.local",
                display_name="Default User",
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)

        return user

    async def _get_active_session(
        self,
        user_id: uuid.UUID,
        resource_id: uuid.UUID,
        *,
        scope_type: Optional[str] = None,
        scope_resource_ids: Optional[list[uuid.UUID | str]] = None,
        notebook_id: Optional[uuid.UUID | str] = None,
    ) -> Optional[UserSession]:
        """Get existing active session for user and resource."""
        result = await self.db.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.resource_id == resource_id)
            .where(UserSession.status == "active")
            .order_by(UserSession.created_at.desc())
        )
        active_sessions = list(result.scalars().all())
        if not active_sessions:
            return None

        if len(active_sessions) > 1:
            logger.warning(
                "Found %s active sessions for user %s and resource %s; reusing newest session %s",
                len(active_sessions),
                user_id,
                resource_id,
                active_sessions[0].id,
            )

        desired_scope = build_curriculum_scope(
            anchor_resource_id=resource_id,
            scope_type=scope_type,
            scope_resource_ids=scope_resource_ids,
            notebook_id=notebook_id,
        )
        for session in active_sessions:
            session_plan = session.plan_state or {}
            session_scope = session_plan.get("curriculum_scope") or {}
            existing_scope = build_curriculum_scope(
                anchor_resource_id=session_scope.get("anchor_resource_id")
                or session_plan.get("resource_id")
                or session.resource_id,
                scope_type=session_scope.get("scope_type"),
                scope_resource_ids=session_scope.get("resource_ids"),
                notebook_id=session_scope.get("notebook_id"),
            )
            if existing_scope == desired_scope:
                return session

        return None

    async def _get_concepts(self, resource_id: uuid.UUID) -> list[str]:
        """Get admitted concepts for resource."""
        result = await self.db.execute(
            select(ResourceConceptStats.concept_id).where(
                ResourceConceptStats.resource_id == resource_id
            )
        )
        return [row[0] for row in result.fetchall()]

    async def _get_scope_concepts(
        self,
        resource_ids: list[uuid.UUID | str],
    ) -> list[str]:
        normalized_resource_ids = [
            uuid.UUID(str(resource_id)) for resource_id in resource_ids
        ]
        result = await self.db.execute(
            select(ResourceConceptStats).where(
                ResourceConceptStats.resource_id.in_(normalized_resource_ids)
            )
        )
        rows = result.scalars().all()
        concepts_by_id: dict[str, dict[str, float | int | None]] = {}
        for row in rows:
            record = concepts_by_id.setdefault(
                row.concept_id,
                {
                    "teach_count": 0,
                    "importance_score": 0.0,
                    "topo_order": None,
                },
            )
            record["teach_count"] = int(record["teach_count"] or 0) + int(
                row.teach_count or 0
            )
            record["importance_score"] = max(
                float(record["importance_score"] or 0.0),
                float(row.importance_score or 0.0),
            )
            if row.topo_order is not None and (
                record["topo_order"] is None
                or int(row.topo_order) < int(record["topo_order"])
            ):
                record["topo_order"] = int(row.topo_order)

        ordered = sorted(
            concepts_by_id.items(),
            key=lambda item: (
                item[1]["topo_order"] is None,
                item[1]["topo_order"] if item[1]["topo_order"] is not None else 10**9,
                -int(item[1]["teach_count"] or 0),
                -float(item[1]["importance_score"] or 0.0),
                item[0],
            ),
        )
        return [concept_id for concept_id, _meta in ordered]
