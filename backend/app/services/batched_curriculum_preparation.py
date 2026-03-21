"""Batched Curriculum Preparation — progressive phased ingestion pipeline.

Replaces the monolithic CurriculumPreparationService with a batch-aware
pipeline that:
  1. Splits resource chunks into section-aligned batches.
  2. Processes each batch independently (ontology → enrichment → KB merge).
  3. Marks each batch as study-ready once its processing completes.
  4. Updates resource-level capabilities progressively.
  5. After all batches complete, runs a final cross-batch merge for
     graph coherence and full curriculum artifacts.

This allows sessions/notebooks to start with partial context and update
as more batches complete.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk, ChunkConcept
from app.models.sub_chunk import SubChunk
from app.models.knowledge_base import (
    ResourceBundle,
    ResourceConceptEvidence,
    ResourceConceptGraph,
    ResourceConceptStats,
    ResourcePrereqHint,
    ResourceTopicBundle,
)
from app.models.processing_batch import ProcessingBatch
from app.models.knowledge_base import ResourceLearningObjective, ResourceTopic
from app.models.resource import Resource, progressive_ready_capabilities
from app.models.resource_artifact import ResourceArtifactState
from app.services.ingestion.bundle_builder import BundleBuilder
from app.services.ingestion.enricher import ChunkEnricher
from app.services.ingestion.graph_builder import ConceptGraphBuilder
from app.services.ingestion.ingestion_types import ChunkData, SectionData
from app.services.ingestion.kb_builder import ResourceKBBuilder
from app.services.ingestion.ontology_extractor import OntologyExtractor
from app.services.ingestion.pipeline_support import save_ontology_data
from app.utils.canonicalization import canonicalize_concept_id

logger = logging.getLogger(__name__)

# Target tokens per batch — chapter-scale context for better ontology quality.
DEFAULT_BATCH_TOKEN_TARGET = 8000
# Minimum chunks per batch to avoid degenerate single-chunk batches.
MIN_CHUNKS_PER_BATCH = 3


class BatchedCurriculumPreparationService:
    """Progressive batch-aware curriculum preparation pipeline."""

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        ontology_extractor: OntologyExtractor,
        enricher: ChunkEnricher,
        kb_builder: Optional[ResourceKBBuilder] = None,
        graph_builder: Optional[ConceptGraphBuilder] = None,
        bundle_builder: Optional[BundleBuilder] = None,
        batch_token_target: int = DEFAULT_BATCH_TOKEN_TARGET,
    ):
        self.db = db_session
        self.ontology_extractor = ontology_extractor
        self.enricher = enricher
        self.kb_builder = kb_builder or ResourceKBBuilder(db_session)
        self.graph_builder = graph_builder or ConceptGraphBuilder(db_session)
        self.bundle_builder = bundle_builder or BundleBuilder(db_session)
        self.batch_token_target = batch_token_target

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def ensure_curriculum_ready(
        self,
        resource_id: uuid.UUID,
        progress_callback: Optional[Callable[[str, int], Awaitable[None]]] = None,
    ) -> dict:
        """Run the full batched curriculum pipeline for a resource.

        Returns a summary dict compatible with the old monolithic service.
        """
        resource = await self.db.get(Resource, resource_id)
        if not resource:
            raise ValueError(f"Resource {resource_id} not found")

        capabilities = dict(resource.capabilities_json or {})
        if capabilities.get("curriculum_ready") and capabilities.get(
            "has_topic_bundles"
        ):
            return {"prepared": False, "reason": "already_ready"}

        chunks = await self._get_chunks(resource_id)
        if not chunks:
            raise ValueError(
                f"Resource {resource_id} has no chunks for curriculum preparation"
            )

        await self._reset_curriculum_state(resource_id)

        # ── Phase 1: create processing batches ──────────────────────
        if progress_callback is not None:
            await progress_callback("batch_planning", 5)

        batches = await self._plan_batches(resource_id, chunks)
        total_batches = len(batches)
        logger.info(
            "Planned %d processing batches for resource %s", total_batches, resource_id
        )

        # Update resource with total batch count
        await self._update_resource_batch_counts(resource, 0, total_batches)

        # ── Phase 2: process each batch ─────────────────────────────
        all_ontology_relations = []
        total_concepts_admitted = 0
        total_graph_edges = 0

        for i, batch in enumerate(batches):
            batch_progress_base = 10 + int(80 * (i / max(total_batches, 1)))
            batch_progress_end = 10 + int(80 * ((i + 1) / max(total_batches, 1)))

            if progress_callback is not None:
                await progress_callback(f"batch_{i}_ontology", batch_progress_base)

            try:
                batch_result = await self._process_single_batch(
                    resource=resource,
                    batch=batch,
                    chunks=chunks,
                    progress_callback=progress_callback,
                    progress_base=batch_progress_base,
                    progress_end=batch_progress_end,
                )

                if batch_result.get("ontology_relations"):
                    all_ontology_relations.extend(batch_result["ontology_relations"])
                total_concepts_admitted += batch_result.get("concepts_admitted", 0)
                total_graph_edges += batch_result.get("graph_edges", 0)

                # Mark batch study-ready
                batch.status = "completed"
                batch.is_study_ready = True
                batch.is_retrieval_ready = True
                batch.completed_at = datetime.now(timezone.utc)
                batch.concepts_admitted = batch_result.get("concepts_admitted", 0)
                batch.graph_edges_created = batch_result.get("graph_edges", 0)
                batch.result_json = batch_result

                # Update resource progressive readiness
                ready_count = i + 1
                await self._update_resource_batch_counts(
                    resource, ready_count, total_batches
                )

                await self.db.flush()
                logger.info(
                    "Batch %d/%d completed for resource %s (%d concepts, %d edges)",
                    i + 1,
                    total_batches,
                    resource_id,
                    batch_result.get("concepts_admitted", 0),
                    batch_result.get("graph_edges", 0),
                )

            except Exception as exc:
                logger.error("Batch %d failed for resource %s: %s", i, resource_id, exc)
                batch.status = "failed"
                batch.error_message = str(exc)[:2000]
                await self.db.flush()
                # Continue with remaining batches

        # ── Phase 3: final cross-batch merge ────────────────────────
        if progress_callback is not None:
            await progress_callback("final_merge_bundles", 92)

        bundle_result = await self._build_bundles(resource_id)

        if progress_callback is not None:
            await progress_callback("final_merge_artifacts", 96)

        await self._mark_resource_fully_ready(
            resource,
            total_concepts_admitted,
            total_graph_edges,
            bundle_result,
        )

        # Persist artifacts (reuse existing artifact helpers)
        ontology_artifact = await self._upsert_processing_manifest_artifact(
            resource=resource,
            batches=batches,
            source_chunk_ids=[c.id for c in chunks],
        )
        artifact = await self._upsert_curriculum_artifact(
            resource,
            {
                "concepts_admitted": total_concepts_admitted,
                "graph_edges": total_graph_edges,
            },
            bundle_result,
            source_chunk_ids=[c.id for c in chunks],
            related_artifact_ids={
                "processing_manifest": str(ontology_artifact.id),
            },
        )

        if progress_callback is not None:
            await progress_callback("curriculum_finalize", 99)

        await self.db.commit()
        return {
            "prepared": True,
            "artifact_id": str(artifact.id),
            "concepts_admitted": total_concepts_admitted,
            "graph_edges": total_graph_edges,
            "topic_bundles": bundle_result.get("topic_bundles_created", 0),
            "total_batches": total_batches,
            "batches_completed": sum(1 for b in batches if b.status == "completed"),
            "batches_failed": sum(1 for b in batches if b.status == "failed"),
        }

    async def _reset_curriculum_state(self, resource_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(ResourceBundle).where(ResourceBundle.resource_id == resource_id)
        )
        await self.db.execute(
            delete(ResourceTopicBundle).where(
                ResourceTopicBundle.resource_id == resource_id
            )
        )
        await self.db.execute(
            delete(ResourceConceptGraph).where(
                ResourceConceptGraph.resource_id == resource_id
            )
        )
        await self.db.execute(
            delete(ResourceConceptEvidence).where(
                ResourceConceptEvidence.resource_id == resource_id
            )
        )
        await self.db.execute(
            delete(ResourceConceptStats).where(
                ResourceConceptStats.resource_id == resource_id
            )
        )
        await self.db.execute(
            delete(ResourcePrereqHint).where(
                ResourcePrereqHint.resource_id == resource_id
            )
        )
        await self.db.execute(
            delete(ResourceTopic).where(ResourceTopic.resource_id == resource_id)
        )
        await self.db.execute(
            delete(ResourceLearningObjective).where(
                ResourceLearningObjective.resource_id == resource_id
            )
        )
        await self.db.flush()

    # ------------------------------------------------------------------
    # Batch planning
    # ------------------------------------------------------------------

    async def _plan_batches(
        self, resource_id: uuid.UUID, chunks: list[Chunk]
    ) -> list[ProcessingBatch]:
        """Split chunks into section-aligned batches.

        Strategy: group by section_heading, then merge small sections into
        a single batch until the token target is reached.
        """
        # Clear any existing batches for this resource
        await self.db.execute(
            delete(ProcessingBatch).where(ProcessingBatch.resource_id == resource_id)
        )
        await self.db.flush()

        # Group chunks by section heading
        section_groups: list[list[Chunk]] = []
        current_group: list[Chunk] = []
        current_heading: Optional[str] = None

        for chunk in chunks:
            heading = chunk.section_heading or current_heading
            if (
                heading != current_heading
                and current_group
                and len(current_group) >= MIN_CHUNKS_PER_BATCH
            ):
                section_groups.append(current_group)
                current_group = []
            current_heading = heading
            current_group.append(chunk)

        if current_group:
            section_groups.append(current_group)

        # Merge small sections into batches up to token target
        batches_planned: list[list[Chunk]] = []
        accumulator: list[Chunk] = []
        accum_tokens = 0

        for group in section_groups:
            group_tokens = sum(self._estimate_tokens(c.text) for c in group)
            if (
                accumulator
                and accum_tokens + group_tokens > self.batch_token_target
                and len(accumulator) >= MIN_CHUNKS_PER_BATCH
            ):
                batches_planned.append(accumulator)
                accumulator = []
                accum_tokens = 0
            accumulator.extend(group)
            accum_tokens += group_tokens

        if accumulator:
            batches_planned.append(accumulator)

        # If everything fits in one batch, just use one
        if not batches_planned:
            batches_planned = [chunks]

        # Persist batch records
        db_batches: list[ProcessingBatch] = []
        for idx, batch_chunks in enumerate(batches_planned):
            headings = sorted(
                {c.section_heading for c in batch_chunks if c.section_heading}
            )
            batch = ProcessingBatch(
                resource_id=resource_id,
                batch_index=idx,
                status="pending",
                chunk_index_start=batch_chunks[0].chunk_index,
                chunk_index_end=batch_chunks[-1].chunk_index,
                section_headings=headings,
                chunk_ids=[str(c.id) for c in batch_chunks],
                token_estimate=sum(self._estimate_tokens(c.text) for c in batch_chunks),
            )
            self.db.add(batch)
            db_batches.append(batch)

        await self.db.flush()
        return db_batches

    # ------------------------------------------------------------------
    # Single batch processing
    # ------------------------------------------------------------------

    async def _process_single_batch(
        self,
        *,
        resource: Resource,
        batch: ProcessingBatch,
        chunks: list[Chunk],
        progress_callback: Optional[Callable] = None,
        progress_base: int = 0,
        progress_end: int = 100,
    ) -> dict:
        """Process one batch: ontology → enrichment → KB merge → graph merge."""
        resource_id = resource.id
        batch_chunk_ids = set(batch.chunk_ids or [])
        batch_chunks = [c for c in chunks if str(c.id) in batch_chunk_ids]

        if not batch_chunks:
            return {"concepts_admitted": 0, "graph_edges": 0}

        # ── Ontology extraction for this batch ──────────────────────
        batch.ontology_status = "running"
        await self.db.flush()

        sections = self._build_sections(batch_chunks)
        ontology = await self.ontology_extractor.extract(
            sections=sections, resource_title=resource.filename
        )
        ontology_context = (
            ontology.get_enrichment_context(max_tokens=800) if ontology else None
        )

        batch.ontology_status = "completed"
        batch.ontology_completed_at = datetime.now(timezone.utc)
        batch.ontology_context = ontology_context
        await self.db.flush()

        # ── Chunk enrichment with ontology context ──────────────────
        mid_progress = progress_base + (progress_end - progress_base) // 2
        if progress_callback is not None:
            await progress_callback(
                f"batch_{batch.batch_index}_enrichment", mid_progress
            )

        batch.enrichment_status = "running"
        await self.db.flush()

        chunk_data = self._build_chunk_data(batch_chunks)
        enrichments = await self.enricher.enrich_batch(
            chunk_data, ontology_context=ontology_context
        )
        enrichments_dict = [item.to_dict() for item in enrichments]
        await self._persist_enrichments(batch_chunks, enrichments_dict)

        batch.enrichment_status = "completed"
        batch.enrichment_completed_at = datetime.now(timezone.utc)
        batch.is_retrieval_ready = True
        await self.db.flush()

        # ── Incremental KB merge ────────────────────────────────────
        batch.kb_merge_status = "running"
        await self.db.flush()

        kb_result = await self.kb_builder.build(
            resource_id,
            force_rebuild=True,
            ontology_relations=(ontology.semantic_relations if ontology else None),
        )
        if ontology:
            await save_ontology_data(self.db, resource_id, ontology)

        batch.kb_merge_status = "completed"
        batch.kb_merge_completed_at = datetime.now(timezone.utc)
        await self.db.flush()

        # ── Incremental graph merge ─────────────────────────────────
        batch.graph_merge_status = "running"
        await self.db.flush()

        graph_result = await self.graph_builder.build(
            resource_id,
            force_rebuild=True,
            ontology_relations=(ontology.semantic_relations if ontology else None),
        )

        batch.graph_merge_status = "completed"
        await self.db.flush()

        return {
            "concepts_admitted": kb_result.get("concepts_admitted", 0),
            "graph_edges": graph_result.get("edges_created", 0),
            "ontology_relations": (ontology.semantic_relations if ontology else []),
            "batch_index": batch.batch_index,
        }

    # ------------------------------------------------------------------
    # Resource capability updates
    # ------------------------------------------------------------------

    async def _update_resource_batch_counts(
        self, resource: Resource, ready_count: int, total_count: int
    ) -> None:
        """Update resource capabilities with progressive batch readiness."""
        has_concepts = ready_count > 0
        capabilities = progressive_ready_capabilities(
            dict(resource.capabilities_json or {}),
            ready_batch_count=ready_count,
            total_batch_count=total_count,
            has_concepts=has_concepts,
        )
        resource.capabilities_json = capabilities
        if has_concepts and resource.tutoring_ready_at is None:
            resource.tutoring_ready_at = datetime.now(timezone.utc)
        self.db.add(resource)
        await self.db.flush()

    async def _mark_resource_fully_ready(
        self,
        resource: Resource,
        total_concepts: int,
        total_edges: int,
        bundle_result: dict,
    ) -> None:
        """Mark resource as fully curriculum-ready after all batches complete."""
        capabilities = dict(resource.capabilities_json or {})
        has_concepts = total_concepts > 0
        has_graph = total_edges > 0
        has_topic_bundles = bundle_result.get("topic_bundles_created", 0) > 0
        now = datetime.now(timezone.utc)
        capabilities.update(
            {
                "concepts_ready": has_concepts,
                "has_concepts": has_concepts,
                "has_prereq_graph": has_graph,
                "graph_ready": has_graph,
                "has_topic_bundles": has_topic_bundles,
                "has_curriculum_artifacts": has_topic_bundles,
                "curriculum_ready": has_topic_bundles,
                "can_start_learn_session": has_topic_bundles or has_concepts,
                "can_start_practice_session": has_topic_bundles or has_concepts,
                "can_start_revision_session": has_topic_bundles or has_concepts,
                "study_ready": has_concepts,
            }
        )
        resource.capabilities_json = capabilities
        resource.curriculum_ready_at = (
            now if has_topic_bundles else resource.curriculum_ready_at
        )
        resource.tutoring_ready_at = now if has_concepts else resource.tutoring_ready_at
        resource.graph_ready_at = now if has_graph else resource.graph_ready_at
        resource.processing_profile = "prepared_for_curriculum"
        self.db.add(resource)
        await self.db.flush()

    # ------------------------------------------------------------------
    # Helpers (reused from CurriculumPreparationService)
    # ------------------------------------------------------------------

    async def _get_chunks(self, resource_id: uuid.UUID) -> list[Chunk]:
        result = await self.db.execute(
            select(Chunk)
            .where(Chunk.resource_id == resource_id)
            .order_by(Chunk.chunk_index)
        )
        return list(result.scalars().all())

    def _build_sections(self, chunks: list[Chunk]) -> list[SectionData]:
        grouped: list[SectionData] = []
        current_heading: Optional[str] = None
        bucket: list[str] = []
        page_start: Optional[int] = None
        page_end: Optional[int] = None

        def flush_bucket():
            nonlocal bucket, current_heading, page_start, page_end
            if not bucket:
                return
            grouped.append(
                SectionData(
                    heading=current_heading,
                    page_start=page_start,
                    page_end=page_end,
                    text="\n\n".join(bucket),
                    metadata={"source": "stored_chunks"},
                )
            )
            bucket = []
            page_start = None
            page_end = None

        for chunk in chunks:
            heading = chunk.section_heading or current_heading
            if current_heading is None:
                current_heading = heading
            elif heading != current_heading and bucket:
                flush_bucket()
                current_heading = heading
            if page_start is None:
                page_start = chunk.page_start
            page_end = chunk.page_end or page_end
            bucket.append(chunk.text)
        flush_bucket()
        return grouped or [
            SectionData(
                heading=None,
                page_start=None,
                page_end=None,
                text="\n\n".join(chunk.text for chunk in chunks),
                metadata={"source": "stored_chunks"},
            )
        ]

    def _build_chunk_data(self, chunks: list[Chunk]) -> list[ChunkData]:
        return [
            ChunkData(
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                section_heading=chunk.section_heading,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                metadata={"source": "stored_chunks"},
            )
            for chunk in chunks
        ]

    async def _persist_enrichments(
        self, chunks: list[Chunk], enrichments: list[dict]
    ) -> None:
        chunk_ids = [chunk.id for chunk in chunks]
        await self.db.execute(
            delete(ChunkConcept).where(ChunkConcept.chunk_id.in_(chunk_ids))
        )
        for chunk, enrichment in zip(chunks, enrichments):
            existing = dict(chunk.enrichment_metadata or {})
            docling_payload = existing.get("docling")
            existing.update(enrichment)
            existing["metadata_level"] = "curriculum_prepare"
            if docling_payload is not None:
                existing["docling"] = docling_payload
            chunk.enrichment_metadata = existing
            chunk.pedagogy_role = enrichment.get("pedagogy_role") or chunk.pedagogy_role
            chunk.difficulty = enrichment.get("difficulty") or chunk.difficulty

            for concept in enrichment.get("concepts_taught", []):
                self.db.add(
                    ChunkConcept(
                        chunk_id=chunk.id,
                        concept_id=canonicalize_concept_id(concept),
                        role="teaches",
                    )
                )
            for concept in enrichment.get("concepts_mentioned", []):
                self.db.add(
                    ChunkConcept(
                        chunk_id=chunk.id,
                        concept_id=canonicalize_concept_id(concept),
                        role="mentions",
                    )
                )

        sub_chunk_result = await self.db.execute(
            select(SubChunk).where(SubChunk.parent_chunk_id.in_(chunk_ids))
        )
        sub_chunks = list(sub_chunk_result.scalars().all())
        enrichments_by_chunk_id = {
            chunk.id: enrichment for chunk, enrichment in zip(chunks, enrichments)
        }
        for sub_chunk in sub_chunks:
            enrichment = enrichments_by_chunk_id.get(sub_chunk.parent_chunk_id)
            if enrichment is None:
                continue
            existing = dict(sub_chunk.enrichment_metadata or {})
            existing.update(enrichment)
            existing["metadata_level"] = "curriculum_prepare"
            sub_chunk.enrichment_metadata = existing
        await self.db.flush()

    async def _build_bundles(self, resource_id: uuid.UUID) -> dict:
        await self.db.execute(
            delete(ResourceBundle).where(ResourceBundle.resource_id == resource_id)
        )
        await self.db.execute(
            delete(ResourceTopicBundle).where(
                ResourceTopicBundle.resource_id == resource_id
            )
        )
        await self.db.flush()
        concept_result = await self.bundle_builder.build_concept_bundles(
            resource_id, force_rebuild=False
        )
        topic_result = await self.bundle_builder.build_topic_bundles(
            resource_id, force_rebuild=False
        )
        return {**concept_result, **topic_result}

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough word-based token estimate."""
        return max(1, len(text.split()) * 4 // 3)

    # ------------------------------------------------------------------
    # Artifact persistence
    # ------------------------------------------------------------------

    async def _upsert_processing_manifest_artifact(
        self,
        *,
        resource: Resource,
        batches: list[ProcessingBatch],
        source_chunk_ids: list[uuid.UUID],
    ) -> ResourceArtifactState:
        payload = {
            "artifact_kind": "processing_manifest",
            "artifact_version": "1.0",
            "resource_id": str(resource.id),
            "total_batches": len(batches),
            "batches_completed": sum(1 for b in batches if b.status == "completed"),
            "batches_failed": sum(1 for b in batches if b.status == "failed"),
            "batches": [
                {
                    "batch_id": str(b.id),
                    "batch_index": b.batch_index,
                    "status": b.status,
                    "chunk_index_start": b.chunk_index_start,
                    "chunk_index_end": b.chunk_index_end,
                    "section_headings": b.section_headings,
                    "token_estimate": b.token_estimate,
                    "is_study_ready": b.is_study_ready,
                    "concepts_admitted": b.concepts_admitted,
                    "graph_edges_created": b.graph_edges_created,
                }
                for b in batches
            ],
        }
        return await self._upsert_resource_artifact(
            resource_id=resource.id,
            artifact_kind="processing_manifest",
            payload=payload,
            source_chunk_ids=source_chunk_ids,
        )

    async def _upsert_curriculum_artifact(
        self,
        resource: Resource,
        kb_summary: dict,
        bundle_result: dict,
        source_chunk_ids: list[uuid.UUID],
        related_artifact_ids: Optional[dict[str, str]] = None,
    ) -> ResourceArtifactState:
        payload = {
            "artifact_kind": "curriculum_prepare",
            "artifact_version": "2.0",
            "pipeline": "batched",
            "concepts_admitted": kb_summary.get("concepts_admitted", 0),
            "graph_edges": kb_summary.get("graph_edges", 0),
            "topic_bundles": bundle_result.get("topic_bundles_created", 0),
            "source_chunk_ids": [str(cid) for cid in source_chunk_ids],
            "related_artifact_ids": related_artifact_ids or {},
        }
        return await self._upsert_resource_artifact(
            resource_id=resource.id,
            artifact_kind="curriculum_prepare",
            payload=payload,
            source_chunk_ids=source_chunk_ids,
        )

    async def _upsert_resource_artifact(
        self,
        *,
        resource_id: uuid.UUID,
        artifact_kind: str,
        payload: dict,
        source_chunk_ids: list[uuid.UUID],
    ) -> ResourceArtifactState:
        result = await self.db.execute(
            select(ResourceArtifactState)
            .where(ResourceArtifactState.resource_id == resource_id)
            .where(ResourceArtifactState.scope_type == "resource")
            .where(ResourceArtifactState.scope_key == str(resource_id))
            .where(ResourceArtifactState.artifact_kind == artifact_kind)
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        normalized_ids = [str(cid) for cid in source_chunk_ids]

        if existing:
            existing.status = "ready"
            existing.version = payload.get("artifact_version", "1.0")
            existing.payload_json = payload
            existing.content_hash = payload_hash
            existing.source_chunk_ids = normalized_ids
            existing.error_message = None
            await self.db.flush()
            return existing

        artifact = ResourceArtifactState(
            resource_id=resource_id,
            scope_type="resource",
            scope_key=str(resource_id),
            artifact_kind=artifact_kind,
            status="ready",
            version=payload.get("artifact_version", "1.0"),
            payload_json=payload,
            source_chunk_ids=normalized_ids,
            content_hash=payload_hash,
        )
        self.db.add(artifact)
        await self.db.flush()
        return artifact
