"""
Curriculum Agent - TICKET-024

Generates learning objectives and curriculum plans from resource content.
"""

from collections import defaultdict
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


MODE_CURRICULUM_GUIDANCE = {
    "learn": "Design a full teaching flow: concept introduction, explanation, worked examples, supported practice, then assessment.",
    "doubt": "Design a short clarification flow centered on resolving one confusion quickly. Prefer 1-2 tightly scoped objectives and explanation/probe/summary steps over long teaching arcs.",
    "practice": "Design a doing-first flow. Minimize exposition, prefer probe/practice/assess steps, and make the student produce answers early.",
    "revision": "Design a compact review flow. Prioritize recall, comparison, summary, misconception repair, and short assessment over first-teach exposition.",
}


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
        mode: str = "learn",
        scope_resource_ids: Optional[list[UUID | str]] = None,
        scope_type: Optional[str] = None,
        notebook_id: Optional[UUID | str] = None,
        objective_limit: Optional[int] = None,
    ) -> dict:
        """
        Generate a curriculum plan for a resource.

        Args:
            resource_id: UUID of the ingested resource
            topic: Optional topic focus

        Returns:
            Dict with active_topic and objective_queue
        """
        planning_resource_ids = self._normalize_resource_ids(
            scope_resource_ids,
            fallback_resource_id=resource_id,
        )
        planning_scope = self._scope_label(
            resource_ids=planning_resource_ids,
            scope_type=scope_type,
            notebook_id=notebook_id,
        )

        topic_bundles = await self._get_topic_bundles(planning_resource_ids)
        concepts = await self._get_concepts(planning_resource_ids)
        learning_objectives = await self._get_learning_objectives(planning_resource_ids)
        concept_graph_edges = await self._get_concept_graph_edges(planning_resource_ids)
        prereq_hints = await self._get_prereq_hints(planning_resource_ids)
        prereq_chains = self._build_prereq_chains(prereq_hints, concepts)

        if not concepts:
            logger.warning(
                "No concepts found for planning scope %s; generating fallback plan",
                planning_scope,
            )
            return self._finalize_plan_payload(
                active_topic=topic or "General",
                objectives=self._create_fallback_objectives(["general"], mode=mode),
                concepts=["general"],
                resource_ids=planning_resource_ids,
                scope_type=scope_type,
                notebook_id=notebook_id,
                objective_limit=objective_limit,
            )

        if selected_topics:
            filtered_bundles = [
                b
                for b in topic_bundles
                if b["topic_id"] in selected_topics
                or b["topic_name"] in selected_topics
            ]
            if filtered_bundles:
                topic_bundles = filtered_bundles
                selected_concepts = set()
                for b in filtered_bundles:
                    selected_concepts.update(b.get("primary_concepts", []))
                    selected_concepts.update(b.get("support_concepts", []))
                if selected_concepts:
                    concepts = [c for c in concepts if c in selected_concepts]
                    concept_graph_edges = [
                        edge
                        for edge in concept_graph_edges
                        if edge.get("source") in selected_concepts
                        and edge.get("target") in selected_concepts
                    ]
                    prereq_hints = [
                        hint
                        for hint in prereq_hints
                        if hint.get("source") in selected_concepts
                        and hint.get("target") in selected_concepts
                    ]
                    prereq_chains = [
                        chain
                        for chain in prereq_chains
                        if chain
                        and all(concept in selected_concepts for concept in chain)
                    ]

        messages = self._build_messages(
            topic_bundles,
            concepts,
            learning_objectives,
            concept_graph_edges,
            prereq_hints,
            prereq_chains,
            topic,
            mode,
            planning_scope=planning_scope,
            resource_count=len(planning_resource_ids),
            objective_limit=objective_limit,
        )

        try:
            output = await self._generate_curriculum_output(
                messages,
                trace_name="curriculum_generate_plan",
            )

            valid_concepts = set(concepts)
            validated_objectives = []

            for obj in output.objective_queue:
                validated_obj = self._validate_objective(obj, valid_concepts)
                if validated_obj:
                    validated_objectives.append(validated_obj)

            if not validated_objectives:
                validated_objectives = self._create_fallback_objectives(
                    concepts,
                    mode=mode,
                )

            validated_objectives = self._ensure_unique_objective_ids(
                validated_objectives
            )

            return self._finalize_plan_payload(
                active_topic=output.active_topic or topic or "General",
                objectives=validated_objectives,
                concepts=concepts,
                resource_ids=planning_resource_ids,
                scope_type=scope_type,
                notebook_id=notebook_id,
                objective_limit=objective_limit,
            )

        except Exception as e:
            logger.error(f"Curriculum generation failed: {e}")
            return self._finalize_plan_payload(
                active_topic=topic or "General",
                objectives=self._create_fallback_objectives(concepts, mode=mode),
                concepts=concepts,
                resource_ids=planning_resource_ids,
                scope_type=scope_type,
                notebook_id=notebook_id,
                objective_limit=objective_limit,
            )

    @observe(name="curriculum-extend", capture_input=False)
    async def extend_plan(
        self,
        resource_id: UUID,
        current_objectives: list[dict],
        completed_concepts: list[str],
        *,
        scope_resource_ids: Optional[list[UUID | str]] = None,
        topic: Optional[str] = None,
        selected_topics: Optional[list[str]] = None,
        mode: str = "learn",
        max_new_objectives: int = 2,
        existing_objective_ids: Optional[list[str]] = None,
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
        planning_resource_ids = self._normalize_resource_ids(
            scope_resource_ids,
            fallback_resource_id=resource_id,
        )
        planning_scope = self._scope_label(resource_ids=planning_resource_ids)
        topic_bundles = await self._get_topic_bundles(planning_resource_ids)
        concepts = await self._get_concepts(planning_resource_ids)
        learning_objectives = await self._get_learning_objectives(planning_resource_ids)
        concept_graph_edges = await self._get_concept_graph_edges(planning_resource_ids)
        prereq_hints = await self._get_prereq_hints(planning_resource_ids)
        prereq_chains = self._build_prereq_chains(prereq_hints, concepts)

        if selected_topics:
            filtered_bundles = [
                b
                for b in topic_bundles
                if b["topic_id"] in selected_topics
                or b["topic_name"] in selected_topics
            ]
            if filtered_bundles:
                topic_bundles = filtered_bundles
                selected_concepts = set()
                for b in filtered_bundles:
                    selected_concepts.update(b.get("primary_concepts", []))
                    selected_concepts.update(b.get("support_concepts", []))
                if selected_concepts:
                    concepts = [c for c in concepts if c in selected_concepts]
                    concept_graph_edges = [
                        edge
                        for edge in concept_graph_edges
                        if edge.get("source") in selected_concepts
                        and edge.get("target") in selected_concepts
                    ]
                    prereq_hints = [
                        hint
                        for hint in prereq_hints
                        if hint.get("source") in selected_concepts
                        and hint.get("target") in selected_concepts
                    ]
                    prereq_chains = [
                        chain
                        for chain in prereq_chains
                        if chain
                        and all(concept in selected_concepts for concept in chain)
                    ]

        covered = set(completed_concepts)
        for obj in current_objectives:
            scope = obj.get("concept_scope", {})
            covered.update(scope.get("primary", []))

        remaining = [c for c in concepts if c not in covered]

        if not remaining:
            return []

        messages = self._build_messages(
            [
                {
                    **bundle,
                    "primary_concepts": [
                        concept
                        for concept in bundle.get("primary_concepts", [])
                        if concept in set(remaining)
                    ],
                    "support_concepts": [
                        concept
                        for concept in bundle.get("support_concepts", [])
                        if concept in set(remaining)
                    ],
                }
                for bundle in topic_bundles
                if set(bundle.get("primary_concepts", []) or []) & set(remaining)
                or set(bundle.get("support_concepts", []) or []) & set(remaining)
            ],
            remaining,
            learning_objectives,
            [
                edge
                for edge in concept_graph_edges
                if edge.get("source") in set(remaining)
                and edge.get("target") in set(remaining)
            ],
            [
                hint
                for hint in prereq_hints
                if hint.get("source") in set(remaining)
                and hint.get("target") in set(remaining)
            ],
            [
                chain
                for chain in prereq_chains
                if chain and all(concept in set(remaining) for concept in chain)
            ],
            topic,
            mode,
            planning_scope=planning_scope,
            resource_count=len(planning_resource_ids),
            objective_limit=max_new_objectives,
        )

        try:
            output = await self._generate_curriculum_output(
                messages,
                trace_name="curriculum_extend_plan",
            )

            valid_concepts = set(remaining)
            extended = [
                self._validate_objective(obj, valid_concepts)
                for obj in output.objective_queue
                if self._validate_objective(obj, valid_concepts)
            ]
            extended = self._ensure_unique_objective_ids(
                extended,
                existing_ids=existing_objective_ids,
            )
            return extended[: max(1, max_new_objectives)]
        except Exception as e:
            logger.error(f"Plan extension failed: {e}")
            fallback = [self._create_fallback_objective(remaining[:3], mode=mode)]
            return self._ensure_unique_objective_ids(
                fallback,
                existing_ids=existing_objective_ids,
            )

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

    def _normalize_resource_ids(
        self,
        resource_ids: Optional[list[UUID | str]],
        *,
        fallback_resource_id: UUID,
    ) -> list[UUID]:
        normalized: list[UUID] = []
        seen: set[UUID] = set()
        for resource_id in resource_ids or []:
            value = (
                UUID(str(resource_id))
                if not isinstance(resource_id, UUID)
                else resource_id
            )
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        if fallback_resource_id not in seen:
            normalized.insert(0, fallback_resource_id)
        return normalized

    def _scope_label(
        self,
        *,
        resource_ids: list[UUID],
        scope_type: Optional[str] = None,
        notebook_id: Optional[UUID | str] = None,
    ) -> str:
        normalized_scope_type = (scope_type or "").strip() or (
            "notebook" if len(resource_ids) > 1 and notebook_id else "single_resource"
        )
        if notebook_id:
            return f"{normalized_scope_type}:{notebook_id}"
        return f"{normalized_scope_type}:{len(resource_ids)}"

    def _collect_objective_concepts(self, objectives: list[dict]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for obj in objectives:
            scope = obj.get("concept_scope", {}) or {}
            for concept in (
                list(scope.get("primary", []) or [])
                + list(scope.get("support", []) or [])
                + list(scope.get("prereq", []) or [])
            ):
                if concept in seen:
                    continue
                seen.add(concept)
                ordered.append(concept)
        return ordered

    def _ensure_unique_objective_ids(
        self,
        objectives: list[dict],
        *,
        existing_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        seen = {objective_id for objective_id in (existing_ids or []) if objective_id}
        normalized: list[dict] = []
        for index, obj in enumerate(objectives):
            candidate = str(obj.get("objective_id") or f"obj_{index + 1:02d}").strip()
            if not candidate:
                candidate = f"obj_{index + 1:02d}"
            if candidate in seen:
                suffix = 2
                base = candidate
                while f"{base}_{suffix}" in seen:
                    suffix += 1
                candidate = f"{base}_{suffix}"
            updated = dict(obj)
            updated["objective_id"] = candidate
            normalized.append(updated)
            seen.add(candidate)
        return normalized

    def _build_prereq_chains(
        self,
        prereq_hints: list[dict],
        concepts: list[str],
    ) -> list[list[str]]:
        adjacency: dict[str, list[tuple[str, int]]] = defaultdict(list)
        incoming: set[str] = set()
        for hint in prereq_hints:
            source = hint.get("source")
            target = hint.get("target")
            support = int(hint.get("support_count", 0) or 0)
            if not source or not target or source == target:
                continue
            adjacency[source].append((target, support))
            incoming.add(target)

        roots = [
            concept
            for concept in concepts
            if concept in adjacency and concept not in incoming
        ]
        if not roots:
            roots = [concept for concept in concepts if concept in adjacency][:6]

        chains: list[list[str]] = []
        seen_paths: set[tuple[str, ...]] = set()

        def _walk(node: str, path: list[str]) -> None:
            if len(chains) >= 8:
                return
            next_nodes = sorted(
                adjacency.get(node, []),
                key=lambda item: (-item[1], item[0]),
            )
            if not next_nodes and len(path) >= 2:
                path_key = tuple(path)
                if path_key not in seen_paths:
                    seen_paths.add(path_key)
                    chains.append(path[:])
                return
            for next_node, _support in next_nodes[:3]:
                if next_node in path or len(path) >= 4:
                    continue
                _walk(next_node, path + [next_node])

        for root in roots[:6]:
            _walk(root, [root])
            if len(chains) >= 8:
                break

        return chains

    def _finalize_plan_payload(
        self,
        *,
        active_topic: str,
        objectives: list[dict],
        concepts: list[str],
        resource_ids: list[UUID],
        scope_type: Optional[str],
        notebook_id: Optional[UUID | str],
        objective_limit: Optional[int],
    ) -> dict:
        normalized_objectives = list(objectives or [])
        if objective_limit and objective_limit > 0:
            normalized_objectives = normalized_objectives[:objective_limit]
        covered_concepts = set(self._collect_objective_concepts(normalized_objectives))
        remaining_concepts = [
            concept for concept in concepts if concept not in covered_concepts
        ]
        rolling_enabled = bool(objective_limit and remaining_concepts)
        normalized_scope_type = (scope_type or "").strip() or (
            "notebook" if len(resource_ids) > 1 and notebook_id else "single_resource"
        )
        plan_horizon = {
            "version": 1,
            "strategy": "rolling" if rolling_enabled else "fixed",
            "visible_objectives": len(normalized_objectives),
            "objective_limit": objective_limit or len(normalized_objectives),
            "remaining_concepts_estimate": len(remaining_concepts),
            "remaining_concepts_sample": remaining_concepts[:8],
        }
        curriculum_planner = {
            "version": 1,
            "scope_type": normalized_scope_type,
            "notebook_id": str(notebook_id) if notebook_id else None,
            "resource_ids": [str(resource_id) for resource_id in resource_ids],
            "resource_count": len(resource_ids),
            "rolling_enabled": rolling_enabled,
            "exhausted": not rolling_enabled,
            "objective_batch_size": objective_limit or len(normalized_objectives),
            "extend_when_remaining": 1,
            "extension_count": 0,
            "remaining_concepts_estimate": len(remaining_concepts),
            "total_concepts": len(concepts),
            "last_planning_mode": "initial",
        }
        return {
            "active_topic": active_topic,
            "objective_queue": normalized_objectives,
            "plan_horizon": plan_horizon,
            "curriculum_planner": curriculum_planner,
        }

    async def _get_topic_bundles(self, resource_ids: list[UUID]) -> list[dict]:
        result = await self.db.execute(
            select(ResourceTopicBundle).where(
                ResourceTopicBundle.resource_id.in_(resource_ids)
            )
        )
        bundles = result.scalars().all()
        merged: dict[str, dict] = {}

        for bundle in bundles:
            key = bundle.topic_id or bundle.topic_name
            record = merged.setdefault(
                key,
                {
                    "topic_id": bundle.topic_id,
                    "topic_name": bundle.topic_name,
                    "primary_concepts": [],
                    "support_concepts": [],
                },
            )
            for concept in bundle.primary_concepts or []:
                if concept not in record["primary_concepts"]:
                    record["primary_concepts"].append(concept)
            for concept in bundle.support_concepts or []:
                if concept in record["primary_concepts"]:
                    continue
                if concept not in record["support_concepts"]:
                    record["support_concepts"].append(concept)

        return sorted(
            merged.values(),
            key=lambda item: (-len(item["primary_concepts"]), item["topic_name"]),
        )

    async def _get_concepts(self, resource_ids: list[UUID]) -> list[str]:
        result = await self.db.execute(
            select(ResourceConceptStats).where(
                ResourceConceptStats.resource_id.in_(resource_ids)
            )
        )
        rows = result.scalars().all()
        aggregated: dict[str, dict] = defaultdict(
            lambda: {"teach_count": 0, "importance_score": 0.0, "topo_order": None}
        )

        for row in rows:
            record = aggregated[row.concept_id]
            record["teach_count"] += int(row.teach_count or 0)
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
            aggregated.items(),
            key=lambda item: (
                item[1]["topo_order"] is None,
                item[1]["topo_order"] if item[1]["topo_order"] is not None else 10**9,
                -item[1]["teach_count"],
                -item[1]["importance_score"],
                item[0],
            ),
        )
        return [concept_id for concept_id, _meta in ordered]

    async def _get_learning_objectives(self, resource_ids: list[UUID]) -> list[dict]:
        result = await self.db.execute(
            select(ResourceLearningObjective).where(
                ResourceLearningObjective.resource_id.in_(resource_ids)
            )
        )
        items = result.scalars().all()
        seen: set[tuple[str, str | None]] = set()
        ordered: list[dict] = []
        for item in items:
            key = (item.objective_text, item.specificity)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(
                {
                    "objective_text": item.objective_text,
                    "specificity": item.specificity,
                }
            )
        return ordered

    async def _get_concept_graph_edges(self, resource_ids: list[UUID]) -> list[dict]:
        result = await self.db.execute(
            select(ResourceConceptGraph)
            .where(ResourceConceptGraph.resource_id.in_(resource_ids))
            .order_by(ResourceConceptGraph.confidence.desc())
        )
        edges = result.scalars().all()
        merged: dict[tuple[str, str, str], dict] = {}

        for edge in edges:
            key = (
                edge.source_concept_id,
                edge.target_concept_id,
                edge.relation_type,
            )
            record = merged.setdefault(
                key,
                {
                    "source": edge.source_concept_id,
                    "target": edge.target_concept_id,
                    "relation_type": edge.relation_type,
                    "confidence": float(edge.confidence or 0.0),
                    "assoc_weight": float(edge.assoc_weight or 0.0),
                },
            )
            record["confidence"] = max(
                float(record.get("confidence") or 0.0),
                float(edge.confidence or 0.0),
            )
            record["assoc_weight"] = max(
                float(record.get("assoc_weight") or 0.0),
                float(edge.assoc_weight or 0.0),
            )

        ordered = sorted(
            merged.values(),
            key=lambda item: (
                -float(item.get("confidence") or 0.0),
                -float(item.get("assoc_weight") or 0.0),
                item.get("source") or "",
                item.get("target") or "",
            ),
        )
        return ordered[:160]

    async def _get_prereq_hints(self, resource_ids: list[UUID]) -> list[dict]:
        result = await self.db.execute(
            select(ResourcePrereqHint)
            .where(ResourcePrereqHint.resource_id.in_(resource_ids))
            .order_by(ResourcePrereqHint.support_count.desc())
        )
        hints = result.scalars().all()
        merged: dict[tuple[str, str], dict] = {}

        for hint in hints:
            key = (hint.source_concept_id, hint.target_concept_id)
            record = merged.setdefault(
                key,
                {
                    "source": hint.source_concept_id,
                    "target": hint.target_concept_id,
                    "support_count": 0,
                },
            )
            record["support_count"] += int(hint.support_count or 0)

        ordered = sorted(
            merged.values(),
            key=lambda item: (
                -int(item.get("support_count") or 0),
                item.get("source") or "",
                item.get("target") or "",
            ),
        )
        return ordered[:120]

    def _build_messages(
        self,
        topic_bundles: list[dict],
        concepts: list[str],
        learning_objectives: list[dict],
        concept_graph_edges: list[dict],
        prereq_hints: list[dict],
        prereq_chains: list[list[str]],
        topic: Optional[str],
        mode: str,
        *,
        planning_scope: str,
        resource_count: int,
        objective_limit: Optional[int],
    ) -> list[dict]:
        """Build messages for LLM."""
        bundles_text = (
            "\n".join(
                [
                    f"- {b['topic_name']}: {', '.join(b['primary_concepts'][:5])}"
                    for b in topic_bundles[:5]
                ]
            )
            or "No topic bundles available"
        )

        concepts_text = ", ".join(concepts[:30])
        learning_objectives_text = (
            "\n".join(
                f"- {item.get('objective_text', '')}"
                for item in learning_objectives[:12]
            )
            or "No extracted learning objectives available"
        )
        graph_edges_text = (
            "\n".join(
                f"- {edge['source']} -[{edge['relation_type']}]-> {edge['target']} (conf={edge['confidence']:.2f})"
                for edge in concept_graph_edges[:30]
            )
            or "No concept graph edges available"
        )
        prereq_hints_text = (
            "\n".join(
                f"- {hint['source']} -> {hint['target']} (support={hint['support_count']})"
                for hint in prereq_hints[:20]
            )
            or "No prerequisite hints available"
        )
        prereq_chains_text = (
            "\n".join(
                f"- {' -> '.join(chain)}"
                for chain in prereq_chains[:12]
                if len(chain) >= 2
            )
            or "No prerequisite chains available"
        )

        normalized_mode = (mode or "learn").strip().lower()
        mode_guidance = MODE_CURRICULUM_GUIDANCE.get(
            normalized_mode, MODE_CURRICULUM_GUIDANCE["learn"]
        )
        max_objective_text = (
            str(max(1, int(objective_limit))) if objective_limit else "4"
        )

        user_content = f"""Create a curriculum plan for the following knowledge scope:

    Session Mode: {normalized_mode}
    Mode Guidance: {mode_guidance}
    Planning Scope: {planning_scope}
    Resource Count: {resource_count}

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

Combined Prerequisite Chains:
{prereq_chains_text}

Generate 1-{max_objective_text} learning objectives that cover the next most important concepts, ordered by prerequisite dependencies.
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
                scope.get("primary", [])
                + scope.get("support", [])
                + scope.get("prereq", [])
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
                c for c in step.get("target_concepts", []) if c in valid_concepts
            ] or primary[:1]

            max_turns = step.get("max_turns", 3)
            if not isinstance(max_turns, int):
                max_turns = 3
            max_turns = max(1, min(4, max_turns))

            validated_roadmap.append(
                {
                    "type": step_type,
                    "target_concepts": target_concepts,
                    "can_skip": bool(step.get("can_skip", False)),
                    "max_turns": max_turns,
                    "goal": step.get("goal") or "Drive understanding for this step.",
                }
            )

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

    def _create_default_roadmap(
        self, concepts: list[str], mode: str = "learn"
    ) -> list[dict]:
        """Create default step roadmap."""
        normalized_mode = (mode or "learn").strip().lower()
        if normalized_mode == "doubt":
            return [
                {
                    "type": "explain",
                    "target_concepts": concepts[:1],
                    "can_skip": True,
                    "max_turns": 2,
                    "goal": "Resolve the learner's specific confusion directly and accurately.",
                },
                {
                    "type": "probe",
                    "target_concepts": concepts[:1],
                    "can_skip": True,
                    "max_turns": 1,
                    "goal": "Check whether the clarification actually resolved the confusion.",
                },
                {
                    "type": "summarize",
                    "target_concepts": concepts[:1],
                    "can_skip": True,
                    "max_turns": 1,
                    "goal": "Summarize the answer crisply and note what to revisit if needed.",
                },
            ]
        if normalized_mode == "practice":
            return [
                {
                    "type": "probe",
                    "target_concepts": concepts[:1],
                    "can_skip": False,
                    "max_turns": 1,
                    "goal": "Elicit the learner's current attempt before teaching further.",
                },
                {
                    "type": "practice",
                    "target_concepts": concepts,
                    "can_skip": False,
                    "max_turns": 2,
                    "goal": "Have the learner solve a representative task with limited support.",
                },
                {
                    "type": "assess",
                    "target_concepts": concepts,
                    "can_skip": False,
                    "max_turns": 2,
                    "goal": "Check for independent performance on the target concepts.",
                },
            ]
        if normalized_mode == "revision":
            return [
                {
                    "type": "summarize",
                    "target_concepts": concepts[:1],
                    "can_skip": False,
                    "max_turns": 1,
                    "goal": "Compress the core idea into a concise review frame.",
                },
                {
                    "type": "compare_contrast",
                    "target_concepts": concepts,
                    "can_skip": True,
                    "max_turns": 1,
                    "goal": "Differentiate easily confused concepts and surface weak spots.",
                },
                {
                    "type": "assess",
                    "target_concepts": concepts,
                    "can_skip": False,
                    "max_turns": 2,
                    "goal": "Use recall and quick checks to verify the learner can retrieve the idea unaided.",
                },
            ]

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

    def _create_fallback_objectives(
        self, concepts: list[str], mode: str = "learn"
    ) -> list[dict]:
        """Create multiple fallback objectives by chunking available concepts."""
        if not concepts:
            return [
                self._create_single_fallback(
                    "obj_01_fallback", ["general"], [], mode=mode
                )
            ]

        # Chunk concepts into groups of 2 primary + up to 2 support
        objectives = []
        idx = 0
        obj_num = 1
        prev_primary = []

        while idx < len(concepts):
            primary = concepts[idx : idx + 2]
            support = concepts[idx + 2 : idx + 4] if idx + 2 < len(concepts) else []
            prereq = prev_primary[:2]  # previous objective's primary are prereqs

            obj = self._create_single_fallback(
                f"obj_{obj_num:02d}_fallback",
                primary,
                support,
                prereq,
                mode=mode,
            )
            objectives.append(obj)
            prev_primary = primary
            idx += 2
            obj_num += 1

            if obj_num > 4:  # cap at 4 objectives
                break

        return (
            objectives
            if objectives
            else [
                self._create_single_fallback(
                    "obj_01_fallback", concepts[:2], [], mode=mode
                )
            ]
        )

    def _create_fallback_objective(
        self, concepts: list[str], mode: str = "learn"
    ) -> dict:
        """Create a single fallback objective for legacy call sites."""
        primary = concepts[:2] if concepts else ["general"]
        support = concepts[2:4] if len(concepts) > 2 else []
        return self._create_single_fallback(
            "obj_01_fallback", primary, support, mode=mode
        )

    def _create_single_fallback(
        self,
        obj_id: str,
        primary: list[str],
        support: list[str],
        prereq: list[str] = None,
        mode: str = "learn",
    ) -> dict:
        """Create a single fallback objective."""
        title_concept = (
            primary[0].replace("_", " ").title() if primary else "Core Concepts"
        )
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
            "step_roadmap": self._create_default_roadmap(primary, mode=mode),
        }
