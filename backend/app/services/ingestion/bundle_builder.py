"""
Bundle Builder - TICKET-017

Build concept and topic bundles for retrieval.
"""

import logging
import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.knowledge_base import (
    ResourceConceptStats,
    ResourceConceptEvidence,
    ResourceConceptGraph,
    ResourceBundle,
    ResourceTopicBundle,
    ResourcePrereqHint,
)

logger = logging.getLogger(__name__)


class BundleBuilder:
    """Builds concept and topic bundles for efficient retrieval."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def build_concept_bundles(
        self,
        resource_id: uuid.UUID,
        top_k_support: int = 5,
        force_rebuild: bool = False,
    ) -> dict:
        """
        Build per-concept bundles.

        Args:
            resource_id: UUID of the resource
            top_k_support: Number of support concepts to include
            force_rebuild: If True, clear existing bundles before rebuilding

        Returns:
            Dict with build metrics
        """
        if force_rebuild:
            await self._clear_bundles(resource_id)

        # Get admitted concepts
        concepts = await self._get_admitted_concepts(resource_id)
        if not concepts:
            logger.warning(f"No concepts found for resource {resource_id}")
            return {"bundles_created": 0}

        # Get graph and evidence
        graph = await self._get_graph(resource_id)
        evidence = await self._get_evidence(resource_id)
        prereqs = await self._get_prereq_hints(resource_id)

        bundles = []
        for concept in concepts:
            # Get top-k neighbors as support (both directions)
            neighbors = [
                e
                for e in graph
                if e.source_concept_id == concept or e.target_concept_id == concept
            ]
            neighbors.sort(key=lambda x: -x.assoc_weight)
            support = []
            for n in neighbors[:top_k_support]:
                other = (
                    n.target_concept_id
                    if n.source_concept_id == concept
                    else n.source_concept_id
                )
                if other not in support:
                    support.append(other)

            # Get prereq hints for this concept
            concept_prereqs = [
                p.target_concept_id for p in prereqs if p.source_concept_id == concept
            ]

            # Get prototype chunks (highest quality evidence)
            concept_evidence = [e for e in evidence if e.concept_id == concept]
            concept_evidence.sort(key=lambda x: -(x.quality_score or 0.5))

            prototypes = {
                "teaches": [
                    str(e.chunk_id) for e in concept_evidence if e.role == "teaches"
                ][:3],
                "exemplifies": [
                    str(e.chunk_id) for e in concept_evidence if e.role == "exemplifies"
                ][:2],
                "mentions": [
                    str(e.chunk_id) for e in concept_evidence if e.role == "mentions"
                ][:2],
            }

            bundles.append(
                ResourceBundle(
                    resource_id=resource_id,
                    primary_concept_id=concept,
                    support_concepts=support,
                    prereq_hints=concept_prereqs,
                    evidence_prototypes=prototypes,
                )
            )

        self.db.add_all(bundles)
        await self.db.flush()

        logger.info(
            f"Created {len(bundles)} concept bundles for resource {resource_id}"
        )
        return {"bundles_created": len(bundles)}

    async def build_topic_bundles(
        self,
        resource_id: uuid.UUID,
        max_topics: int = 10,
        force_rebuild: bool = False,
    ) -> dict:
        """
        Group concepts into topic bundles.

        Uses a simple clustering approach:
        1. Compute adjacency from resource_concept_graph
        2. Seed topics by highest-degree concepts
        3. Greedy-assign neighbors to nearest seed
        4. Select representative chunks from evidence for each topic

        Args:
            resource_id: UUID of the resource
            max_topics: Maximum number of topics to create
            force_rebuild: If True, clear existing topic bundles before rebuilding

        Returns:
            Dict with build metrics
        """
        if force_rebuild:
            await self._clear_topic_bundles(resource_id)

        # Get graph edges
        graph = await self._get_graph(resource_id)
        if not graph:
            logger.warning(f"No graph found for resource {resource_id}")
            return {"topic_bundles_created": 0}

        # Compute degrees (both directions)
        degree: dict[str, int] = defaultdict(int)
        adjacency: dict[str, set[str]] = defaultdict(set)

        for edge in graph:
            degree[edge.source_concept_id] += 1
            degree[edge.target_concept_id] += 1
            adjacency[edge.source_concept_id].add(edge.target_concept_id)
            adjacency[edge.target_concept_id].add(edge.source_concept_id)

        concepts = list(degree.keys())
        if not concepts:
            return {"topic_bundles_created": 0}

        # Select seed concepts (highest degree, limited by max_topics)
        sorted_by_degree = sorted(concepts, key=lambda x: -degree[x])
        seeds = sorted_by_degree[:max_topics]

        # Assign each concept to nearest seed
        topic_assignments: dict[str, str] = {}
        for seed in seeds:
            topic_assignments[seed] = seed

        # Assign remaining concepts
        for concept in concepts:
            if concept in topic_assignments:
                continue

            # Find seed with highest adjacency
            best_seed = None
            best_overlap = 0

            for seed in seeds:
                overlap = len(adjacency[concept] & adjacency[seed])
                if seed in adjacency[concept]:
                    overlap += 2  # Bonus for direct connection

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_seed = seed

            if best_seed:
                topic_assignments[concept] = best_seed
            else:
                # Assign to first seed if no overlap
                topic_assignments[concept] = seeds[0]

        # Group concepts by topic
        topic_concepts: dict[str, list[str]] = defaultdict(list)
        for concept, topic_seed in topic_assignments.items():
            topic_concepts[topic_seed].append(concept)

        # Get evidence for representative chunks
        evidence = await self._get_evidence(resource_id)

        # Get prereq hints for cross-topic prerequisite edges
        prereqs = await self._get_prereq_hints(resource_id)

        # Build concept -> topic_id lookup
        concept_to_topic: dict[str, str] = {}
        topic_id_list: list[str] = []
        for i, (seed_concept, concepts_in_topic) in enumerate(topic_concepts.items()):
            tid = f"topic_{i}"
            topic_id_list.append(tid)
            for c in concepts_in_topic:
                concept_to_topic[c] = tid

        # Compute topic-level prerequisites
        topic_prereq_map: dict[str, set[str]] = defaultdict(set)
        for hint in prereqs:
            src_topic = concept_to_topic.get(hint.source_concept_id)
            tgt_topic = concept_to_topic.get(hint.target_concept_id)
            if src_topic and tgt_topic and src_topic != tgt_topic:
                # source_concept REQUIRES target_concept -> src_topic depends on tgt_topic
                topic_prereq_map[src_topic].add(tgt_topic)

        # Also infer from directed graph edges
        directed_types = {"REQUIRES", "ENABLES", "DERIVES_FROM"}
        for edge in graph:
            if edge.relation_type in directed_types:
                src_topic = concept_to_topic.get(edge.source_concept_id)
                tgt_topic = concept_to_topic.get(edge.target_concept_id)
                if src_topic and tgt_topic and src_topic != tgt_topic:
                    topic_prereq_map[src_topic].add(tgt_topic)

        # Create topic bundles
        topic_bundles = []
        for i, (seed_concept, concepts_in_topic) in enumerate(topic_concepts.items()):
            tid = f"topic_{i}"
            # Get representative chunks from evidence
            topic_evidence = [
                e
                for e in evidence
                if e.concept_id in concepts_in_topic and e.role == "teaches"
            ]
            topic_evidence.sort(key=lambda x: -(x.quality_score or 0.5))
            representative_chunks = [str(e.chunk_id) for e in topic_evidence[:5]]

            topic_bundles.append(
                ResourceTopicBundle(
                    resource_id=resource_id,
                    topic_id=tid,
                    topic_name=seed_concept.replace("_", " ").title(),
                    primary_concepts=concepts_in_topic,
                    representative_chunk_ids=representative_chunks,
                    prereq_topic_ids=list(topic_prereq_map.get(tid, [])) or None,
                )
            )

        self.db.add_all(topic_bundles)
        await self.db.flush()

        logger.info(
            f"Created {len(topic_bundles)} topic bundles for resource {resource_id}"
        )
        return {"topic_bundles_created": len(topic_bundles)}

    async def _get_admitted_concepts(self, resource_id: uuid.UUID) -> list[str]:
        """Get all admitted concepts for a resource."""
        result = await self.db.execute(
            select(ResourceConceptStats.concept_id).where(
                ResourceConceptStats.resource_id == resource_id
            )
        )
        return [row[0] for row in result.all()]

    async def _get_graph(self, resource_id: uuid.UUID) -> list[ResourceConceptGraph]:
        """Get graph edges for a resource."""
        result = await self.db.execute(
            select(ResourceConceptGraph).where(
                ResourceConceptGraph.resource_id == resource_id
            )
        )
        return list(result.scalars().all())

    async def _get_evidence(
        self, resource_id: uuid.UUID
    ) -> list[ResourceConceptEvidence]:
        """Get evidence for a resource."""
        result = await self.db.execute(
            select(ResourceConceptEvidence).where(
                ResourceConceptEvidence.resource_id == resource_id
            )
        )
        return list(result.scalars().all())

    async def _get_prereq_hints(
        self, resource_id: uuid.UUID
    ) -> list[ResourcePrereqHint]:
        """Get prereq hints for a resource."""
        result = await self.db.execute(
            select(ResourcePrereqHint).where(
                ResourcePrereqHint.resource_id == resource_id
            )
        )
        return list(result.scalars().all())

    async def _clear_bundles(self, resource_id: uuid.UUID) -> None:
        """Clear existing bundles for a resource."""
        await self.db.execute(
            delete(ResourceBundle).where(ResourceBundle.resource_id == resource_id)
        )
        await self.db.flush()

    async def _clear_topic_bundles(self, resource_id: uuid.UUID) -> None:
        """Clear existing topic bundles for a resource."""
        await self.db.execute(
            delete(ResourceTopicBundle).where(
                ResourceTopicBundle.resource_id == resource_id
            )
        )
        await self.db.flush()
