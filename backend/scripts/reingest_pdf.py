"""
Script to clear existing KB/graph data and re-ingest a PDF.
Usage: python scripts/reingest_pdf.py <pdf_path>
"""
import asyncio
import sys
import os
from pathlib import Path
from uuid import UUID
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, select, text
from app.db.database import async_session_factory
from app.models.resource import Resource
from app.models.chunk import Chunk
from app.models.ingestion import IngestionJob
from app.models.knowledge_base import (
    ResourceConceptStats,
    ResourceConceptEvidence,
    ResourceConceptGraph,
    ResourceBundle,
    ResourceTopicBundle,
    ResourcePrereqHint,
    ResourceTopic,
    ResourceLearningObjective,
)
from app.services.ingestion.pipeline import IngestionPipeline
from app.services.llm.factory import create_llm_provider
from app.services.embedding.factory import create_embedding_provider
from app.services.storage.factory import create_storage_provider
from app.config import settings


async def clear_all_kb_data(db):
    """Clear all knowledge base and graph data."""
    print("Clearing existing KB/graph data...")
    
    # Delete in order to respect foreign keys
    await db.execute(delete(ResourceBundle))
    await db.execute(delete(ResourceTopicBundle))
    await db.execute(delete(ResourceConceptGraph))
    await db.execute(delete(ResourceConceptEvidence))
    await db.execute(delete(ResourceConceptStats))
    await db.execute(delete(ResourcePrereqHint))
    await db.execute(delete(ResourceTopic))
    await db.execute(delete(ResourceLearningObjective))
    await db.execute(delete(Chunk))
    await db.execute(delete(IngestionJob))
    await db.execute(delete(Resource))
    
    await db.commit()
    print("✓ All KB/graph data cleared")


async def ingest_pdf(db, pdf_path: str):
    """Ingest a PDF file."""
    print(f"\nIngesting PDF: {pdf_path}")
    
    # Read file
    with open(pdf_path, "rb") as f:
        file_content = f.read()
    
    filename = os.path.basename(pdf_path)
    
    # Save to storage
    storage = create_storage_provider(settings)
    file_path = await storage.save_file(file_content, filename)
    print(f"✓ File saved to storage: {file_path}")
    
    # Create resource
    resource = Resource(
        filename=filename,
        topic="Heat Transfer",
        status="processing",
        file_path_or_uri=file_path,
        uploaded_at=datetime.utcnow(),
    )
    db.add(resource)
    await db.flush()
    print(f"✓ Resource created: {resource.id}")
    
    # Create ingestion job
    job = IngestionJob(
        resource_id=resource.id,
        status="pending",
        progress_percent=0,
    )
    db.add(job)
    await db.flush()
    await db.commit()
    print(f"✓ Ingestion job created: {job.id}")
    
    # Create providers
    llm_provider = create_llm_provider(settings)
    embedding_provider = create_embedding_provider(settings)
    storage_provider = create_storage_provider(settings)
    
    # Run pipeline
    print("\nRunning ingestion pipeline...")
    pipeline = IngestionPipeline(
        db_session=db,
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
        storage_provider=storage_provider,
    )
    
    result = await pipeline.run(resource.id, job.id)
    await db.commit()
    
    return resource.id, result


async def print_kb_stats(db, resource_id: UUID):
    """Print knowledge base statistics."""
    print("\n" + "="*60)
    print("KNOWLEDGE BASE STATISTICS")
    print("="*60)
    
    # Concept stats
    result = await db.execute(
        select(ResourceConceptStats).where(ResourceConceptStats.resource_id == resource_id)
    )
    concepts = list(result.scalars().all())
    print(f"\n📊 Concepts admitted: {len(concepts)}")
    
    if concepts:
        print("\nTop concepts by teach count:")
        sorted_concepts = sorted(concepts, key=lambda x: -(x.teach_count or 0))[:10]
        for i, c in enumerate(sorted_concepts, 1):
            print(f"  {i}. {c.concept_id}: teach={c.teach_count}, mention={c.mention_count}, chunks={c.chunk_count}")
    
    # Graph edges
    result = await db.execute(
        select(ResourceConceptGraph).where(ResourceConceptGraph.resource_id == resource_id)
    )
    edges = list(result.scalars().all())
    print(f"\n🔗 Graph edges: {len(edges)}")
    
    if edges:
        # Compute avg degree
        from collections import Counter
        source_counts = Counter(e.source_concept_id for e in edges)
        avg_degree = sum(source_counts.values()) / len(source_counts) if source_counts else 0
        print(f"   Average out-degree: {avg_degree:.2f}")
        print(f"   Max out-degree: {max(source_counts.values()) if source_counts else 0}")
        
        # Sample edges
        print("\nSample edges (top 5 by weight):")
        sorted_edges = sorted(edges, key=lambda x: -(x.assoc_weight or 0))[:5]
        for e in sorted_edges:
            print(f"  {e.source_concept_id} -> {e.target_concept_id} (weight={e.assoc_weight:.3f})")
    
    # Bundles
    result = await db.execute(
        select(ResourceBundle).where(ResourceBundle.resource_id == resource_id)
    )
    bundles = list(result.scalars().all())
    print(f"\n📦 Concept bundles: {len(bundles)}")
    
    result = await db.execute(
        select(ResourceTopicBundle).where(ResourceTopicBundle.resource_id == resource_id)
    )
    topic_bundles = list(result.scalars().all())
    print(f"📚 Topic bundles: {len(topic_bundles)}")
    
    if topic_bundles:
        print("\nTopics:")
        for tb in topic_bundles:
            concept_count = len(tb.primary_concepts or [])
            print(f"  - {tb.topic_name}: {concept_count} concepts")
    
    # Evidence
    result = await db.execute(
        select(ResourceConceptEvidence).where(ResourceConceptEvidence.resource_id == resource_id)
    )
    evidence = list(result.scalars().all())
    print(f"\n📝 Evidence entries: {len(evidence)}")
    
    # Role distribution
    from collections import Counter
    role_counts = Counter(e.role for e in evidence)
    print("   By role:", dict(role_counts))
    
    print("\n" + "="*60)


async def main():
    if len(sys.argv) < 2:
        # Default to Chapter 2.pdf
        pdf_path = str(Path(__file__).parent.parent.parent / "notes" / "Chapter 2.pdf")
    else:
        pdf_path = sys.argv[1]
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)
    
    async with async_session_factory() as db:
        # Clear existing data
        await clear_all_kb_data(db)
        
        # Ingest PDF
        resource_id, result = await ingest_pdf(db, pdf_path)
        
        print("\n✓ Ingestion complete!")
        print(f"Result: {result}")
        
        # Print stats
        await print_kb_stats(db, resource_id)


if __name__ == "__main__":
    asyncio.run(main())
