#!/usr/bin/env python3
"""Run ingestion pipeline on a PDF file with KB cleanup."""
import asyncio
import logging
import sys
import uuid
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, delete

from app.config import settings
from app.models.resource import Resource
from app.models.chunk import Chunk, ChunkConcept
from app.models.knowledge_base import (
    ResourceConceptStats,
    ResourceConceptEvidence,
    ResourceConceptGraph,
    ResourceBundle,
    ResourceTopicBundle,
    ResourceTopic,
    ResourceLearningObjective,
    ResourcePrereqHint,
)
from app.models.ingestion import IngestionJob
from app.services.ingestion.pipeline import IngestionPipeline
from app.services.llm.openai_provider import OpenAICompatibleProvider
from app.services.embedding.factory import create_embedding_provider
from app.services.storage.factory import create_storage_provider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# Reduce noise from other loggers
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)


async def clear_knowledge_base(session: AsyncSession) -> None:
    """Clear all knowledge base data."""
    logger.info("Clearing existing knowledge base...")
    
    # Delete in order to respect foreign keys
    tables = [
        ResourcePrereqHint,
        ResourceBundle,
        ResourceTopicBundle,
        ResourceConceptGraph,
        ResourceConceptEvidence,
        ResourceConceptStats,
        ResourceLearningObjective,
        ResourceTopic,
        ChunkConcept,
        Chunk,
        IngestionJob,
        Resource,
    ]
    
    for table in tables:
        result = await session.execute(delete(table))
        logger.info(f"  Deleted {result.rowcount} rows from {table.__tablename__}")
    
    await session.commit()
    logger.info("Knowledge base cleared.")


async def main():
    pdf_path = "/Users/shreyashkumar/coding/projects/StudyAgent/tutorAI/notes/MTL106 Lec 1-6.pdf"
    
    if not Path(pdf_path).exists():
        logger.error(f"PDF not found: {pdf_path}")
        return
    
    logger.info("=" * 70)
    logger.info("INGESTION PIPELINE v1.1.0 - WITH ONTOLOGY EXTRACTION")
    logger.info("=" * 70)
    logger.info(f"PDF: {pdf_path}")
    
    # Setup database
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Initialize providers
    logger.info("Initializing providers...")
    llm = OpenAICompatibleProvider(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE_URL,
        model=settings.LLM_MODEL,
    )
    embedding = create_embedding_provider(settings)
    storage = create_storage_provider(settings)
    
    # Clear existing KB
    async with AsyncSessionLocal() as session:
        await clear_knowledge_base(session)
    
    # Create resource
    resource_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        resource = Resource(
            id=resource_id,
            filename="MTL106 Lec 1-6.pdf",
            file_path_or_uri=pdf_path,
            topic="Probability and Statistics",
            status="processing",
        )
        session.add(resource)
        await session.commit()
        logger.info(f"Created resource: {resource_id}")
    
    # Run pipeline
    logger.info("")
    logger.info("=" * 70)
    logger.info("STARTING INGESTION PIPELINE")
    logger.info("=" * 70)
    
    async with AsyncSessionLocal() as session:
        pipeline = IngestionPipeline(session, llm, embedding, storage)
        result = await pipeline.run(resource_id)
    
    # Print results
    logger.info("")
    logger.info("=" * 70)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 70)
    
    status = result.get("status", "unknown")
    logger.info(f"Status: {status}")
    
    if result.get("error"):
        logger.error(f"Error: {result['error']}")
    
    metrics = result.get("metrics", {})
    if metrics:
        logger.info("")
        logger.info("METRICS:")
        logger.info("-" * 40)
        
        # Group metrics
        chunk_metrics = ["chunks_created", "embeddings_created", "enrichments_created", 
                        "enriched_chunks", "skipped_chunks"]
        concept_metrics = ["concepts_admitted", "distinct_concepts_extracted",
                          "avg_concepts_per_chunk", "avg_taught_per_chunk", "avg_mentioned_per_chunk"]
        graph_metrics = ["graph_edges_created", "semantic_edges", "cooccurrence_edges",
                        "semantic_relationships_extracted", "avg_neighbors", "semantic_edge_ratio"]
        kb_metrics = ["evidence_created", "prereq_hints_created", "bundles_created", 
                     "topic_bundles_created"]
        
        logger.info("Chunks:")
        for key in chunk_metrics:
            if key in metrics:
                logger.info(f"  {key}: {metrics[key]}")
        
        logger.info("Concepts:")
        for key in concept_metrics:
            if key in metrics:
                logger.info(f"  {key}: {metrics[key]}")
        
        logger.info("Graph:")
        for key in graph_metrics:
            if key in metrics:
                logger.info(f"  {key}: {metrics[key]}")
        
        logger.info("Knowledge Base:")
        for key in kb_metrics:
            if key in metrics:
                logger.info(f"  {key}: {metrics[key]}")
        
        # QA checks
        qa = metrics.get("qa_checks", {})
        if qa:
            logger.info("")
            logger.info("QA Checks:")
            for check, passed in qa.items():
                status_icon = "✓" if passed else "✗"
                logger.info(f"  {status_icon} {check}")
        
        warnings = metrics.get("qa_warnings", [])
        if warnings:
            logger.warning(f"QA Warnings: {', '.join(warnings)}")
    
    await engine.dispose()
    logger.info("")
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
