"""
Curriculum Agent - TICKET-024

Generates learning objectives and curriculum plans from resource content.
"""
import logging
from typing import Optional
from uuid import UUID

from langfuse import observe
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.llm.base import BaseLLMProvider
from app.schemas.agent_output import CurriculumPlanOutput
from app.models.knowledge_base import (
    ResourceTopicBundle,
    ResourceConceptStats,
    ResourceConceptGraph,
    ResourceLearningObjective,
    ResourcePrereqHint,
    ResourceBundle,
)

logger = logging.getLogger(__name__)


CURRICULUM_SYSTEM_PROMPT = """You are the **Curriculum Planner** of an agentic tutoring system.
Your job is to design a sequence of **learning objectives**, each with a **step roadmap** (step_roadmap).
These are the fundamental working units of the entire system — the Policy, Tutor, and Evaluator agents all operate within your plan.

# Learning Objective Structure
Each objective must have:
- `objective_id`: Unique identifier (e.g., "obj_01_probability_space")
- `title`: Clear, action-oriented title (e.g., "Understand Probability Spaces and Their Components")
- `description`: 1-2 sentences on what the student will learn and why it matters.
- `concept_scope`:
  - `primary`: 1-3 core concepts the student must master (these drive progression).
  - `support`: 0-2 related concepts that appear in explanations.
  - `prereq`: 0-2 concepts the student should already know.
- `success_criteria`: `{min_correct: 2, min_mastery: 0.7}` — how many correct responses and what mastery level trigger advancement.
- `estimated_turns`: Expected turns to complete (3-8).
- `step_roadmap`: The step plan (see below).

# Step Roadmap (step_roadmap)
Each objective has 4-7 steps. Use only these step types:
- motivate
- activate_prior
- define
- explain
- worked_example
- derive
- compare_contrast
- probe
- practice
- assess
- correct
- reflect
- connect
- summarize

Each step has:
- `type`: one of the listed step types
- `target_concepts`: concepts this step focuses on (must be from concept_scope)
- `can_skip`: true/false
- `max_turns`: integer 1-4
- `goal`: short completion goal

# Rules
- Use ingestion-extracted learning objectives as PRIMARY grounding when available.
- **Prerequisite ordering**: Foundational concepts FIRST. If concept B depends on A, the objective covering A must come before B.
- **Concept IDs**: Use ONLY the exact concept IDs provided. Do not invent new ones.
- **Scope**: Each objective should be completable in 3-8 turns. Don't make objectives too broad.
- Vary roadmaps by bloom level and concept type; avoid identical roadmaps across all objectives.
- Generate 2-4 objectives that cover the key concepts.

Output valid JSON with:
{
  "active_topic": "string",
  "objective_queue": [list of objectives]
}"""


class CurriculumAgent:
    """Generates curriculum plans from resource content."""
    
    def __init__(self, llm_provider: BaseLLMProvider, db_session: AsyncSession):
        self.llm = llm_provider
        self.db = db_session
    
    @observe(name="curriculum-planner", capture_input=False)
    async def generate_plan(
        self,
        resource_id: UUID,
        topic: Optional[str] = None,
        selected_topics: Optional[list[str]] = None,
    ) -> dict:
        """
        Generate a curriculum plan for a resource.
        
        Args:
            resource_id: UUID of the ingested resource
            topic: Optional topic focus
        
        Returns:
            Dict with active_topic and objective_queue
        """
        # Get topic bundles and concepts
        topic_bundles = await self._get_topic_bundles(resource_id)
        concepts = await self._get_concepts(resource_id)
        learning_objectives = await self._get_learning_objectives(resource_id)
        concept_graph_edges = await self._get_concept_graph_edges(resource_id)
        prereq_hints = await self._get_prereq_hints(resource_id)
        
        if not concepts:
            raise ValueError(f"No concepts found for resource {resource_id}")
        
        # Filter by selected topics if provided
        if selected_topics:
            filtered_bundles = [b for b in topic_bundles if b["topic_id"] in selected_topics or b["topic_name"] in selected_topics]
            if filtered_bundles:
                topic_bundles = filtered_bundles
                # Restrict concepts to those in selected topic bundles
                selected_concepts = set()
                for b in filtered_bundles:
                    selected_concepts.update(b.get("primary_concepts", []))
                    selected_concepts.update(b.get("support_concepts", []))
                if selected_concepts:
                    concepts = [c for c in concepts if c in selected_concepts]
                    concept_graph_edges = [
                        edge
                        for edge in concept_graph_edges
                        if edge.get("source") in selected_concepts and edge.get("target") in selected_concepts
                    ]
                    prereq_hints = [
                        hint
                        for hint in prereq_hints
                        if hint.get("source") in selected_concepts and hint.get("target") in selected_concepts
                    ]
        
        # Build prompt
        messages = self._build_messages(
            topic_bundles,
            concepts,
            learning_objectives,
            concept_graph_edges,
            prereq_hints,
            topic,
        )
        
        try:
            output = await self._generate_curriculum_output(
                messages,
                trace_name="curriculum_generate_plan",
            )
            
            # Validate concepts in output
            valid_concepts = set(concepts)
            validated_objectives = []
            
            for obj in output.objective_queue:
                validated_obj = self._validate_objective(obj, valid_concepts)
                if validated_obj:
                    validated_objectives.append(validated_obj)
            
            if not validated_objectives:
                # Fallback: create basic objective from concepts
                validated_objectives = self._create_fallback_objectives(concepts)
            
            return {
                "active_topic": output.active_topic or topic or "General",
                "objective_queue": validated_objectives,
            }
            
        except Exception as e:
            logger.error(f"Curriculum generation failed: {e}")
            # Return fallback plan
            return {
                "active_topic": topic or "General",
                "objective_queue": self._create_fallback_objectives(concepts),
            }
    
    @observe(name="curriculum-extend", capture_input=False)
    async def extend_plan(
        self,
        resource_id: UUID,
        current_objectives: list[dict],
        completed_concepts: list[str],
    ) -> list[dict]:
        """
        Generate additional objectives when horizon reached.
        
        Args:
            resource_id: UUID of the resource
            current_objectives: Existing objectives
            completed_concepts: Concepts already covered
        
        Returns:
            List of new objectives
        """
        concepts = await self._get_concepts(resource_id)
        
        # Find uncovered concepts
        covered = set(completed_concepts)
        for obj in current_objectives:
            scope = obj.get("concept_scope", {})
            covered.update(scope.get("primary", []))
        
        remaining = [c for c in concepts if c not in covered]
        
        if not remaining:
            return []
        
        # Generate objectives for remaining concepts
        topic_bundles = await self._get_topic_bundles(resource_id)
        learning_objectives = await self._get_learning_objectives(resource_id)
        concept_graph_edges = await self._get_concept_graph_edges(resource_id)
        prereq_hints = await self._get_prereq_hints(resource_id)
        messages = self._build_messages(
            topic_bundles,
            remaining,
            learning_objectives,
            concept_graph_edges,
            prereq_hints,
            None,
        )
        
        try:
            output = await self._generate_curriculum_output(
                messages,
                trace_name="curriculum_extend_plan",
            )
            
            valid_concepts = set(remaining)
            return [
                self._validate_objective(obj, valid_concepts)
                for obj in output.objective_queue
                if self._validate_objective(obj, valid_concepts)
            ]
        except Exception as e:
            logger.error(f"Plan extension failed: {e}")
            return [self._create_fallback_objective(remaining[:3])]

    async def _generate_curriculum_output(
        self,
        messages: list[dict],
        *,
        trace_name: str,
    ) -> CurriculumPlanOutput:
        """Generate curriculum JSON with one strict retry for malformed model outputs."""
        try:
            return await self.llm.generate_json(
                messages=messages,
                schema=CurriculumPlanOutput,
                temperature=0.2,
                max_tokens=4096,
                trace_name=trace_name,
            )
        except Exception as first_error:
            logger.warning(
                "Curriculum output parse failed (%s), retrying once: %s",
                trace_name,
                first_error,
            )
            return await self.llm.generate_json(
                messages=messages,
                schema=CurriculumPlanOutput,
                temperature=0.0,
                max_tokens=4096,
                trace_name=f"{trace_name}_retry",
            )
    
    async def _get_topic_bundles(self, resource_id: UUID) -> list[dict]:
        """Get topic bundles for resource."""
        result = await self.db.execute(
            select(ResourceTopicBundle)
            .where(ResourceTopicBundle.resource_id == resource_id)
        )
        bundles = result.scalars().all()
        
        return [
            {
                "topic_id": b.topic_id,
                "topic_name": b.topic_name,
                "primary_concepts": b.primary_concepts or [],
                "support_concepts": b.support_concepts or [],
            }
            for b in bundles
        ]
    
    async def _get_concepts(self, resource_id: UUID) -> list[str]:
        """Get admitted concepts for resource."""
        result = await self.db.execute(
            select(ResourceConceptStats.concept_id)
            .where(ResourceConceptStats.resource_id == resource_id)
            .order_by(ResourceConceptStats.teach_count.desc())
        )
        return [row[0] for row in result.fetchall()]

    async def _get_learning_objectives(self, resource_id: UUID) -> list[dict]:
        """Get ingestion-derived learning objective hints for the resource."""
        result = await self.db.execute(
            select(ResourceLearningObjective)
            .where(ResourceLearningObjective.resource_id == resource_id)
        )
        items = result.scalars().all()
        return [
            {
                "objective_text": item.objective_text,
                "specificity": item.specificity,
            }
            for item in items
        ]

    async def _get_concept_graph_edges(self, resource_id: UUID) -> list[dict]:
        """Get typed concept graph edges for the resource."""
        result = await self.db.execute(
            select(ResourceConceptGraph)
            .where(ResourceConceptGraph.resource_id == resource_id)
            .order_by(ResourceConceptGraph.confidence.desc())
        )
        edges = result.scalars().all()
        return [
            {
                "source": edge.source_concept_id,
                "target": edge.target_concept_id,
                "relation_type": edge.relation_type,
                "confidence": edge.confidence,
            }
            for edge in edges[:120]
        ]

    async def _get_prereq_hints(self, resource_id: UUID) -> list[dict]:
        """Get prerequisite hints for the resource."""
        result = await self.db.execute(
            select(ResourcePrereqHint)
            .where(ResourcePrereqHint.resource_id == resource_id)
            .order_by(ResourcePrereqHint.support_count.desc())
        )
        hints = result.scalars().all()
        return [
            {
                "source": hint.source_concept_id,
                "target": hint.target_concept_id,
                "support_count": hint.support_count,
            }
            for hint in hints[:80]
        ]
    
    def _build_messages(
        self,
        topic_bundles: list[dict],
        concepts: list[str],
        learning_objectives: list[dict],
        concept_graph_edges: list[dict],
        prereq_hints: list[dict],
        topic: Optional[str],
    ) -> list[dict]:
        """Build messages for LLM."""
        bundles_text = "\n".join([
            f"- {b['topic_name']}: {', '.join(b['primary_concepts'][:5])}"
            for b in topic_bundles[:5]
        ]) or "No topic bundles available"
        
        concepts_text = ", ".join(concepts[:30])
        learning_objectives_text = "\n".join(
            f"- {item.get('objective_text', '')}" for item in learning_objectives[:12]
        ) or "No extracted learning objectives available"
        graph_edges_text = "\n".join(
            f"- {edge['source']} -[{edge['relation_type']}]-> {edge['target']} (conf={edge['confidence']:.2f})"
            for edge in concept_graph_edges[:30]
        ) or "No concept graph edges available"
        prereq_hints_text = "\n".join(
            f"- {hint['source']} -> {hint['target']} (support={hint['support_count']})"
            for hint in prereq_hints[:20]
        ) or "No prerequisite hints available"
        
        user_content = f"""Create a curriculum plan for the following resource:

Topic Focus: {topic or "All topics"}

Available Topic Bundles:
{bundles_text}

Available Concepts (use these exact IDs):
{concepts_text}

Extracted Learning Objectives (primary grounding):
{learning_objectives_text}

Concept Graph Edges:
{graph_edges_text}

Prerequisite Hints:
{prereq_hints_text}

Generate 2-4 learning objectives that cover the key concepts, ordered by prerequisite dependencies.
"""
        
        return [
            {"role": "system", "content": CURRICULUM_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    
    def _validate_objective(
        self,
        obj: dict,
        valid_concepts: set[str],
    ) -> Optional[dict]:
        """Validate and fix objective."""
        if not isinstance(obj, dict):
            return None

        if not obj.get("objective_id") or not obj.get("title"):
            return None
        
        # Filter concepts to only valid ones
        scope = obj.get("concept_scope", {})
        if not isinstance(scope, dict):
            scope = {}
        primary = [c for c in scope.get("primary", []) if c in valid_concepts]
        support = [c for c in scope.get("support", []) if c in valid_concepts]
        prereq = [c for c in scope.get("prereq", []) if c in valid_concepts]
        
        if not primary:
            # Try to salvage by using any mentioned concepts
            all_mentioned = (
                scope.get("primary", []) +
                scope.get("support", []) +
                scope.get("prereq", [])
            )
            primary = [c for c in all_mentioned if c in valid_concepts][:2]
            if not primary:
                return None
        
        # Validate roadmap
        roadmap = obj.get("step_roadmap") or []
        if not isinstance(roadmap, list):
            roadmap = []
        valid_steps = {
            "motivate",
            "activate_prior",
            "define",
            "explain",
            "worked_example",
            "derive",
            "compare_contrast",
            "probe",
            "practice",
            "assess",
            "correct",
            "reflect",
            "connect",
            "summarize",
        }

        validated_roadmap = []
        for step in roadmap:
            if not isinstance(step, dict):
                continue
            step_type = step.get("type") or "explain"
            if step_type not in valid_steps:
                step_type = "explain"

            target_concepts = [
                c for c in step.get("target_concepts", [])
                if c in valid_concepts
            ] or primary[:1]

            max_turns = step.get("max_turns", 3)
            if not isinstance(max_turns, int):
                max_turns = 3
            max_turns = max(1, min(4, max_turns))

            validated_roadmap.append({
                "type": step_type,
                "target_concepts": target_concepts,
                "can_skip": bool(step.get("can_skip", False)),
                "max_turns": max_turns,
                "goal": step.get("goal") or "Drive understanding for this step.",
            })

        if not validated_roadmap:
            validated_roadmap = self._create_default_roadmap(primary)

        success_criteria = obj.get("success_criteria", {})
        if not isinstance(success_criteria, dict):
            success_criteria = {}

        return {
            "objective_id": obj["objective_id"],
            "title": obj["title"],
            "description": obj.get("description", obj["title"]),
            "concept_scope": {
                "primary": primary,
                "support": support,
                "prereq": prereq,
            },
            "success_criteria": {
                "min_correct": success_criteria.get("min_correct", 2),
                "min_mastery": success_criteria.get("min_mastery", 0.7),
            },
            "estimated_turns": obj.get("estimated_turns", 5),
            "step_roadmap": validated_roadmap,
        }

    def _create_default_roadmap(self, concepts: list[str]) -> list[dict]:
        """Create default step roadmap."""
        return [
            {
                "type": "motivate",
                "target_concepts": concepts[:1],
                "can_skip": True,
                "max_turns": 1,
                "goal": "Connect the concept to a concrete motivation.",
            },
            {
                "type": "define",
                "target_concepts": concepts,
                "can_skip": False,
                "max_turns": 2,
                "goal": "Establish a precise conceptual definition.",
            },
            {
                "type": "worked_example",
                "target_concepts": concepts,
                "can_skip": False,
                "max_turns": 2,
                "goal": "Walk through a representative example.",
            },
            {
                "type": "practice",
                "target_concepts": concepts,
                "can_skip": False,
                "max_turns": 2,
                "goal": "Student attempts a similar task with support available.",
            },
            {
                "type": "assess",
                "target_concepts": concepts,
                "can_skip": False,
                "max_turns": 2,
                "goal": "Student demonstrates independent mastery.",
            },
        ]
    
    def _create_fallback_objectives(self, concepts: list[str]) -> list[dict]:
        """Create multiple fallback objectives by chunking available concepts."""
        if not concepts:
            return [self._create_single_fallback("obj_01_fallback", ["general"], [])]

        # Chunk concepts into groups of 2 primary + up to 2 support
        objectives = []
        idx = 0
        obj_num = 1
        prev_primary = []

        while idx < len(concepts):
            primary = concepts[idx:idx + 2]
            support = concepts[idx + 2:idx + 4] if idx + 2 < len(concepts) else []
            prereq = prev_primary[:2]  # previous objective's primary are prereqs

            obj = self._create_single_fallback(
                f"obj_{obj_num:02d}_fallback",
                primary, support, prereq,
            )
            objectives.append(obj)
            prev_primary = primary
            idx += 2
            obj_num += 1

            if obj_num > 4:  # cap at 4 objectives
                break

        return objectives if objectives else [self._create_single_fallback("obj_01_fallback", concepts[:2], [])]

    def _create_fallback_objective(self, concepts: list[str]) -> dict:
        """Create a single fallback objective for legacy call sites."""
        primary = concepts[:2] if concepts else ["general"]
        support = concepts[2:4] if len(concepts) > 2 else []
        return self._create_single_fallback("obj_01_fallback", primary, support)

    def _create_single_fallback(
        self, obj_id: str, primary: list[str], support: list[str], prereq: list[str] = None,
    ) -> dict:
        """Create a single fallback objective."""
        title_concept = primary[0].replace("_", " ").title() if primary else "Core Concepts"
        return {
            "objective_id": obj_id,
            "title": f"Understanding {title_concept}",
            "description": f"Learn the fundamental concepts: {', '.join(primary)}",
            "concept_scope": {
                "primary": primary,
                "support": support,
                "prereq": prereq or [],
            },
            "success_criteria": {
                "min_correct": 2,
                "min_mastery": 0.6,
            },
            "estimated_turns": 5,
            "step_roadmap": self._create_default_roadmap(primary),
        }
