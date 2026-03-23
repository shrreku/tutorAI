"""Core ingestion pipeline.

Upload-time ingestion now stops once a resource is parsed, chunked, embedded,
and persisted for retrieval. Heavier enrichment and knowledge preparation are
deferred to later job families.
"""

import logging
import re
import tempfile
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from app.config import settings
from app.models.ingestion import IngestionJob
from app.models.resource import Resource
from app.models.resource_artifact import ResourceArtifactState
from app.models.chunk import Chunk, ChunkConcept
from app.models.sub_chunk import SubChunk
from app.db.repositories.resource_artifact_repo import ResourceArtifactRepository
from app.services.llm.base import BaseLLMProvider
from app.services.embedding.base import BaseEmbeddingProvider
from app.services.storage.base import StorageProvider
from app.services.ingestion.llamaparse_adapter import (
    LlamaParseAdapter,
    LlamaParseConversionResult,
)
from app.services.ingestion.section_chunker import SectionChunker, SectionChunkingResult
from app.services.ingestion.sub_chunker import SubChunker
from app.services.ingestion.ingestion_types import ChunkData, SectionData, token_len
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
CORE_CHECKPOINT_ARTIFACT_KIND = "core_ingestion_checkpoint"
CORE_CHECKPOINT_VERSION = "1.0"
_RETRIEVAL_ARTIFACT_PATTERNS = (
    re.compile(r"\bfull[- ]page screenshot\b", re.IGNORECASE),
    re.compile(r"\bnavigation symbols?\b", re.IGNORECASE),
    re.compile(r"\bbeamer\b", re.IGNORECASE),
    re.compile(r"\bswitching between slides\b", re.IGNORECASE),
    re.compile(r"\bimage contains no data to transcribe\b", re.IGNORECASE),
    re.compile(r"\bno data to transcribe into a table\b", re.IGNORECASE),
    re.compile(r"\bscreenshot confirms\b", re.IGNORECASE),
)


class IngestionStage(str, Enum):
    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    PERSIST = "persist"
    CORE_READY = "core_ready"
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

        self.parser_adapter = LlamaParseAdapter()
        self.section_chunker = SectionChunker(
            embedding_model_id=embedding_provider.model_id,
        )
        self.sub_chunker = SubChunker(
            target_tokens=448,
            min_tokens=128,
            overlap_tokens=64,
        )

    @staticmethod
    def _serialize_section(section) -> dict:
        if isinstance(section, dict):
            payload = dict(section)
        else:
            payload = {
                "heading": getattr(section, "heading", None),
                "page_start": getattr(section, "page_start", None),
                "page_end": getattr(section, "page_end", None),
                "text": getattr(section, "text", ""),
                "metadata": getattr(section, "metadata", {}) or {},
            }
        return {
            "heading": payload.get("heading") or payload.get("title"),
            "page_start": payload.get("page_start"),
            "page_end": payload.get("page_end"),
            "text": payload.get("text") or "",
            "metadata": payload.get("metadata") or {},
        }

    @staticmethod
    def _serialize_chunk(chunk: ChunkData) -> dict:
        return {
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "section_heading": chunk.section_heading,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "metadata": chunk.metadata or {},
        }

    @staticmethod
    def _deserialize_section(payload: dict) -> SectionData:
        return SectionData(
            heading=payload.get("heading"),
            page_start=payload.get("page_start"),
            page_end=payload.get("page_end"),
            text=payload.get("text") or "",
            metadata=payload.get("metadata") or {},
        )

    @staticmethod
    def _deserialize_chunk(payload: dict) -> ChunkData:
        return ChunkData(
            chunk_index=int(payload.get("chunk_index") or 0),
            text=payload.get("text") or "",
            section_heading=payload.get("section_heading"),
            page_start=payload.get("page_start"),
            page_end=payload.get("page_end"),
            metadata=payload.get("metadata") or {},
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
        current_metrics = (
            getattr(current_job, "metrics", None) if current_job is not None else None
        )
        if not isinstance(current_metrics, dict):
            return metrics

        return {
            **current_metrics,
            **metrics,
        }

    async def _upsert_chunk_checkpoint(
        self,
        *,
        resource: Resource,
        sections: list,
        chunks: list[ChunkData],
        chunking_metadata: Optional[dict],
        document_metrics: dict,
    ) -> None:
        artifact_repo = ResourceArtifactRepository(self.db)
        payload = {
            "artifact_kind": CORE_CHECKPOINT_ARTIFACT_KIND,
            "artifact_version": CORE_CHECKPOINT_VERSION,
            "stage": "chunk_complete",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "resource_id": str(resource.id),
            "document_metrics": document_metrics,
            "chunking_metadata": chunking_metadata or {},
            "sections": [self._serialize_section(section) for section in sections],
            "chunks": [self._serialize_chunk(chunk) for chunk in chunks],
        }
        existing = await artifact_repo.get_for_scope(
            resource_id=resource.id,
            scope_type="resource",
            scope_key=str(resource.id),
            artifact_kind=CORE_CHECKPOINT_ARTIFACT_KIND,
        )
        if existing:
            existing.status = "ready"
            existing.version = CORE_CHECKPOINT_VERSION
            existing.payload_json = payload
            existing.error_message = None
        else:
            self.db.add(
                ResourceArtifactState(
                    resource_id=resource.id,
                    scope_type="resource",
                    scope_key=str(resource.id),
                    artifact_kind=CORE_CHECKPOINT_ARTIFACT_KIND,
                    status="ready",
                    version=CORE_CHECKPOINT_VERSION,
                    payload_json=payload,
                )
            )
        await self.db.flush()

    async def _load_chunk_checkpoint(
        self, resource_id: uuid.UUID
    ) -> Optional[tuple[list[SectionData], list[ChunkData], dict, dict]]:
        artifact_repo = ResourceArtifactRepository(self.db)
        checkpoint = await artifact_repo.get_for_scope(
            resource_id=resource_id,
            scope_type="resource",
            scope_key=str(resource_id),
            artifact_kind=CORE_CHECKPOINT_ARTIFACT_KIND,
        )
        payload = checkpoint.payload_json if checkpoint is not None else None
        if not isinstance(payload, dict):
            return None
        if payload.get("stage") != "chunk_complete":
            return None
        sections_payload = payload.get("sections")
        chunks_payload = payload.get("chunks")
        if not isinstance(sections_payload, list) or not isinstance(
            chunks_payload, list
        ):
            return None
        sections = [
            self._deserialize_section(item)
            for item in sections_payload
            if isinstance(item, dict)
        ]
        chunks = [
            self._deserialize_chunk(item)
            for item in chunks_payload
            if isinstance(item, dict)
        ]
        document_metrics = payload.get("document_metrics")
        chunking_metadata = payload.get("chunking_metadata")
        return (
            sections,
            chunks,
            document_metrics if isinstance(document_metrics, dict) else {},
            chunking_metadata if isinstance(chunking_metadata, dict) else {},
        )

    async def _clear_partial_core_state(self, resource_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(SubChunk).where(SubChunk.resource_id == resource_id)
        )
        await self.db.execute(
            delete(ChunkConcept).where(
                ChunkConcept.chunk_id.in_(
                    select(Chunk.id).where(Chunk.resource_id == resource_id)
                )
            )
        )
        await self.db.execute(delete(Chunk).where(Chunk.resource_id == resource_id))
        await self.db.flush()

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

        logger.info(
            "Starting ingestion pipeline for resource %s job %s",
            resource_id,
            job_id,
        )

        try:
            # Update job status
            await self._update_job_stage(job_id, IngestionStage.PARSE, 0)

            # Get resource
            resource = await self._get_resource(resource_id)
            if not resource:
                raise ValueError(f"Resource {resource_id} not found")

            if not resource.file_path_or_uri:
                raise ValueError(f"Resource {resource_id} has no file path")

            checkpoint_state = await self._load_chunk_checkpoint(resource_id)
            chunking_metadata: dict = {}
            if checkpoint_state:
                sections, chunks, document_metrics, chunking_metadata = checkpoint_state
                metrics["stages"]["parse"] = {
                    "sections": len(sections),
                    "status": "checkpoint_reused",
                    "warnings": 0,
                    "errors": 0,
                }
                metrics["stages"]["chunk"] = {
                    "chunks": len(chunks),
                    "strategy": "checkpoint_reused",
                    "embedding_strategy": chunking_metadata.get("embedding_strategy"),
                }
                metrics["document"] = document_metrics
                metrics["recovery"] = {
                    "resumable": True,
                    "resumed": True,
                    "resume_from_stage": "chunk",
                    "checkpoint_artifact_kind": CORE_CHECKPOINT_ARTIFACT_KIND,
                }
                logger.warning(
                    "Resuming ingestion for resource %s from saved chunk checkpoint",
                    resource_id,
                )
                await self._clear_partial_core_state(resource_id)
                await self._update_job_stage(
                    job_id, IngestionStage.EMBED, 55, metrics=metrics
                )
            else:
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

                logger.info(f"Stage 2: Chunking text for resource {resource_id}")
                chunking_result = await self._run_chunk_stage(parse_result)
                chunks = chunking_result.chunks
                chunking_metadata = chunking_result.metadata or {}
                document_metrics = self._build_document_metrics(parse_result, chunks)
                metrics["stages"]["chunk"] = {
                    "chunks": len(chunks),
                    "strategy": chunking_result.strategy,
                    "embedding_strategy": chunking_metadata.get("embedding_strategy"),
                }
                metrics["document"] = document_metrics
                metrics["recovery"] = {
                    "resumable": True,
                    "resumed": False,
                    "resume_from_stage": "chunk",
                    "checkpoint_artifact_kind": CORE_CHECKPOINT_ARTIFACT_KIND,
                }
                await self._upsert_chunk_checkpoint(
                    resource=resource,
                    sections=sections,
                    chunks=chunks,
                    chunking_metadata=chunking_metadata,
                    document_metrics=document_metrics,
                )
                commit = getattr(self.db, "commit", None)
                if callable(commit):
                    await commit()

            chunk_metrics = await self._merge_job_metrics(job_id, metrics)
            await self._update_job_stage(
                job_id,
                IngestionStage.EMBED,
                55,
                metrics=chunk_metrics,
            )

            enrichments = self._build_lightweight_enrichments(chunks)
            metrics["stages"]["persist"] = {
                "chunks": len(chunks),
                "light_metadata": len(enrichments),
            }

            # Save parent chunks to database (no embeddings — sub-chunks hold embeddings)
            chunk_id_map = await self._save_chunks(
                resource_id,
                chunks,
                enrichments,
                chunking_metadata=chunking_metadata,
            )
            enrichment_by_chunk_index = {
                int(getattr(chunk, "chunk_index", index)): dict(enrichment)
                for index, (chunk, enrichment) in enumerate(zip(chunks, enrichments))
            }

            # Stage 3: Sub-chunk for retrieval + embed
            logger.info(f"Stage 3: Sub-chunking + embedding for resource {resource_id}")
            sub_chunking_result = self.sub_chunker.sub_chunk(chunks)
            generated_sub_chunks = sub_chunking_result.sub_chunks
            metrics["stages"]["sub_chunk"] = sub_chunking_result.metadata
            retrieval_eligible_parent_indices = {
                index
                for index, enrichment in enrichment_by_chunk_index.items()
                if ((enrichment.get("retrieval") or {}).get("eligible") is not False)
            }
            sub_chunks = [
                sub_chunk
                for sub_chunk in generated_sub_chunks
                if sub_chunk.parent_chunk_index in retrieval_eligible_parent_indices
            ]
            filtered_sub_chunk_count = len(generated_sub_chunks) - len(sub_chunks)
            metrics["stages"]["sub_chunk"]["generated"] = len(generated_sub_chunks)
            metrics["stages"]["sub_chunk"]["indexed"] = len(sub_chunks)
            metrics["stages"]["sub_chunk"]["filtered_out"] = filtered_sub_chunk_count
            metrics["stages"]["sub_chunk"]["filtered_parent_count"] = max(
                0,
                len(enrichment_by_chunk_index) - len(retrieval_eligible_parent_indices),
            )

            if sub_chunks:
                batch_size = max(1, int(settings.INGESTION_EMBED_BATCH_SIZE or 0))
                metrics["stages"]["sub_chunk"]["embed_batch_size"] = batch_size
                embedded_total = 0

                for start in range(0, len(sub_chunks), batch_size):
                    batch = sub_chunks[start : start + batch_size]
                    sub_texts = [sc.text for sc in batch]
                    sub_embeddings = await self.embedding.embed(sub_texts)
                    if len(sub_embeddings) != len(batch):
                        raise ValueError(
                            "Embedding batch size mismatch for sub-chunks: "
                            f"expected {len(batch)}, got {len(sub_embeddings)}"
                        )
                    await self._save_sub_chunks(
                        resource_id,
                        batch,
                        sub_embeddings,
                        chunk_id_map,
                        enrichment_by_chunk_index,
                    )
                    embedded_total += len(sub_embeddings)

                metrics["stages"]["sub_chunk"]["embedded"] = embedded_total
            else:
                logger.warning("No sub-chunks generated for resource %s", resource_id)

            await self._update_job_stage(job_id, IngestionStage.PERSIST, 80)

            artifacts_created = await self._persist_core_artifacts(
                resource=resource,
                sections=sections,
                chunks=chunks,
                chunking_metadata=chunking_metadata,
            )
            metrics["stages"]["persist"]["artifacts_created"] = artifacts_created
            metrics["kb_summary"] = self._build_core_kb_summary(
                chunks,
                sub_chunks,
                enrichments,
                artifacts_created,
                filtered_sub_chunk_count,
            )

            metrics["quality"] = compute_quality_metrics(
                resource_id=resource_id,
                chunks=chunks,
                embeddings=[],  # Sub-chunks hold embeddings now
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
            await update_resource_status(
                self.db,
                resource_id,
                "ready",
                PIPELINE_VERSION,
                study_ready=metrics["quality"].get("concepts_admitted", 0) > 0,
            )

            metrics["capability_progress"] = {
                "search_ready": True,
                "doubt_ready": True,
                "learn_ready": False,
            }

            core_ready_metrics = await self._merge_job_metrics(job_id, metrics)
            await self._update_job_stage(
                job_id,
                IngestionStage.CORE_READY,
                70,
                metrics=core_ready_metrics,
            )

            metrics = await self._merge_job_metrics(job_id, metrics)

            commit = getattr(self.db, "commit", None)
            if callable(commit):
                await commit()

            logger.info(
                f"Core ingestion completed successfully for resource {resource_id}"
            )
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

    def _build_document_metrics(
        self,
        parse_result: LlamaParseConversionResult,
        chunks: list[ChunkData],
    ) -> dict:
        page_numbers: set[int] = set()
        for item in parse_result.sections:
            if isinstance(item, dict):
                page_start = item.get("page_start")
                page_end = item.get("page_end")
            else:
                page_start = getattr(item, "page_start", None)
                page_end = getattr(item, "page_end", None)
            if page_start is not None:
                page_numbers.add(page_start)
            if page_end is not None:
                page_numbers.add(page_end)
        for chunk in chunks:
            if chunk.page_start is not None:
                page_numbers.add(chunk.page_start)
            if chunk.page_end is not None:
                page_numbers.add(chunk.page_end)

        parser_pages = ((parse_result.metadata or {}).get("llamaparse") or {}).get(
            "pages"
        )
        if isinstance(parser_pages, list):
            page_count_actual = max(len(parser_pages), len(page_numbers))
        else:
            page_count_actual = len(page_numbers)

        token_count_actual = sum(token_len(chunk.text or "") for chunk in chunks)
        return {
            "page_count_actual": page_count_actual,
            "section_count": len(parse_result.sections),
            "chunk_count_actual": len(chunks),
            "token_count_actual": token_count_actual,
        }

    async def _get_resource(self, resource_id: uuid.UUID) -> Optional[Resource]:
        """Get resource by ID."""
        result = await self.db.execute(
            select(Resource).where(Resource.id == resource_id)
        )
        return result.scalar_one_or_none()

    async def _run_parse_stage(self, resource: Resource) -> LlamaParseConversionResult:
        """Convert source file with Docling and normalize extracted sections."""
        if not resource.file_path_or_uri:
            raise ValueError(f"Resource {resource.id} has no source path/URI")

        source = resource.file_path_or_uri
        temp_path: Optional[Path] = None

        logger.info(
            "Starting LlamaParse stage for resource %s source=%s",
            resource.id,
            source,
        )

        try:
            parsed = urlparse(source)
            if parsed.scheme == "s3":
                file_bytes = await self.storage.open_file(source)
                suffix = (
                    Path(parsed.path).suffix or Path(resource.filename or "").suffix
                )
                with tempfile.NamedTemporaryFile(
                    prefix="studyagent-ingest-",
                    suffix=suffix,
                    delete=False,
                ) as handle:
                    handle.write(file_bytes)
                    temp_path = Path(handle.name)
                source = str(temp_path)
                logger.info(
                    "Materialized S3 source for LlamaParse resource %s to temp file %s",
                    resource.id,
                    source,
                )

            conversion = await self.parser_adapter.convert(source)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning(
                        "Failed to clean up temp ingestion file %s: %s", temp_path, exc
                    )

        if not conversion.sections:
            raise ValueError("LlamaParse conversion produced no extractable sections")
        logger.info(
            "Completed LlamaParse stage for resource %s parser_job_id=%s sections=%s status=%s",
            resource.id,
            conversion.parser_job_id,
            len(conversion.sections),
            conversion.status,
        )
        return conversion

    async def _run_chunk_stage(
        self, parse_result: LlamaParseConversionResult
    ) -> SectionChunkingResult:
        """Chunk converted Docling document with HybridChunker default."""
        chunking_result = self.section_chunker.chunk(sections=parse_result.sections)
        return chunking_result

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

    def _build_retrieval_metadata(self, chunk: ChunkData) -> dict:
        text = chunk.text or ""
        heading = chunk.section_heading or ""
        combined = "\n".join(part for part in [heading, text] if part)
        pattern_hits = [
            pattern.pattern
            for pattern in _RETRIEVAL_ARTIFACT_PATTERNS
            if pattern.search(combined)
        ]
        alpha_chars = sum(1 for char in combined if char.isalpha())
        eligible = not pattern_hits and not (len(combined) >= 120 and alpha_chars <= 20)
        return {
            "eligible": eligible,
            "artifact_noise": not eligible,
            "artifact_signals": pattern_hits,
        }

    def _build_core_kb_summary(
        self,
        chunks: list[ChunkData],
        indexed_sub_chunks: list,
        enrichments: list[dict],
        artifacts_created: int,
        filtered_sub_chunk_count: int,
    ) -> dict:
        retrieval_eligible_parents = sum(
            1
            for enrichment in enrichments
            if ((enrichment.get("retrieval") or {}).get("eligible") is not False)
        )
        return {
            "phase": "core_ready",
            "parent_chunks": len(chunks),
            "retrieval_eligible_parent_chunks": retrieval_eligible_parents,
            "retrieval_filtered_parent_chunks": len(chunks)
            - retrieval_eligible_parents,
            "indexed_sub_chunks": len(indexed_sub_chunks),
            "retrieval_filtered_sub_chunks": filtered_sub_chunk_count,
            "resource_profile_artifacts": artifacts_created,
        }

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
                    "retrieval": self._build_retrieval_metadata(chunk),
                    "skipped": False,
                    "metadata_level": "core_lightweight",
                }
            )
        return enrichments

    async def _save_chunks(
        self,
        resource_id: uuid.UUID,
        chunks: list[ChunkData],
        enrichments: list[dict],
        chunking_metadata: Optional[dict] = None,
    ) -> dict[int, "uuid.UUID"]:
        """Save parent chunks (no embedding). Returns chunk_index → chunk_id map."""
        from app.services.ingestion.llamaparse_adapter import LlamaParseAdapter

        chunk_id_map: dict[int, uuid.UUID] = {}

        for i, (chunk, enrichment) in enumerate(zip(chunks, enrichments)):
            enrichment_payload = dict(enrichment)
            enrichment_payload["parser"] = {
                "provider": "llamaparse",
                "chunk_provenance": chunk.metadata,
                "chunking": chunking_metadata or {},
            }
            enrichment_payload = LlamaParseAdapter._make_json_safe(enrichment_payload)
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
                embedding=None,  # Sub-chunks hold embeddings
                enrichment_metadata=enrichment_payload,
                embedding_model_id=None,
            )
            self.db.add(db_chunk)
            chunk_id_map[i] = db_chunk.id

            # Add chunk concepts
            for concept in enrichment.get("concepts_taught", []):
                self.db.add(
                    ChunkConcept(
                        chunk_id=db_chunk.id,
                        concept_id=concept,
                        role="teaches",
                    )
                )

            for concept in enrichment.get("concepts_mentioned", []):
                self.db.add(
                    ChunkConcept(
                        chunk_id=db_chunk.id,
                        concept_id=concept,
                        role="mentions",
                    )
                )

        await self.db.flush()
        return chunk_id_map

    async def _save_sub_chunks(
        self,
        resource_id: uuid.UUID,
        sub_chunks: list,
        embeddings: list[list[float]],
        chunk_id_map: dict[int, uuid.UUID],
        enrichment_by_chunk_index: dict[int, dict],
    ) -> None:
        """Save sub-chunks with embeddings and parent chunk references."""
        from app.models.sub_chunk import SubChunk

        for sc, embedding in zip(sub_chunks, embeddings):
            parent_chunk_id = chunk_id_map.get(sc.parent_chunk_index)
            enrichment_payload = dict(
                enrichment_by_chunk_index.get(sc.parent_chunk_index) or {}
            )
            if parent_chunk_id is None:
                logger.warning(
                    "Sub-chunk references unknown parent index %d, skipping",
                    sc.parent_chunk_index,
                )
                continue

            self.db.add(
                SubChunk(
                    id=uuid.uuid4(),
                    parent_chunk_id=parent_chunk_id,
                    resource_id=resource_id,
                    sub_index=sc.sub_index,
                    text=sc.text,
                    char_start=sc.char_start,
                    char_end=sc.char_end,
                    page_start=sc.page_start,
                    page_end=sc.page_end,
                    enrichment_metadata=enrichment_payload,
                    embedding=embedding,
                    embedding_model_id=self.embedding.model_id,
                )
            )

        await self.db.flush()
        logger.info(
            "[INGESTION] Saved %d sub-chunks for resource %s",
            len(sub_chunks),
            resource_id,
        )

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
