"""
Ingestion Pipeline Orchestrator - TICKET-018

Orchestrates the full ingestion pipeline from PDF to Knowledge Base.
"""
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.resource import Resource
from app.models.chunk import Chunk, ChunkConcept
from app.services.llm.base import BaseLLMProvider
from app.services.embedding.base import BaseEmbeddingProvider
from app.services.storage.base import StorageProvider
from app.services.ingestion.docling_adapter import DoclingAdapter, DoclingConversionResult
from app.services.ingestion.docling_chunker import DoclingChunker, DoclingChunkingResult
from app.services.ingestion.ingestion_types import ChunkData
from app.services.ingestion.ontology_extractor import OntologyExtractor, ResourceOntology
from app.services.ingestion.enricher import ChunkEnricher
from app.services.ingestion.kb_builder import ResourceKBBuilder
from app.services.ingestion.graph_builder import ConceptGraphBuilder
from app.services.ingestion.bundle_builder import BundleBuilder
from app.services.ingestion.pipeline_support import (
    compute_quality_metrics,
    get_graph_data,
    save_ontology_data,
    update_job,
    update_resource_status,
)
from app.services.neo4j import get_neo4j_client
from langfuse import observe

from app.config import settings

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1.1.0"  # Added ontology extraction stage


class IngestionStage(str, Enum):
    PARSE = "parse"
    CHUNK = "chunk"
    ONTOLOGY = "ontology"  # New: extract document-level ontology
    EMBED = "embed"
    ENRICH = "enrich"
    BUILD_KB = "build_kb"
    BUILD_GRAPH = "build_graph"
    BUILD_BUNDLES = "build_bundles"
    COMPLETE = "complete"


class IngestionPipeline:
    """Orchestrates the full ingestion pipeline."""
    
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
        
        # Initialize stage processors
        self.docling_adapter = DoclingAdapter()
        self.docling_chunker = DoclingChunker(
            embedding_model_id=embedding_provider.model_id,
            use_contextualized_text=True,
        )
        self.ontology_extractor = OntologyExtractor(
            llm_provider,
            ontology_model=settings.LLM_MODEL_ONTOLOGY or None,
            embed_fn=embedding_provider.embed,
        )
        self.enricher = ChunkEnricher(
            llm_provider,
            enrichment_model=settings.LLM_MODEL_ENRICHMENT or None,
        )
        self.kb_builder = ResourceKBBuilder(db_session)
        self.graph_builder = ConceptGraphBuilder(db_session)
        self.bundle_builder = BundleBuilder(db_session)

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
    
    @observe(name="ingestion-pipeline", capture_input=False)
    async def run(
        self,
        resource_id: uuid.UUID,
        job_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """
        Run the full ingestion pipeline for a resource.
        
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
            
            await self._update_job_stage(job_id, IngestionStage.CHUNK, 15)
            
            # Stage 2: Chunk text
            logger.info(f"Stage 2: Chunking text for resource {resource_id}")
            chunking_result = await self._run_chunk_stage(parse_result)
            chunks = chunking_result.chunks
            metrics["stages"]["chunk"] = {
                "chunks": len(chunks),
                "strategy": chunking_result.strategy,
                "embedding_strategy": chunking_result.metadata.get("embedding_strategy"),
            }
            
            await self._update_job_stage(job_id, IngestionStage.ONTOLOGY, 25)
            
            # Stage 3: Extract document-level ontology (NEW)
            logger.info(f"Stage 3: Extracting ontology for resource {resource_id}")
            ontology = await self._run_ontology_stage(sections, resource.filename)
            metrics["stages"]["ontology"] = {
                "topics": len(ontology.main_topics),
                "concepts": len(ontology.concept_taxonomy),
                "prerequisites": len(ontology.prerequisites),
                "semantic_relations": len(ontology.semantic_relations),
                "learning_objectives": len(ontology.learning_objectives),
                "windows_processed": ontology.window_count,
            }
            
            await self._update_job_stage(job_id, IngestionStage.EMBED, 35)
            
            # Stage 4: Embed chunks
            logger.info(f"Stage 4: Embedding chunks for resource {resource_id}")
            embeddings = await self._run_embed_stage(chunks)
            metrics["stages"]["embed"] = {"embeddings": len(embeddings)}
            
            await self._update_job_stage(job_id, IngestionStage.ENRICH, 45)
            
            # Stage 5: Enrich chunks with LLM (using ontology context)
            logger.info(f"Stage 5: Enriching chunks for resource {resource_id}")
            enrichments = await self._run_enrich_stage(chunks, ontology)
            metrics["stages"]["enrich"] = {
                "enrichments": len(enrichments),
                "skipped": sum(1 for e in enrichments if e.get("skipped", False)),
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
            
            await self._update_job_stage(job_id, IngestionStage.BUILD_KB, 60)
            
            # Stage 6: Build KB
            logger.info(f"Stage 6: Building KB for resource {resource_id}")
            kb_result = await self._run_kb_stage(resource_id, ontology)
            metrics["stages"]["build_kb"] = kb_result
            
            await self._update_job_stage(job_id, IngestionStage.BUILD_GRAPH, 75)
            
            # Stage 7: Build concept graph
            logger.info(f"Stage 7: Building concept graph for resource {resource_id}")
            graph_result = await self._run_graph_stage(resource_id, ontology)
            metrics["stages"]["build_graph"] = graph_result
            
            await self._update_job_stage(job_id, IngestionStage.BUILD_BUNDLES, 90)
            
            # Stage 8: Build bundles
            logger.info(f"Stage 8: Building bundles for resource {resource_id}")
            bundle_result = await self._run_bundle_stage(resource_id)
            metrics["stages"]["build_bundles"] = bundle_result

            metrics["quality"] = compute_quality_metrics(
                resource_id=resource_id,
                chunks=chunks,
                embeddings=embeddings,
                enrichments=enrichments,
                kb_result=kb_result,
                graph_result=graph_result,
                bundle_result=bundle_result,
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

            await self._update_job_stage(
                job_id,
                IngestionStage.COMPLETE,
                100,
                status="completed",
                metrics=metrics,
            )

            await self.db.commit()
            
            logger.info(f"Pipeline completed successfully for resource {resource_id}")
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

            await self.db.commit()
            
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
    
    async def _run_ontology_stage(
        self,
        sections: list,
        resource_title: Optional[str] = None,
    ) -> ResourceOntology:
        """Extract document-level ontology for enrichment guidance."""
        ontology = await self.ontology_extractor.extract(
            sections=sections,
            resource_title=resource_title,
        )
        return ontology
    
    async def _run_embed_stage(self, chunks: list[ChunkData]) -> list[list[float]]:
        """Generate embeddings for chunks."""
        texts = [chunk.text for chunk in chunks]
        embeddings = await self.embedding.embed(texts)
        return embeddings
    
    async def _run_enrich_stage(
        self,
        chunks: list[ChunkData],
        ontology: Optional[ResourceOntology] = None,
    ) -> list[dict]:
        """Enrich chunks with concept extraction, using ontology context."""
        # Generate context string from ontology
        ontology_context = None
        if ontology:
            ontology_context = ontology.get_enrichment_context(max_tokens=800)
            logger.info(f"Using ontology context for enrichment ({len(ontology_context)} chars)")
        
        enrichments = await self.enricher.enrich_batch(
            chunks,
            ontology_context=ontology_context,
        )
        return [e.to_dict() for e in enrichments]
    
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
    
    async def _run_kb_stage(
        self,
        resource_id: uuid.UUID,
        ontology: Optional[ResourceOntology] = None,
    ) -> dict:
        """Build knowledge base, optionally using ontology for prereq hints."""
        result = await self.kb_builder.build(
            resource_id,
            force_rebuild=True,
            ontology_relations=(ontology.semantic_relations if ontology else None),
        )
        
        # Persist ontology-derived topics and learning objectives
        if ontology:
            await save_ontology_data(self.db, resource_id, ontology)
            result["ontology_topics_saved"] = len(ontology.main_topics)
            result["ontology_objectives_saved"] = len(ontology.learning_objectives)
            result["ontology_prerequisites"] = len(ontology.prerequisites)
        
        return result
    
    async def _run_graph_stage(
        self,
        resource_id: uuid.UUID,
        ontology: Optional[ResourceOntology] = None,
    ) -> dict:
        """Build concept graph, enforce DAG, sync to Neo4j if available."""
        result = await self.graph_builder.build(
            resource_id,
            force_rebuild=True,
            ontology_relations=(ontology.semantic_relations if ontology else None),
        )
        
        # Store topo_order back to concept stats
        topo_order = result.get("topo_order", {})
        if topo_order:
            from app.models.knowledge_base import ResourceConceptStats
            for concept_id, order in topo_order.items():
                await self.db.execute(
                    update(ResourceConceptStats)
                    .where(
                        ResourceConceptStats.resource_id == resource_id,
                        ResourceConceptStats.concept_id == concept_id,
                    )
                    .values(topo_order=order)
                )
            await self.db.flush()
        
        # Sync to Neo4j only when explicitly enabled
        if not settings.NEO4J_ENABLED:
            result["neo4j_sync"] = {"synced": False, "reason": "disabled"}
            return result

        try:
            neo4j_client = await get_neo4j_client()
            if neo4j_client is None:
                result["neo4j_sync"] = {
                    "synced": False,
                    "reason": "client_unavailable",
                }
                return result
            if not neo4j_client.is_connected:
                result["neo4j_sync"] = {
                    "synced": False,
                    "reason": "not_connected",
                }
                return result

            concepts, edges, prereq_hints = await get_graph_data(self.db, resource_id)
            neo4j_result = await neo4j_client.sync_resource_graph(
                resource_id=str(resource_id),
                concepts=concepts,
                edges=edges,
                prereq_hints=prereq_hints,
            )
            result["neo4j_sync"] = neo4j_result
            logger.info(f"Synced concept graph to Neo4j for resource {resource_id}")
        except Exception as e:
            logger.warning(f"Failed to sync to Neo4j: {e}")
            result["neo4j_sync"] = {"synced": False, "error": str(e)}
        
        return result
    
    async def _run_bundle_stage(self, resource_id: uuid.UUID) -> dict:
        """Build bundles."""
        concept_result = await self.bundle_builder.build_concept_bundles(
            resource_id, force_rebuild=True
        )
        topic_result = await self.bundle_builder.build_topic_bundles(
            resource_id, force_rebuild=True
        )
        return {**concept_result, **topic_result}
