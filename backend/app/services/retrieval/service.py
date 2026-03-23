"""
Retrieval Service - TICKET-020

Concept-aware retrieval for tutoring context.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.models.chunk import Chunk
from app.models.knowledge_base import (
    ResourceBundle,
    ResourceConceptEvidence,
    ResourceConceptStats,
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
    enrichment_metadata: Optional[dict] = None

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
NEIGHBOR_MIN_SCORE = 0.58
NEIGHBOR_SCORE_RATIO = 0.72
MAX_NEIGHBOR_ANCHORS = 2
_WORD_RE = re.compile(r"[a-z0-9]+")
_ARTIFACT_PATTERNS = (
    re.compile(r"\bfull[- ]page screenshot\b", re.IGNORECASE),
    re.compile(r"\bnavigation symbols?\b", re.IGNORECASE),
    re.compile(r"\bbeamer\b", re.IGNORECASE),
    re.compile(r"\bswitching between slides\b", re.IGNORECASE),
    re.compile(r"\bimage contains no data to transcribe\b", re.IGNORECASE),
    re.compile(r"\bno data to transcribe into a table\b", re.IGNORECASE),
    re.compile(r"\bscreenshot confirms\b", re.IGNORECASE),
)


class RetrievalService:
    """Concept-aware retrieval service."""

    def __init__(
        self,
        db_session: AsyncSession,
        embedding_provider: BaseEmbeddingProvider,
    ):
        self.db = db_session
        self.embedding = embedding_provider

    @staticmethod
    def _normalize_match_text(value: str) -> str:
        return " ".join(_WORD_RE.findall((value or "").lower()))

    def _score_explicit_concept_match(
        self,
        concept_id: str,
        normalized_message: str,
        message_tokens: set[str],
    ) -> float:
        tokens = [token for token in concept_id.lower().split("_") if token]
        if not tokens:
            return 0.0

        phrase = " ".join(tokens)
        score = 0.0
        if phrase and re.search(rf"\b{re.escape(phrase)}\b", normalized_message):
            score = max(score, 100.0 + len(tokens) * 5)

        acronym = "".join(token[0] for token in tokens if token)
        if len(acronym) >= 2 and acronym in message_tokens:
            score = max(score, 70.0 + len(tokens) * 3)

        overlap = sum(
            1 for token in tokens if len(token) >= 4 and token in message_tokens
        )
        if overlap >= 2:
            score = max(score, 40.0 + overlap * 8)
        elif len(tokens) == 1 and len(tokens[0]) >= 6 and tokens[0] in message_tokens:
            score = max(score, 25.0 + len(tokens[0]))
        return score

    def _looks_like_artifact(self, text: str, section_heading: Optional[str]) -> bool:
        combined = "\n".join(
            part for part in [section_heading or "", text or ""] if part
        )
        if not combined.strip():
            return True
        pattern_hits = sum(
            1 for pattern in _ARTIFACT_PATTERNS if pattern.search(combined)
        )
        if pattern_hits >= 1:
            return True
        alpha_chars = sum(1 for char in combined if char.isalpha())
        if len(combined) >= 120 and alpha_chars <= 20:
            return True
        return False

    def _is_retrieval_eligible(
        self,
        text: str,
        section_heading: Optional[str],
        enrichment_metadata: Optional[dict],
    ) -> bool:
        metadata = enrichment_metadata if isinstance(enrichment_metadata, dict) else {}
        retrieval_meta = metadata.get("retrieval") or {}
        if isinstance(retrieval_meta, dict):
            if retrieval_meta.get("eligible") is False:
                return False
            if retrieval_meta.get("artifact_noise"):
                return False
        return not self._looks_like_artifact(text or "", section_heading)

    def _is_neighbor_compatible(
        self,
        anchor: RetrievedChunk,
        neighbor: RetrievedChunk,
    ) -> bool:
        if not self._is_retrieval_eligible(
            neighbor.text,
            neighbor.section_heading,
            neighbor.enrichment_metadata,
        ):
            return False
        anchor_heading = (anchor.section_heading or "").strip().lower()
        neighbor_heading = (neighbor.section_heading or "").strip().lower()
        if anchor_heading and neighbor_heading:
            return anchor_heading == neighbor_heading
        if anchor.page_end is not None and neighbor.page_start is not None:
            return abs(anchor.page_end - neighbor.page_start) <= 1
        if anchor.page_start is not None and neighbor.page_end is not None:
            return abs(anchor.page_start - neighbor.page_end) <= 1
        return False

    async def resolve_explicit_concepts(
        self,
        resource_ids: list[uuid.UUID | str],
        student_message: str,
        limit: int = 3,
    ) -> list[str]:
        normalized_message = self._normalize_match_text(student_message)
        if not normalized_message:
            return []

        scoped_resource_ids: list[uuid.UUID] = []
        for value in resource_ids:
            try:
                scoped_resource_ids.append(
                    value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
                )
            except (TypeError, ValueError):
                continue
        if not scoped_resource_ids:
            return []

        result = await self.db.execute(
            select(ResourceConceptStats.concept_id).where(
                ResourceConceptStats.resource_id.in_(
                    list(dict.fromkeys(scoped_resource_ids))
                )
            )
        )
        concept_ids = [
            concept_id
            for concept_id in dict.fromkeys(result.scalars().all())
            if isinstance(concept_id, str) and concept_id.strip()
        ]
        if not concept_ids:
            return []

        message_tokens = set(normalized_message.split())
        ranked = [
            (
                self._score_explicit_concept_match(
                    concept_id,
                    normalized_message,
                    message_tokens,
                ),
                concept_id,
            )
            for concept_id in concept_ids
        ]
        ranked = [item for item in ranked if item[0] > 0]
        ranked.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
        return [concept_id for _, concept_id in ranked[:limit]]

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

        filtered_candidates = [
            candidate
            for candidate in candidates.values()
            if self._is_retrieval_eligible(
                candidate.text,
                candidate.section_heading,
                candidate.enrichment_metadata,
            )
        ]

        # Sort by relevance and softly prefer novelty against recently used chunks.
        sorted_candidates = sorted(
            filtered_candidates, key=lambda x: -x.relevance_score
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
        search_limit = max(limit * 4, limit)
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
                    sc.enrichment_metadata AS sub_metadata,
                    c.id AS chunk_id,
                    c.text AS chunk_text,
                    c.section_heading,
                    c.chunk_index,
                    c.page_start,
                    c.page_end,
                    c.pedagogy_role,
                    c.difficulty,
                    c.enrichment_metadata AS chunk_metadata,
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
                "limit": search_limit,
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
                enrichment_metadata = row.sub_metadata or row.chunk_metadata
                if not self._is_retrieval_eligible(
                    row.sub_text or row.chunk_text,
                    row.section_heading,
                    enrichment_metadata,
                ):
                    continue
                parent_id = row.chunk_id
                if parent_id in seen_parents:
                    # Keep better score, but update citation if this sub is better
                    if sim > seen_parents[parent_id].relevance_score:
                        seen_parents[parent_id].relevance_score = sim
                        seen_parents[parent_id].sub_chunk_id = row.sub_chunk_id
                        seen_parents[parent_id].char_start = row.char_start
                        seen_parents[parent_id].char_end = row.char_end
                        seen_parents[parent_id].page_start = (
                            row.sub_page_start
                            if row.sub_page_start is not None
                            else row.page_start
                        )
                        seen_parents[parent_id].page_end = (
                            row.sub_page_end
                            if row.sub_page_end is not None
                            else row.page_end
                        )
                        seen_parents[parent_id].snippet = row.sub_text[:200]
                        seen_parents[
                            parent_id
                        ].enrichment_metadata = enrichment_metadata
                    continue

                seen_parents[parent_id] = RetrievedChunk(
                    chunk_id=parent_id,
                    text=row.chunk_text,
                    section_heading=row.section_heading,
                    chunk_index=row.chunk_index,
                    page_start=(
                        row.sub_page_start
                        if row.sub_page_start is not None
                        else row.page_start
                    ),
                    page_end=(
                        row.sub_page_end
                        if row.sub_page_end is not None
                        else row.page_end
                    ),
                    pedagogy_role=row.pedagogy_role,
                    difficulty=row.difficulty,
                    relevance_score=sim,
                    retrieval_reason="sub_chunk vector",
                    resource_id=resource_id,
                    sub_chunk_id=row.sub_chunk_id,
                    char_start=row.char_start,
                    char_end=row.char_end,
                    snippet=row.sub_text[:200],
                    enrichment_metadata=enrichment_metadata,
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
                    enrichment_metadata,
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
                "limit": search_limit,
            },
        )

        chunks = []
        for row in result.all():
            sim = float(row.similarity) if row.similarity else 0.0
            if sim < MIN_SIMILARITY:
                continue
            if not self._is_retrieval_eligible(
                row.text,
                row.section_heading,
                row.enrichment_metadata,
            ):
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
                    enrichment_metadata=row.enrichment_metadata,
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
            snippet=chunk.text[:200],
            enrichment_metadata=chunk.enrichment_metadata,
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
        anchor_chunks = [
            chunk
            for chunk in chunks
            if chunk.resource_id and chunk.relevance_score >= NEIGHBOR_MIN_SCORE
        ][:MAX_NEIGHBOR_ANCHORS]

        for chunk in anchor_chunks:
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
                    relevance_score=0.0,
                    retrieval_reason="neighbor expansion",
                    resource_id=chunk.resource_id,
                    snippet=chunk.text[:200],
                    enrichment_metadata=chunk.enrichment_metadata,
                )
                for chunk in result.scalars().all()
            }

        for anchor in chunks:
            if anchor.chunk_id not in seen_ids:
                ordered.append(anchor)
                seen_ids.add(anchor.chunk_id)

            neighbor_by_index = (
                resource_neighbor_maps.get(anchor.resource_id, {})
                if anchor.resource_id is not None
                else {}
            )
            if anchor not in anchor_chunks:
                continue
            for offset in range(-max_neighbors, max_neighbors + 1):
                neighbor_index = anchor.chunk_index + offset
                if offset != 0 and neighbor_index in neighbor_by_index:
                    neighbor = neighbor_by_index[neighbor_index]
                    if not self._is_neighbor_compatible(anchor, neighbor):
                        continue
                    neighbor.relevance_score = max(
                        MIN_SIMILARITY,
                        min(
                            anchor.relevance_score * NEIGHBOR_SCORE_RATIO,
                            anchor.relevance_score - 0.08,
                        ),
                    )
                    if neighbor.chunk_id not in seen_ids:
                        ordered.append(neighbor)
                        seen_ids.add(neighbor.chunk_id)

        return ordered
