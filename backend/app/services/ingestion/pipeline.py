"""Core ingestion pipeline.

Upload-time ingestion now stops once a resource is parsed, chunked, embedded,
and persisted for retrieval. Heavier enrichment and knowledge preparation are
deferred to later job families.
"""
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.ingestion import IngestionJob
from app.models.resource import Resource
from app.models.resource_artifact import ResourceArtifactState
from app.models.chunk import Chunk, ChunkConcept
from app.db.repositories.resource_artifact_repo import ResourceArtifactRepository
from app.services.llm.base import BaseLLMProvider
from app.services.embedding.base import BaseEmbeddingProvider
from app.services.storage.base import StorageProvider
from app.services.ingestion.docling_adapter import DoclingAdapter, DoclingConversionResult
from app.services.ingestion.docling_chunker import DoclingChunker, DoclingChunkingResult
from app.services.ingestion.ingestion_types import ChunkData
from app.services.ingestion.resource_profile import build_resource_profile
from app.services.ingestion.pipeline_support import (
    compute_quality_metrics,
    update_job,
    update_resource_status,
)
from app.services.neo4j.client import get_neo4j_client
from langfuse import observe

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "2.0.0"


class IngestionStage(str, Enum):
    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    PERSIST = "persist"
    COMPLETE = "complete"


class IngestionPipeline:
    """Orchestrates the core upload-time ingestion pipeline."""
    
    def __init__(
        self,
        db_session: AsyncSession,
        llm_provider: BaseLLMProvider,
        embedding_provider: BaseEmbeddingProvider,
        storage_provider: StorageProvider,
    ):
        self.db = db_session
        self.llm = llm_provider
        self.embedding = embedding_provider
        self.storage = storage_provider
        
        self.docling_adapter = DoclingAdapter()
        self.docling_chunker = DoclingChunker(
            embedding_model_id=embedding_provider.model_id,
            use_contextualized_text=True,
        )

    async def _update_job_stage(
        self,
        job_id: Optional[uuid.UUID],
        stage: IngestionStage,
        progress: int,
        *,
        status: str = "running",
        metrics: Optional[dict] = None,
    ) -> None:
        """Update job stage/progress if a job id is present."""
        if not job_id:
            return
        await update_job(
            self.db,
            job_id,
            status,
            stage,
            progress,
            metrics=metrics,
        )
        commit = getattr(self.db, "commit", None)
        if callable(commit):
            await commit()

    async def _merge_job_metrics(
        self,
        job_id: Optional[uuid.UUID],
        metrics: Optional[dict],
    ) -> Optional[dict]:
        if not job_id or not isinstance(metrics, dict):
            return metrics

        get_record = getattr(self.db, "get", None)
        if not callable(get_record):
            return metrics

        current_job = await get_record(IngestionJob, job_id)
        current_metrics = getattr(current_job, "metrics", None) if current_job is not None else None
        if not isinstance(current_metrics, dict):
            return metrics

        return {
            **current_metrics,
            **metrics,
        }
    
    @observe(name="ingestion-pipeline", capture_input=False)
    async def run(
        self,
        resource_id: uuid.UUID,
        job_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """
        Run the core upload-time ingestion pipeline for a resource.
        
        Args:
            resource_id: UUID of the resource to ingest
            job_id: Optional job ID for tracking progress
            
        Returns:
            Dict with pipeline results and metrics
        """
        metrics = {
            "resource_id": str(resource_id),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "stages": {},
        }
        
        try:
            # Update job status
            await self._update_job_stage(job_id, IngestionStage.PARSE, 0)
            
            # Get resource
            resource = await self._get_resource(resource_id)
            if not resource:
                raise ValueError(f"Resource {resource_id} not found")
            
            if not resource.file_path_or_uri:
                raise ValueError(f"Resource {resource_id} has no file path")
            
            # Stage 1: Parse PDF
            logger.info(f"Stage 1: Parsing PDF for resource {resource_id}")
            parse_result = await self._run_parse_stage(resource)
            sections = parse_result.sections
            metrics["stages"]["parse"] = {
                "sections": len(sections),
                "status": parse_result.status,
                "warnings": len(parse_result.warnings),
                "errors": len(parse_result.errors),
            }
            if parse_result.warnings:
                logger.warning(
                    "Docling parse warnings for resource %s: %s",
                    resource_id,
                    "; ".join(parse_result.warnings),
                )
            
            await self._update_job_stage(job_id, IngestionStage.CHUNK, 25)
            
            # Stage 2: Chunk text
            logger.info(f"Stage 2: Chunking text for resource {resource_id}")
            chunking_result = await self._run_chunk_stage(parse_result)
            chunks = chunking_result.chunks
            metrics["stages"]["chunk"] = {
                "chunks": len(chunks),
                "strategy": chunking_result.strategy,
                "embedding_strategy": chunking_result.metadata.get("embedding_strategy"),
            }
            
            await self._update_job_stage(job_id, IngestionStage.EMBED, 55)
            
            # Stage 3: Embed chunks
            logger.info(f"Stage 3: Embedding chunks for resource {resource_id}")
            embeddings = await self._run_embed_stage(chunks)
            metrics["stages"]["embed"] = {"embeddings": len(embeddings)}
            
            await self._update_job_stage(job_id, IngestionStage.PERSIST, 80)

            enrichments = self._build_lightweight_enrichments(chunks)
            metrics["stages"]["persist"] = {
                "chunks": len(chunks),
                "light_metadata": len(enrichments),
            }

            # Save chunks to database
            await self._save_chunks(
                resource_id,
                chunks,
                embeddings,
                enrichments,
                conversion_metadata=parse_result.metadata,
                chunking_metadata=chunking_result.metadata,
            )
            artifacts_created = await self._persist_core_artifacts(
                resource=resource,
                sections=sections,
                chunks=chunks,
                chunking_metadata=chunking_result.metadata,
            )
            metrics["stages"]["persist"]["artifacts_created"] = artifacts_created

            metrics["quality"] = compute_quality_metrics(
                resource_id=resource_id,
                chunks=chunks,
                embeddings=embeddings,
                enrichments=enrichments,
                kb_result={},
                graph_result={},
                bundle_result={},
            )
            if metrics["quality"].get("qa_warnings"):
                logger.warning(
                    "Ingestion QA checks failed for resource %s: %s",
                    resource_id,
                    ", ".join(metrics["quality"]["qa_warnings"]),
                )

            metrics["completed_at"] = datetime.now(timezone.utc).isoformat()
            metrics["status"] = "success"

            # Mark complete
            await update_resource_status(self.db, resource_id, "ready", PIPELINE_VERSION)

            metrics = await self._merge_job_metrics(job_id, metrics)

            await self._update_job_stage(
                job_id,
                IngestionStage.COMPLETE,
                100,
                status="completed",
                metrics=metrics,
            )

            commit = getattr(self.db, "commit", None)
            if callable(commit):
                await commit()
            
            logger.info(f"Core ingestion completed successfully for resource {resource_id}")
            return metrics
            
        except Exception as e:
            logger.error(f"Pipeline failed for resource {resource_id}: {e}")
            
            # Update statuses on failure
            await update_resource_status(
                self.db,
                resource_id,
                "failed",
                PIPELINE_VERSION,
                str(e),
            )
            
            metrics["completed_at"] = datetime.now(timezone.utc).isoformat()
            metrics["status"] = "failed"
            metrics["error"] = str(e)
            metrics = await self._merge_job_metrics(job_id, metrics)

            if job_id:
                await update_job(
                    self.db,
                    job_id,
                    "failed",
                    None,
                    None,
                    error_message=str(e),
                    metrics=metrics,
                )

            commit = getattr(self.db, "commit", None)
            if callable(commit):
                await commit()
            
            raise
    
    async def _get_resource(self, resource_id: uuid.UUID) -> Optional[Resource]:
        """Get resource by ID."""
        result = await self.db.execute(
            select(Resource).where(Resource.id == resource_id)
        )
        return result.scalar_one_or_none()
    
    async def _run_parse_stage(self, resource: Resource) -> DoclingConversionResult:
        """Convert source file with Docling and normalize extracted sections."""
        if not resource.file_path_or_uri:
            raise ValueError(f"Resource {resource.id} has no source path/URI")

        conversion = await self.docling_adapter.convert(resource.file_path_or_uri)
        if not conversion.sections:
            raise ValueError("Docling conversion produced no extractable sections")
        return conversion
    
    async def _run_chunk_stage(self, parse_result: DoclingConversionResult) -> DoclingChunkingResult:
        """Chunk converted Docling document with HybridChunker default."""
        chunking_result = self.docling_chunker.chunk(
            docling_document=parse_result.docling_document,
            sections=parse_result.sections,
        )
        return chunking_result
    
    async def _run_embed_stage(self, chunks: list[ChunkData]) -> list[list[float]]:
        """Generate embeddings for chunks."""
        texts = [chunk.text for chunk in chunks]
        embeddings = await self.embedding.embed(texts)
        return embeddings

    async def _run_graph_stage(self, resource_id: uuid.UUID) -> dict:
        """Compatibility helper for optional graph sync tests and future use."""
        build_result = await self.graph_builder.build(resource_id, force_rebuild=True)

        if not settings.NEO4J_ENABLED:
            build_result["neo4j_sync"] = {
                "synced": False,
                "reason": "disabled",
            }
            return build_result

        client = await get_neo4j_client()
        if client is None:
            build_result["neo4j_sync"] = {
                "synced": False,
                "reason": "client_unavailable",
            }
            return build_result

        if not getattr(client, "is_connected", False):
            build_result["neo4j_sync"] = {
                "synced": False,
                "reason": "not_connected",
            }
            return build_result

        build_result["neo4j_sync"] = {
            "synced": True,
            "reason": "connected",
        }
        return build_result

    def _build_lightweight_enrichments(self, chunks: list[ChunkData]) -> list[dict]:
        """Build minimal deterministic per-chunk metadata for core ingestion."""
        enrichments: list[dict] = []
        for chunk in chunks:
            text = chunk.text or ""
            lowered = text.lower()
            pedagogy_role = None
            if "definition" in lowered:
                pedagogy_role = "definition"
            elif "example" in lowered:
                pedagogy_role = "example"
            elif "exercise" in lowered or "practice" in lowered:
                pedagogy_role = "exercise"

            difficulty = None
            if len(text) > 1200:
                difficulty = "medium"
            if len(text) > 2200:
                difficulty = "hard"

            enrichments.append(
                {
                    "concepts_taught": [],
                    "concepts_mentioned": [],
                    "semantic_relationships": [],
                    "prereq_hints": [],
                    "pedagogy_role": pedagogy_role,
                    "difficulty": difficulty,
                    "skipped": False,
                    "metadata_level": "core_lightweight",
                }
            )
        return enrichments
    
    async def _save_chunks(
        self,
        resource_id: uuid.UUID,
        chunks: list[ChunkData],
        embeddings: list[list[float]],
        enrichments: list[dict],
        conversion_metadata: Optional[dict] = None,
        chunking_metadata: Optional[dict] = None,
    ) -> None:
        """Save chunks and their enrichments to database."""
        from app.services.ingestion.docling_adapter import DoclingAdapter

        for i, (chunk, embedding, enrichment) in enumerate(zip(chunks, embeddings, enrichments)):
            enrichment_payload = dict(enrichment)
            enrichment_payload["docling"] = {
                "chunk_provenance": chunk.metadata,
                "chunking": chunking_metadata or {},
                "conversion": conversion_metadata or {},
            }
            # Ensure entire payload is JSON-serializable (defense-in-depth)
            enrichment_payload = DoclingAdapter._make_json_safe(enrichment_payload)
            db_chunk = Chunk(
                id=uuid.uuid4(),
                resource_id=resource_id,
                text=chunk.text,
                section_heading=chunk.section_heading,
                chunk_index=i,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                pedagogy_role=enrichment.get("pedagogy_role"),
                difficulty=enrichment.get("difficulty"),
                embedding=embedding,
                enrichment_metadata=enrichment_payload,
                embedding_model_id=self.embedding.model_id,
            )
            self.db.add(db_chunk)
            
            # Add chunk concepts
            for concept in enrichment.get("concepts_taught", []):
                self.db.add(ChunkConcept(
                    chunk_id=db_chunk.id,
                    concept_id=concept,
                    role="teaches",
                ))
            
            for concept in enrichment.get("concepts_mentioned", []):
                self.db.add(ChunkConcept(
                    chunk_id=db_chunk.id,
                    concept_id=concept,
                    role="mentions",
                ))
        
        await self.db.flush()

    async def _persist_core_artifacts(
        self,
        *,
        resource: Resource,
        sections: list,
        chunks: list[ChunkData],
        chunking_metadata: Optional[dict] = None,
    ) -> int:
        """Persist lightweight understanding artifacts for future preparation."""
        profile_payload = build_resource_profile(
            filename=resource.filename,
            topic=resource.topic,
            sections=sections,
            chunks=chunks,
            chunking_metadata=chunking_metadata,
        )
        artifact_repo = ResourceArtifactRepository(self.db)
        existing = await artifact_repo.get_for_scope(
            resource_id=resource.id,
            scope_type="resource",
            scope_key=str(resource.id),
            artifact_kind="resource_profile",
        )
        if existing:
            existing.status = "ready"
            existing.version = profile_payload.get("artifact_version", "1.0")
            existing.payload_json = profile_payload
            existing.content_hash = profile_payload.get("content_hash")
            existing.error_message = None
        else:
            self.db.add(
                ResourceArtifactState(
                    resource_id=resource.id,
                    scope_type="resource",
                    scope_key=str(resource.id),
                    artifact_kind="resource_profile",
                    status="ready",
                    version=profile_payload.get("artifact_version", "1.0"),
                    payload_json=profile_payload,
                    content_hash=profile_payload.get("content_hash"),
                )
            )

        capabilities = dict(resource.capabilities_json or {})
        capabilities["resource_profile_ready"] = True
        capabilities["has_resource_profile"] = True
        resource.capabilities_json = capabilities
        await self.db.flush()
        return 1
    
