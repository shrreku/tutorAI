"""
Session Service - TICKET-028

Handles session creation and management.
"""
import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.session import UserSession, UserProfile
from app.models.resource import Resource
from app.models.knowledge_base import ResourceConceptStats
from app.agents.curriculum_agent import CurriculumAgent
from app.services.student_state import build_student_concept_state
from app.services.tutor_runtime.step_state import (
    build_step_status,
    get_step_roadmap,
    get_step_type,
)

logger = logging.getLogger(__name__)


def _build_session_overview(objective_queue: list[dict]) -> str:
    """Build a short human-readable overview for session start."""
    if not objective_queue:
        return "Let's begin exploring this material!"

    titles = [obj.get("title", "Untitled") for obj in objective_queue]
    return (
        f"Welcome! In this session we will cover {len(objective_queue)} learning objective(s): "
        + "; ".join(f"{i+1}) {title}" for i, title in enumerate(titles))
        + ". Let's get started!"
    )


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
        consent_training: bool = False,
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
        
        if resource.status != "ready" and resource.status != "completed":
            raise ValueError(f"Resource {resource_id} is not ready (status: {resource.status})")
        
        # Get or create user
        if user_id:
            user = await self._get_user(user_id)
        else:
            user = await self._get_or_create_default_user()
        
        # Check for existing active session
        existing = await self._get_active_session(user.id, resource_id)
        if existing:
            existing_version = (existing.plan_state or {}).get("version")
            if existing_version in (None, 3):
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
        
        # Get concepts for resource
        concepts = await self._get_concepts(resource_id)
        
        # Generate curriculum plan
        plan_output = await self.curriculum.generate_plan(
            resource_id=resource_id,
            topic=topic or resource.topic,
            selected_topics=selected_topics,
        )
        
        # Build initial plan state
        objective_queue = plan_output.get("objective_queue", [])
        first_obj = objective_queue[0] if objective_queue else {}
        first_roadmap = get_step_roadmap(first_obj)
        first_step = first_roadmap[0] if first_roadmap else {}
        session_overview = _build_session_overview(objective_queue)
        
        plan_state = {
            "version": 3,
            "resource_id": str(resource_id),
            "active_topic": plan_output.get("active_topic", topic or resource.topic),
            "objective_queue": objective_queue,
            "current_objective_index": 0,
            "current_step_index": 0,
            "current_step": get_step_type(first_step) if first_step else "explain",
            "turns_at_step": 0,
            "step_status": build_step_status(first_roadmap, 0),
            "ad_hoc_count": 0,
            "max_ad_hoc_per_objective": 4,
            "last_decision": None,
            "last_ad_hoc_type": None,
            "objective_progress": {
                obj.get("objective_id", f"obj_{i}"): {
                    "attempts": 0,
                    "correct": 0,
                    "steps_completed": 0,
                    "steps_skipped": 0,
                }
                for i, obj in enumerate(objective_queue)
            },
            "focus_concepts": (
                first_obj.get("concept_scope", {}).get("primary", []) +
                first_obj.get("concept_scope", {}).get("support", [])
            )[:5],
            "session_overview": session_overview,
        }
        
        # Initialize mastery (all discovered concepts at 0)
        initial_mastery = {c: 0.0 for c in concepts}

        # Ensure all objective concepts are tracked even if not in concept stats yet.
        for obj in objective_queue:
            scope = obj.get("concept_scope", {})
            for concept_id in scope.get("primary", []) + scope.get("support", []) + scope.get("prereq", []):
                initial_mastery.setdefault(concept_id, 0.0)

        plan_state["student_concept_state"] = build_student_concept_state(initial_mastery)
        
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
        await self.db.commit()
        await self.db.refresh(session)
        
        logger.info(f"Created session {session.id} for resource {resource_id}")
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
    ) -> Optional[UserSession]:
        """Get existing active session for user and resource."""
        result = await self.db.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.resource_id == resource_id)
            .where(UserSession.status == "active")
        )
        return result.scalar_one_or_none()
    
    async def _get_concepts(self, resource_id: uuid.UUID) -> list[str]:
        """Get admitted concepts for resource."""
        result = await self.db.execute(
            select(ResourceConceptStats.concept_id)
            .where(ResourceConceptStats.resource_id == resource_id)
        )
        return [row[0] for row in result.fetchall()]
