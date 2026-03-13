"""
Resource KB Builder - TICKET-015

Build per-resource Knowledge Base from enriched chunks.
"""

import logging
import math
import uuid
from collections import defaultdict
from typing import Optional
import statistics

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.chunk import Chunk
from app.models.knowledge_base import (
    ResourceConceptStats,
    ResourceConceptEvidence,
    ResourcePrereqHint,
)
from app.utils.canonicalization import canonicalize_concept_id

logger = logging.getLogger(__name__)


class ResourceKBBuilder:
    """Builds per-resource knowledge base artifacts from enriched chunks."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def build(
        self,
        resource_id: uuid.UUID,
        force_rebuild: bool = False,
        ontology_relations: Optional[list[dict]] = None,
    ) -> dict:
        """
        Build knowledge base artifacts for a resource.

        Args:
            resource_id: UUID of the resource
            force_rebuild: If True, clear existing artifacts before rebuilding

        Returns:
            Dict with build metrics
        """
        if force_rebuild:
            await self._clear_kb_artifacts(resource_id)

        # Get enriched chunks
        chunks = await self._get_chunks(resource_id)
        if not chunks:
            logger.warning(f"No chunks found for resource {resource_id}")
            return {"concepts_admitted": 0, "evidence_created": 0}

        # Parse enrichments
        enrichments = []
        for chunk in chunks:
            if chunk.enrichment_metadata:
                enrichments.append(chunk.enrichment_metadata)
            else:
                enrichments.append({})

        # Step 1: Admit concepts based on thresholds (now returns metadata too)
        admitted, concept_metadata = await self._admit_concepts(
            resource_id, enrichments
        )
        logger.info(f"Admitted {len(admitted)} concepts for resource {resource_id}")

        # Step 2: Build evidence table
        evidence_count = await self._build_concept_evidence(
            resource_id, chunks, enrichments, admitted
        )

        # Step 3: Build stats table with ontological metadata
        await self._build_concept_stats(
            resource_id, chunks, enrichments, admitted, concept_metadata
        )

        # Step 4: Build prereq hints
        prereq_count = await self._build_prereq_hints(
            resource_id,
            enrichments,
            admitted,
            ontology_relations=ontology_relations,
        )

        await self.db.commit()

        return {
            "concepts_admitted": len(admitted),
            "evidence_created": evidence_count,
            "prereq_hints_created": prereq_count,
        }

    async def _get_chunks(self, resource_id: uuid.UUID) -> list[Chunk]:
        """Get all chunks for a resource ordered by index."""
        result = await self.db.execute(
            select(Chunk)
            .where(Chunk.resource_id == resource_id)
            .order_by(Chunk.chunk_index)
        )
        return list(result.scalars().all())

    async def _clear_kb_artifacts(self, resource_id: uuid.UUID) -> None:
        """Clear existing KB artifacts for a resource."""
        await self.db.execute(
            delete(ResourceConceptStats).where(
                ResourceConceptStats.resource_id == resource_id
            )
        )
        await self.db.execute(
            delete(ResourceConceptEvidence).where(
                ResourceConceptEvidence.resource_id == resource_id
            )
        )
        await self.db.execute(
            delete(ResourcePrereqHint).where(
                ResourcePrereqHint.resource_id == resource_id
            )
        )
        await self.db.flush()

    async def _admit_concepts(
        self,
        resource_id: uuid.UUID,
        enrichments: list[dict],
    ) -> tuple[set[str], dict[str, dict]]:
        """
        Admit concepts meeting thresholds and collect their metadata.

        Admission criteria (with importance weighting):
        - Core concepts get a bonus for admission
        - Concepts with explicit relationships get a bonus
        - Tiered thresholds based on document size

        Returns:
            Tuple of (admitted concept IDs, concept metadata dict)
        """
        # Track counts and metadata for each concept
        concept_data: dict[str, dict] = defaultdict(
            lambda: {
                "teach": 0,
                "mention": 0,
                "chunks": set(),
                "concept_types": [],
                "bloom_levels": [],
                "importances": [],
                "has_relationships": False,
            }
        )

        for i, enrichment in enumerate(enrichments):
            # Process taught concepts (may include metadata)
            for concept in enrichment.get("concepts_taught", []):
                concept_data[concept]["teach"] += 1
                concept_data[concept]["chunks"].add(i)

            # Process concept metadata if available
            for meta in enrichment.get("concept_metadata", []):
                if isinstance(meta, dict):
                    cid = meta.get("concept_id")
                    if cid:
                        concept_data[cid]["concept_types"].append(
                            meta.get("concept_type", "principle")
                        )
                        concept_data[cid]["bloom_levels"].append(
                            meta.get("bloom_level", "understand")
                        )
                        importance = meta.get("importance", "core")
                        concept_data[cid]["importances"].append(importance)

            # Process mentioned concepts
            for concept in enrichment.get("concepts_mentioned", []):
                concept_data[concept]["mention"] += 1
                concept_data[concept]["chunks"].add(i)

            # Mark concepts involved in semantic relationships
            for rel in enrichment.get("semantic_relationships", []):
                if isinstance(rel, dict):
                    src = rel.get("source_id")
                    tgt = rel.get("target_id")
                    if src:
                        concept_data[src]["has_relationships"] = True
                    if tgt:
                        concept_data[tgt]["has_relationships"] = True

        admitted = set()
        concept_metadata: dict[str, dict] = {}
        total_chunks = len(enrichments)

        # Tiered thresholds based on document size (logarithmic scaling for large docs)
        if total_chunks <= 4:
            min_teach = 1
            min_score = 1.2
            min_chunk_count = 1
        elif total_chunks <= 12:
            min_teach = 1
            min_score = 1.5
            min_chunk_count = 1
        else:
            # Scale with document size (logarithmic)
            min_teach = min(2 + int(math.log2(total_chunks / 12)), 5)
            min_score = min(2.0 + 0.5 * math.log2(total_chunks / 12), 4.0)
            min_chunk_count = 2

        # Importance weights
        importance_weights = {"core": 1.0, "supporting": 0.5, "peripheral": 0.2}
        mention_weight = 0.2  # Slightly higher than before for better coverage
        relationship_bonus = 0.5  # Bonus for concepts in explicit relationships

        for concept, data in concept_data.items():
            # Calculate importance-weighted score
            base_score = data["teach"] + mention_weight * data["mention"]

            # Apply importance weighting
            if data["importances"]:
                avg_importance = sum(
                    importance_weights.get(imp, 0.5) for imp in data["importances"]
                ) / len(data["importances"])
                base_score *= 0.5 + avg_importance  # Scale by 0.5-1.5x

            # Bonus for concepts with explicit relationships
            if data["has_relationships"]:
                base_score += relationship_bonus

            chunk_count = len(data["chunks"])

            if chunk_count < min_chunk_count:
                continue

            if data["teach"] >= min_teach or base_score >= min_score:
                admitted.add(concept)

                # Aggregate metadata for this concept
                concept_metadata[concept] = {
                    "concept_type": self._most_common(data["concept_types"])
                    or "principle",
                    "bloom_level": self._highest_bloom(data["bloom_levels"])
                    or "understand",
                    "importance_score": base_score / max(total_chunks, 1),
                }

        logger.debug(
            f"Concept admission: {len(admitted)}/{len(concept_data)} admitted "
            f"(total_chunks={total_chunks}, min_teach={min_teach}, min_score={min_score})"
        )

        return admitted, concept_metadata

    def _most_common(self, items: list) -> Optional[str]:
        """Return the most common item in a list."""
        if not items:
            return None
        counts = defaultdict(int)
        for item in items:
            counts[item] += 1
        return max(counts, key=counts.get)

    def _compute_distribution(self, items: list[str]) -> dict[str, float]:
        """Compute proportional distribution from a list of labels."""
        if not items:
            return {}
        counts: dict[str, int] = defaultdict(int)
        for item in items:
            if item:
                counts[item] += 1
        total = len(items)
        return {
            k: round(v / total, 3)
            for k, v in sorted(counts.items(), key=lambda x: -x[1])
        }

    def _highest_bloom(self, levels: list) -> Optional[str]:
        """Return the highest Bloom's taxonomy level from a list."""
        if not levels:
            return None
        bloom_order = [
            "remember",
            "understand",
            "apply",
            "analyze",
            "evaluate",
            "create",
        ]
        highest_idx = -1
        highest_level = None
        for level in levels:
            if level in bloom_order:
                idx = bloom_order.index(level)
                if idx > highest_idx:
                    highest_idx = idx
                    highest_level = level
        return highest_level or "understand"

    async def _build_concept_evidence(
        self,
        resource_id: uuid.UUID,
        chunks: list[Chunk],
        enrichments: list[dict],
        admitted: set[str],
    ) -> int:
        """Build resource_concept_evidence table."""
        evidence_rows = []

        for i, (chunk, enrichment) in enumerate(zip(chunks, enrichments)):
            quality = enrichment.get("quality_score", 0.5)
            pedagogy_role = enrichment.get("pedagogy_role", "explanation")

            # Concepts taught -> "teaches" role
            for concept in enrichment.get("concepts_taught", []):
                if concept in admitted:
                    evidence_rows.append(
                        ResourceConceptEvidence(
                            resource_id=resource_id,
                            concept_id=concept,
                            chunk_id=chunk.id,
                            role="teaches",
                            weight=1.0,
                            quality_score=quality,
                            position_index=i,
                        )
                    )

                    # Add "exemplifies" role for examples/exercises
                    if pedagogy_role in ["example", "exercise"]:
                        evidence_rows.append(
                            ResourceConceptEvidence(
                                resource_id=resource_id,
                                concept_id=concept,
                                chunk_id=chunk.id,
                                role="exemplifies",
                                weight=0.7,
                                quality_score=quality,
                                position_index=i,
                            )
                        )

            # Concepts mentioned -> "mentions" role
            for concept in enrichment.get("concepts_mentioned", []):
                if concept in admitted:
                    evidence_rows.append(
                        ResourceConceptEvidence(
                            resource_id=resource_id,
                            concept_id=concept,
                            chunk_id=chunk.id,
                            role="mentions",
                            weight=0.3,
                            quality_score=quality,
                            position_index=i,
                        )
                    )

        # Bulk insert
        self.db.add_all(evidence_rows)
        await self.db.flush()

        return len(evidence_rows)

    async def _build_concept_stats(
        self,
        resource_id: uuid.UUID,
        chunks: list[Chunk],
        enrichments: list[dict],
        admitted: set[str],
        concept_metadata: Optional[dict[str, dict]] = None,
    ) -> None:
        """Build resource_concept_stats table with ontological metadata."""
        concept_metadata = concept_metadata or {}

        # Aggregate stats per concept
        stats: dict[str, dict] = defaultdict(
            lambda: {
                "teach_count": 0,
                "mention_count": 0,
                "chunks": set(),
                "quality_scores": [],
                "positions": [],
                "source_types": set(),
                "concept_types": [],
                "bloom_levels": [],
                "difficulties": [],
                "pedagogy_roles": [],
            }
        )

        # Build a lookup from concept_id to per-chunk metadata
        concept_meta_lookup: dict[str, list[dict]] = defaultdict(list)
        for enrichment in enrichments:
            for meta in enrichment.get("concept_metadata", []):
                if isinstance(meta, dict) and meta.get("concept_id"):
                    concept_meta_lookup[meta["concept_id"]].append(meta)

        for i, (chunk, enrichment) in enumerate(zip(chunks, enrichments)):
            quality = enrichment.get("quality_score", 0.5)
            pedagogy_role = enrichment.get("pedagogy_role", "explanation")
            difficulty = enrichment.get("difficulty", "intermediate")

            for concept in enrichment.get("concepts_taught", []):
                if concept in admitted:
                    stats[concept]["teach_count"] += 1
                    stats[concept]["chunks"].add(i)
                    stats[concept]["quality_scores"].append(quality)
                    stats[concept]["positions"].append(i)
                    stats[concept]["source_types"].add(pedagogy_role)
                    stats[concept]["pedagogy_roles"].append(pedagogy_role)
                    stats[concept]["difficulties"].append(difficulty)

            for concept in enrichment.get("concepts_mentioned", []):
                if concept in admitted:
                    stats[concept]["mention_count"] += 1
                    stats[concept]["chunks"].add(i)
                    stats[concept]["positions"].append(i)

        # Populate concept_types and bloom_levels from metadata lookup
        for concept in stats:
            for meta in concept_meta_lookup.get(concept, []):
                if meta.get("concept_type"):
                    stats[concept]["concept_types"].append(meta["concept_type"])
                if meta.get("bloom_level"):
                    stats[concept]["bloom_levels"].append(meta["bloom_level"])

        # Create stats rows with ontological metadata
        stats_rows = []
        for concept, data in stats.items():
            positions = data["positions"]
            pos_mean = statistics.mean(positions) if positions else None
            pos_std = statistics.stdev(positions) if len(positions) > 1 else 0.0
            avg_quality = (
                statistics.mean(data["quality_scores"])
                if data["quality_scores"]
                else None
            )

            # Get ontological metadata for this concept
            meta = concept_metadata.get(concept, {})

            # Compute proportional distributions
            type_dist = self._compute_distribution(data["concept_types"])
            bloom_dist = self._compute_distribution(data["bloom_levels"])
            diff_dist = self._compute_distribution(data["difficulties"])
            ped_dist = self._compute_distribution(data["pedagogy_roles"])

            # Primary values = argmax of distributions (backward compat)
            primary_type = meta.get("concept_type") or (
                max(type_dist, key=type_dist.get) if type_dist else None
            )
            primary_bloom = meta.get("bloom_level") or (
                max(bloom_dist, key=bloom_dist.get) if bloom_dist else None
            )

            stats_rows.append(
                ResourceConceptStats(
                    resource_id=resource_id,
                    concept_id=concept,
                    teach_count=data["teach_count"],
                    mention_count=data["mention_count"],
                    chunk_count=len(data["chunks"]),
                    avg_quality=avg_quality,
                    position_mean=float(pos_mean) if pos_mean is not None else None,
                    position_std=float(pos_std) if pos_std is not None else None,
                    source_types=list(data["source_types"]),
                    # Ontological metadata (primary = argmax for backward compat)
                    concept_type=primary_type,
                    bloom_level=primary_bloom,
                    importance_score=meta.get("importance_score"),
                    # Proportional distributions
                    type_distribution=type_dist or None,
                    bloom_distribution=bloom_dist or None,
                    difficulty_distribution=diff_dist or None,
                    pedagogy_distribution=ped_dist or None,
                )
            )

        self.db.add_all(stats_rows)
        await self.db.flush()

    async def _build_prereq_hints(
        self,
        resource_id: uuid.UUID,
        enrichments: list[dict],
        admitted: set[str],
        ontology_relations: Optional[list[dict]] = None,
    ) -> int:
        """Build prereq hints from enrichment data."""
        # Aggregate prereq hints
        prereq_counts: dict[tuple, dict] = defaultdict(
            lambda: {"count": 0, "sources": []}
        )

        for i, enrichment in enumerate(enrichments):
            for hint in enrichment.get("prereq_hints", []):
                if isinstance(hint, dict):
                    source = hint.get("source_concept")
                    target = hint.get("target_concept")

                    if source and target and source in admitted and target in admitted:
                        key = (source, target)
                        prereq_counts[key]["count"] += 1
                        prereq_counts[key]["sources"].append(
                            {
                                "source": "chunk_enrichment",
                                "chunk_index": i,
                                "relation_type": hint.get("relation_type"),
                                "confidence": hint.get("confidence"),
                            }
                        )

        prereq_like_relations = {"REQUIRES", "ENABLES", "DERIVES_FROM"}
        for relation in ontology_relations or []:
            relation_type = str(relation.get("relation_type", "")).upper().strip()
            if relation_type not in prereq_like_relations:
                continue

            source = canonicalize_concept_id(relation.get("source_concept", ""))
            target = canonicalize_concept_id(relation.get("target_concept", ""))
            if (
                not source
                or not target
                or source not in admitted
                or target not in admitted
            ):
                continue

            key = (source, target)
            prereq_counts[key]["count"] += 1
            prereq_counts[key]["sources"].append(
                {
                    "source": "ontology_relation",
                    "relation_type": relation_type,
                    "confidence": relation.get("confidence"),
                    "evidence_quote": relation.get("evidence_quote"),
                    "page_range": relation.get("page_range"),
                    "section_heading": relation.get("section_heading"),
                }
            )

        # Create prereq hint rows
        hint_rows = []
        for (source, target), data in prereq_counts.items():
            hint_rows.append(
                ResourcePrereqHint(
                    resource_id=resource_id,
                    source_concept_id=source,
                    target_concept_id=target,
                    support_count=data["count"],
                    sources={"evidence": data["sources"]},
                )
            )

        self.db.add_all(hint_rows)
        await self.db.flush()

        return len(hint_rows)
