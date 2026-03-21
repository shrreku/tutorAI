"""
Retrieval Service - TICKET-020

Concept-aware retrieval for tutoring context.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.models.chunk import Chunk
from app.models.knowledge_base import (
    ResourceBundle,
    ResourceConceptEvidence,
)
from app.services.embedding.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A retrieved chunk with metadata."""

    chunk_id: uuid.UUID
    text: str
    section_heading: Optional[str]
    chunk_index: int
    page_start: Optional[int]
    page_end: Optional[int]
    pedagogy_role: Optional[str]
    difficulty: Optional[str]
    relevance_score: float
    retrieval_reason: str
    concepts: list[str] = field(default_factory=list)
    # Citation fields (populated when sub-chunk search is used)
    resource_id: Optional[uuid.UUID] = None
    sub_chunk_id: Optional[uuid.UUID] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    snippet: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "chunk_id": str(self.chunk_id),
            "text": self.text,
            "section_heading": self.section_heading,
            "chunk_index": self.chunk_index,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "pedagogy_role": self.pedagogy_role,
            "difficulty": self.difficulty,
            "relevance_score": self.relevance_score,
            "retrieval_reason": self.retrieval_reason,
            "concepts": self.concepts,
            "resource_id": str(self.resource_id) if self.resource_id else None,
            "sub_chunk_id": str(self.sub_chunk_id) if self.sub_chunk_id else None,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "snippet": self.snippet,
        }


@dataclass
class RetrievalResult:
    """Result of a retrieval query."""

    chunks: list[RetrievedChunk]
    concepts_used: list[str]
    query_embedding_used: bool
    total_candidates: int
    sub_chunk_search_used: bool = False

    def to_dict(self) -> dict:
        return {
            "chunks": [c.to_dict() for c in self.chunks],
            "concepts_used": self.concepts_used,
            "query_embedding_used": self.query_embedding_used,
            "total_candidates": self.total_candidates,
            "sub_chunk_search_used": self.sub_chunk_search_used,
        }


# Minimum cosine similarity to include a result
MIN_SIMILARITY = 0.25
# Score drop ratio: if score drops below this fraction of best score, stop
SCORE_CUTOFF_RATIO = 0.35


class RetrievalService:
    """Concept-aware retrieval service."""

    def __init__(
        self,
        db_session: AsyncSession,
        embedding_provider: BaseEmbeddingProvider,
    ):
        self.db = db_session
        self.embedding = embedding_provider

    async def retrieve(
        self,
        resource_id: uuid.UUID,
        resource_ids: Optional[list[uuid.UUID | str]] = None,
        query: Optional[str] = None,
        target_concepts: Optional[list[str]] = None,
        pedagogy_roles: Optional[list[str]] = None,
        exclude_chunk_ids: Optional[list[str]] = None,
        top_k: int = 5,
        include_neighbors: bool = True,
    ) -> RetrievalResult:
        """
        Retrieve relevant chunks for a tutoring context.

        Strategy:
        1. If target_concepts provided, use bundle-based retrieval
        2. If query provided, use vector similarity search
        3. Combine and re-rank results
        4. Optionally expand with neighboring chunks

        Args:
            resource_id: UUID of the resource
            resource_ids: Optional list of resource IDs for scoped retrieval
            query: Optional text query for semantic search
            target_concepts: Optional list of target concept IDs
            pedagogy_roles: Optional filter for pedagogy roles
            top_k: Maximum number of chunks to return
            include_neighbors: Whether to include neighboring chunks

        Returns:
            RetrievalResult with ranked chunks
        """
        candidates: dict[uuid.UUID, RetrievedChunk] = {}
        concepts_used = []
        query_embedding_used = False
        scoped_resource_ids = [resource_id]
        if resource_ids:
            scoped_resource_ids = []
            seen_resource_ids: set[uuid.UUID] = set()
            for value in resource_ids:
                try:
                    normalized_value = (
                        value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
                    )
                except (TypeError, ValueError):
                    continue
                if normalized_value in seen_resource_ids:
                    continue
                seen_resource_ids.add(normalized_value)
                scoped_resource_ids.append(normalized_value)
            if not scoped_resource_ids:
                scoped_resource_ids = [resource_id]

        # Strategy 1: Bundle-based retrieval for target concepts
        if target_concepts:
            concepts_used = target_concepts.copy()
            for scoped_resource_id in scoped_resource_ids:
                bundle_chunks = await self._retrieve_by_concepts(
                    scoped_resource_id, target_concepts, top_k * 2
                )
                for chunk in bundle_chunks:
                    if chunk.chunk_id not in candidates:
                        candidates[chunk.chunk_id] = chunk

        # Strategy 2: Vector similarity search (prefer sub-chunk index)
        sub_chunk_used = False
        if query:
            query_embedding_used = True
            for scoped_resource_id in scoped_resource_ids:
                vector_chunks, used_sub = await self._retrieve_by_vector(
                    scoped_resource_id, query, top_k * 2
                )
                sub_chunk_used = sub_chunk_used or used_sub
                for chunk in vector_chunks:
                    if chunk.chunk_id in candidates:
                        # Boost score if found by both methods
                        candidates[chunk.chunk_id].relevance_score = min(
                            1.0,
                            candidates[chunk.chunk_id].relevance_score
                            + chunk.relevance_score * 0.5,
                        )
                        candidates[chunk.chunk_id].retrieval_reason += " + vector"
                    else:
                        candidates[chunk.chunk_id] = chunk

        # Apply pedagogy role as soft preference (boost matching, keep all)
        if pedagogy_roles:
            for cid, c in candidates.items():
                if c.pedagogy_role in pedagogy_roles:
                    c.relevance_score = min(1.0, c.relevance_score + 0.15)
                    c.retrieval_reason += " + role_match"

        # Sort by relevance and softly prefer novelty against recently used chunks.
        sorted_candidates = sorted(
            candidates.values(), key=lambda x: -x.relevance_score
        )
        excluded = {str(cid) for cid in (exclude_chunk_ids or []) if cid}
        if excluded:
            novel = [c for c in sorted_candidates if str(c.chunk_id) not in excluded]
            repeated = [c for c in sorted_candidates if str(c.chunk_id) in excluded]
            sorted_chunks = (novel + repeated)[:top_k]
        else:
            sorted_chunks = sorted_candidates[:top_k]

        # Dynamic score cutoff: drop chunks scoring much lower than the best
        if sorted_chunks:
            best_score = sorted_chunks[0].relevance_score
            cutoff = best_score * SCORE_CUTOFF_RATIO
            sorted_chunks = [c for c in sorted_chunks if c.relevance_score >= cutoff]

        # Optionally include neighbors
        if include_neighbors and sorted_chunks:
            sorted_chunks = await self._expand_with_neighbors(
                sorted_chunks,
                max_neighbors=1,
            )

        return RetrievalResult(
            chunks=sorted_chunks,
            concepts_used=concepts_used,
            query_embedding_used=query_embedding_used,
            total_candidates=len(candidates),
            sub_chunk_search_used=sub_chunk_used,
        )

    async def retrieve_for_concept_teaching(
        self,
        resource_id: uuid.UUID,
        concept_id: str,
        include_prereqs: bool = True,
        top_k: int = 5,
    ) -> RetrievalResult:
        """
        Specialized retrieval for teaching a specific concept.

        Prioritizes:
        1. Chunks that "teach" the concept
        2. Example/exercise chunks for the concept
        3. Prereq concept chunks if needed

        Args:
            resource_id: UUID of the resource
            concept_id: Target concept ID
            include_prereqs: Whether to include prereq concept chunks
            top_k: Maximum chunks to return

        Returns:
            RetrievalResult with teaching-focused chunks
        """
        concepts_to_retrieve = [concept_id]

        # Get prereq concepts if requested
        if include_prereqs:
            prereqs = await self._get_prereq_concepts(resource_id, concept_id)
            concepts_to_retrieve.extend(prereqs[:2])  # Limit prereqs

        # Get bundle for primary concept
        bundle = await self._get_bundle(resource_id, concept_id)

        candidates: dict[uuid.UUID, RetrievedChunk] = {}

        if bundle:
            # Get prototype chunks from bundle
            prototypes = bundle.evidence_prototypes or {}
            prototype_scores: dict[uuid.UUID, tuple[float, str]] = {}
            candidate_chunk_ids: list[uuid.UUID] = []

            # Priority 1: Teaching chunks
            teach_ids = prototypes.get("teaches", [])
            for chunk_id_str in teach_ids[:3]:
                try:
                    chunk_id = uuid.UUID(chunk_id_str)
                except (ValueError, TypeError):
                    continue
                candidate_chunk_ids.append(chunk_id)
                prototype_scores[chunk_id] = (1.0, "teaches primary")

            # Priority 2: Example chunks
            example_ids = prototypes.get("exemplifies", [])
            for chunk_id_str in example_ids[:2]:
                try:
                    chunk_id = uuid.UUID(chunk_id_str)
                except (ValueError, TypeError):
                    continue
                if chunk_id not in prototype_scores:
                    candidate_chunk_ids.append(chunk_id)
                    prototype_scores[chunk_id] = (0.8, "exemplifies primary")

            for chunk in await self._get_chunks_by_ids(candidate_chunk_ids):
                score, reason = prototype_scores.get(chunk.chunk_id, (0.0, ""))
                chunk.relevance_score = score
                chunk.retrieval_reason = reason
                candidates[chunk.chunk_id] = chunk

        # Add prereq chunks if needed
        if include_prereqs and len(candidates) < top_k:
            for prereq in concepts_to_retrieve[1:]:
                prereq_chunks = await self._retrieve_by_concepts(
                    resource_id, [prereq], limit=2
                )
                for chunk in prereq_chunks:
                    if chunk.chunk_id not in candidates:
                        chunk.relevance_score *= 0.6
                        chunk.retrieval_reason = f"prereq: {prereq}"
                        candidates[chunk.chunk_id] = chunk

        sorted_chunks = sorted(candidates.values(), key=lambda x: -x.relevance_score)[
            :top_k
        ]

        return RetrievalResult(
            chunks=sorted_chunks,
            concepts_used=concepts_to_retrieve,
            query_embedding_used=False,
            total_candidates=len(candidates),
        )

    async def _retrieve_by_concepts(
        self,
        resource_id: uuid.UUID,
        concept_ids: list[str],
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        """Retrieve chunks by concept IDs using evidence table."""
        result = await self.db.execute(
            select(
                ResourceConceptEvidence.chunk_id,
                ResourceConceptEvidence.concept_id,
                ResourceConceptEvidence.role,
                ResourceConceptEvidence.weight,
                ResourceConceptEvidence.quality_score,
            )
            .where(ResourceConceptEvidence.resource_id == resource_id)
            .where(ResourceConceptEvidence.concept_id.in_(concept_ids))
            .order_by(ResourceConceptEvidence.weight.desc())
            .limit(limit * 2)
        )

        evidence_rows = result.all()

        # Group by chunk and compute aggregate score
        chunk_scores: dict[uuid.UUID, dict] = {}
        for row in evidence_rows:
            chunk_id = row.chunk_id
            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    "score": 0.0,
                    "concepts": [],
                    "role": row.role,
                }
            chunk_scores[chunk_id]["score"] += row.weight * (row.quality_score or 0.5)
            if row.concept_id not in chunk_scores[chunk_id]["concepts"]:
                chunk_scores[chunk_id]["concepts"].append(row.concept_id)

        ranked_chunk_ids = [
            chunk_id
            for chunk_id, _ in sorted(
                chunk_scores.items(),
                key=lambda x: -x[1]["score"],
            )[:limit]
        ]

        chunks_by_id = {
            chunk.chunk_id: chunk
            for chunk in await self._get_chunks_by_ids(ranked_chunk_ids)
        }

        chunks: list[RetrievedChunk] = []
        for chunk_id in ranked_chunk_ids:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                continue
            data = chunk_scores[chunk_id]
            chunk.relevance_score = min(1.0, data["score"])
            chunk.concepts = data["concepts"]
            chunk.retrieval_reason = f"concept match ({data['role']})"
            chunks.append(chunk)
        return chunks

    async def _retrieve_by_vector(
        self,
        resource_id: uuid.UUID,
        query: str,
        limit: int = 10,
    ) -> tuple[list[RetrievedChunk], bool]:
        """Retrieve chunks by vector similarity.

        Prefers searching sub_chunk embeddings (512 tokens, better for retrieval).
        Falls back to parent chunk embeddings if no sub-chunks exist.
        Returns (chunks, used_sub_chunks).
        """
        embeddings = await self.embedding.embed([query])
        query_embedding = embeddings[0]

        # Try sub-chunk search first
        sub_result = await self.db.execute(
            text("""
                SELECT
                    sc.id AS sub_chunk_id,
                    sc.parent_chunk_id,
                    sc.text AS sub_text,
                    sc.char_start,
                    sc.char_end,
                    sc.page_start AS sub_page_start,
                    sc.page_end AS sub_page_end,
                    c.id AS chunk_id,
                    c.text AS chunk_text,
                    c.section_heading,
                    c.chunk_index,
                    c.page_start,
                    c.page_end,
                    c.pedagogy_role,
                    c.difficulty,
                    1 - (sc.embedding <=> :query_embedding) AS similarity
                FROM sub_chunk sc
                JOIN chunk c ON c.id = sc.parent_chunk_id
                WHERE sc.resource_id = :resource_id
                    AND sc.embedding IS NOT NULL
                ORDER BY sc.embedding <=> :query_embedding
                LIMIT :limit
            """),
            {
                "resource_id": str(resource_id),
                "query_embedding": str(query_embedding),
                "limit": limit,
            },
        )
        sub_rows = sub_result.all()

        if sub_rows:
            # Deduplicate by parent chunk (keep best sub-chunk match per parent)
            seen_parents: dict[uuid.UUID, RetrievedChunk] = {}
            for row in sub_rows:
                sim = float(row.similarity) if row.similarity else 0.0
                if sim < MIN_SIMILARITY:
                    continue
                parent_id = row.chunk_id
                if parent_id in seen_parents:
                    # Keep better score, but update citation if this sub is better
                    if sim > seen_parents[parent_id].relevance_score:
                        seen_parents[parent_id].relevance_score = sim
                        seen_parents[parent_id].sub_chunk_id = row.sub_chunk_id
                        seen_parents[parent_id].char_start = row.char_start
                        seen_parents[parent_id].char_end = row.char_end
                        seen_parents[parent_id].snippet = row.sub_text[:200]
                    continue

                seen_parents[parent_id] = RetrievedChunk(
                    chunk_id=parent_id,
                    text=row.chunk_text,
                    section_heading=row.section_heading,
                    chunk_index=row.chunk_index,
                    page_start=row.page_start,
                    page_end=row.page_end,
                    pedagogy_role=row.pedagogy_role,
                    difficulty=row.difficulty,
                    relevance_score=sim,
                    retrieval_reason="sub_chunk vector",
                    resource_id=resource_id,
                    sub_chunk_id=row.sub_chunk_id,
                    char_start=row.char_start,
                    char_end=row.char_end,
                    snippet=row.sub_text[:200],
                )

            if seen_parents:
                return list(seen_parents.values()), True

        # Fallback: search parent chunk embeddings
        result = await self.db.execute(
            text("""
                SELECT
                    id,
                    text,
                    section_heading,
                    chunk_index,
                    page_start,
                    page_end,
                    pedagogy_role,
                    difficulty,
                    1 - (embedding <=> :query_embedding) as similarity
                FROM chunk
                WHERE resource_id = :resource_id
                    AND embedding IS NOT NULL
                ORDER BY embedding <=> :query_embedding
                LIMIT :limit
            """),
            {
                "resource_id": str(resource_id),
                "query_embedding": str(query_embedding),
                "limit": limit,
            },
        )

        chunks = []
        for row in result.all():
            sim = float(row.similarity) if row.similarity else 0.0
            if sim < MIN_SIMILARITY:
                continue
            chunks.append(
                RetrievedChunk(
                    chunk_id=row.id,
                    text=row.text,
                    section_heading=row.section_heading,
                    chunk_index=row.chunk_index,
                    page_start=row.page_start,
                    page_end=row.page_end,
                    pedagogy_role=row.pedagogy_role,
                    difficulty=row.difficulty,
                    relevance_score=sim,
                    retrieval_reason="vector similarity",
                    resource_id=resource_id,
                    snippet=row.text[:200],
                )
            )

        return chunks, False

    async def _get_chunk_by_id(self, chunk_id: uuid.UUID) -> Optional[RetrievedChunk]:
        """Get a chunk by ID."""
        result = await self.db.execute(select(Chunk).where(Chunk.id == chunk_id))
        chunk = result.scalar_one_or_none()
        if not chunk:
            return None
        return self._chunk_to_retrieved_chunk(chunk)

    async def _get_chunks_by_ids(
        self, chunk_ids: list[uuid.UUID]
    ) -> list[RetrievedChunk]:
        """Bulk-load chunks by IDs preserving caller-provided order."""
        if not chunk_ids:
            return []

        unique_chunk_ids = list(dict.fromkeys(chunk_ids))
        result = await self.db.execute(
            select(Chunk).where(Chunk.id.in_(unique_chunk_ids))
        )
        chunks_by_id = {chunk.id: chunk for chunk in result.scalars().all()}

        ordered: list[RetrievedChunk] = []
        for chunk_id in unique_chunk_ids:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                continue
            ordered.append(self._chunk_to_retrieved_chunk(chunk))

        return ordered

    def _chunk_to_retrieved_chunk(self, chunk: Chunk) -> RetrievedChunk:
        """Convert DB chunk model into retrieval payload."""
        concepts: list[str] = []
        if chunk.enrichment_metadata:
            concepts.extend(chunk.enrichment_metadata.get("concepts_taught", []))
            concepts.extend(chunk.enrichment_metadata.get("concepts_mentioned", []))

        return RetrievedChunk(
            chunk_id=chunk.id,
            text=chunk.text,
            section_heading=chunk.section_heading,
            chunk_index=chunk.chunk_index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            pedagogy_role=chunk.pedagogy_role,
            difficulty=chunk.difficulty,
            relevance_score=0.0,
            retrieval_reason="",
            concepts=concepts,
            resource_id=chunk.resource_id,
        )

    async def _get_bundle(
        self,
        resource_id: uuid.UUID,
        concept_id: str,
    ) -> Optional[ResourceBundle]:
        """Get bundle for a concept."""
        result = await self.db.execute(
            select(ResourceBundle)
            .where(ResourceBundle.resource_id == resource_id)
            .where(ResourceBundle.primary_concept_id == concept_id)
        )
        return result.scalar_one_or_none()

    async def _get_prereq_concepts(
        self,
        resource_id: uuid.UUID,
        concept_id: str,
    ) -> list[str]:
        """Get prereq concepts for a concept from bundle."""
        bundle = await self._get_bundle(resource_id, concept_id)
        if bundle and bundle.prereq_hints:
            return bundle.prereq_hints
        return []

    async def _expand_with_neighbors(
        self,
        chunks: list[RetrievedChunk],
        max_neighbors: int = 1,
    ) -> list[RetrievedChunk]:
        """Expand retrieved chunks with neighboring chunks."""
        ordered: list[RetrievedChunk] = []
        seen_ids: set[uuid.UUID] = set()
        resource_neighbor_maps: dict[uuid.UUID, dict[int, RetrievedChunk]] = {}
        resource_neighbor_indices: dict[uuid.UUID, set[int]] = {}
        resource_chunk_indices: dict[uuid.UUID, set[int]] = {}

        for chunk in chunks:
            if not chunk.resource_id:
                continue
            resource_neighbor_indices.setdefault(chunk.resource_id, set())
            resource_chunk_indices.setdefault(chunk.resource_id, set()).add(
                chunk.chunk_index
            )
            for offset in range(-max_neighbors, max_neighbors + 1):
                if offset != 0:
                    resource_neighbor_indices[chunk.resource_id].add(
                        chunk.chunk_index + offset
                    )

        for scoped_resource_id, neighbor_indices in resource_neighbor_indices.items():
            neighbor_indices -= resource_chunk_indices.get(scoped_resource_id, set())
            if not neighbor_indices:
                resource_neighbor_maps[scoped_resource_id] = {}
                continue
            result = await self.db.execute(
                select(Chunk)
                .where(Chunk.resource_id == scoped_resource_id)
                .where(Chunk.chunk_index.in_(list(neighbor_indices)))
            )
            resource_neighbor_maps[scoped_resource_id] = {
                chunk.chunk_index: RetrievedChunk(
                    chunk_id=chunk.id,
                    text=chunk.text,
                    section_heading=chunk.section_heading,
                    chunk_index=chunk.chunk_index,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    pedagogy_role=chunk.pedagogy_role,
                    difficulty=chunk.difficulty,
                    relevance_score=0.3,
                    retrieval_reason="neighbor expansion",
                    resource_id=chunk.resource_id,
                )
                for chunk in result.scalars().all()
            }

        for anchor in chunks:
            neighbor_by_index = (
                resource_neighbor_maps.get(anchor.resource_id, {})
                if anchor.resource_id is not None
                else {}
            )
            for offset in range(-max_neighbors, max_neighbors + 1):
                neighbor_index = anchor.chunk_index + offset
                if offset != 0 and neighbor_index in neighbor_by_index:
                    neighbor = neighbor_by_index[neighbor_index]
                    if neighbor.chunk_id not in seen_ids:
                        ordered.append(neighbor)
                        seen_ids.add(neighbor.chunk_id)

            if anchor.chunk_id not in seen_ids:
                ordered.append(anchor)
                seen_ids.add(anchor.chunk_id)

        return ordered
