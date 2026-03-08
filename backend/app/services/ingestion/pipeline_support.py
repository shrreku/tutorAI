import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import IngestionJob
from app.models.knowledge_base import (
    ResourceConceptGraph,
    ResourceConceptStats,
    ResourceLearningObjective,
    ResourcePrereqHint,
    ResourceTopic,
)
from app.models.resource import Resource
from app.models.resource import study_ready_capabilities
from app.services.ingestion.ingestion_types import ChunkData
from app.services.ingestion.ontology_extractor import ResourceOntology


async def save_ontology_data(
    db: AsyncSession,
    resource_id: uuid.UUID,
    ontology: ResourceOntology,
) -> None:
    """Persist ontology-derived topics and learning objectives."""
    await db.execute(delete(ResourceTopic).where(ResourceTopic.resource_id == resource_id))
    await db.execute(
        delete(ResourceLearningObjective).where(
            ResourceLearningObjective.resource_id == resource_id
        )
    )

    for topic in ontology.main_topics:
        topic_name = topic.get("name", "")
        if topic_name:
            db.add(
                ResourceTopic(
                    resource_id=resource_id,
                    topic_string=topic_name,
                )
            )
        for subtopic in topic.get("subtopics", []):
            if subtopic:
                db.add(
                    ResourceTopic(
                        resource_id=resource_id,
                        topic_string=subtopic,
                    )
                )

    for obj in ontology.learning_objectives:
        obj_text = obj.get("objective", "")
        if obj_text:
            db.add(
                ResourceLearningObjective(
                    resource_id=resource_id,
                    objective_text=obj_text,
                    specificity=obj.get("specificity"),
                )
            )

    await db.flush()


async def get_graph_data(
    db: AsyncSession,
    resource_id: uuid.UUID,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Get concepts, graph edges, and prereq hints for Neo4j sync."""
    concept_result = await db.execute(
        select(ResourceConceptStats).where(ResourceConceptStats.resource_id == resource_id)
    )
    concepts = [
        {
            "concept_id": c.concept_id,
            "name": c.concept_id,
            "teach_count": c.teach_count,
            "mention_count": c.mention_count,
            "avg_quality": c.avg_quality,
        }
        for c in concept_result.scalars().all()
    ]

    edge_result = await db.execute(
        select(ResourceConceptGraph).where(ResourceConceptGraph.resource_id == resource_id)
    )
    edges: list[dict] = []
    for e in edge_result.scalars().all():
        dir_forward = e.dir_forward if e.dir_forward is not None else 0.5
        rel_type = e.relation_type or "RELATED_TO"
        confidence = e.confidence
        if confidence is None:
            confidence = round(min(1.0, max(0.0, abs(dir_forward - 0.5) * 2.0)), 3)

        edges.append(
            {
                "source_concept_id": e.source_concept_id,
                "target_concept_id": e.target_concept_id,
                "assoc_weight": e.assoc_weight,
                "dir_forward": e.dir_forward,
                "dir_backward": e.dir_backward,
                "rel_type": rel_type,
                "confidence": confidence,
            }
        )

    prereq_result = await db.execute(
        select(ResourcePrereqHint).where(ResourcePrereqHint.resource_id == resource_id)
    )
    prereq_hints = [
        {
            "source_concept_id": h.source_concept_id,
            "target_concept_id": h.target_concept_id,
            "support_count": h.support_count,
        }
        for h in prereq_result.scalars().all()
    ]

    return concepts, edges, prereq_hints


def compute_quality_metrics(
    *,
    resource_id: uuid.UUID,
    chunks: list[ChunkData],
    embeddings: list[list[float]],
    enrichments: list[dict],
    kb_result: dict,
    graph_result: dict,
    bundle_result: dict,
) -> dict:
    chunk_count = len(chunks)
    embedding_count = len(embeddings)
    enrichment_count = len(enrichments)
    non_empty_enrichments = sum(
        1
        for enrichment in enrichments
        if (
            enrichment.get("concepts_taught")
            or enrichment.get("concepts_mentioned")
            or enrichment.get("prereq_hints")
            or enrichment.get("semantic_relationships")
        )
        and not enrichment.get("skipped", False)
    )

    skipped_chunks = sum(1 for e in enrichments if e.get("skipped", False))
    total_semantic_rels = sum(len(e.get("semantic_relationships", [])) for e in enrichments)

    total_taught = sum(len(e.get("concepts_taught", [])) for e in enrichments)
    total_mentioned = sum(len(e.get("concepts_mentioned", [])) for e in enrichments)
    total_concepts = total_taught + total_mentioned
    distinct_concepts = {
        concept
        for enrichment in enrichments
        for concept in (enrichment.get("concepts_taught", []) + enrichment.get("concepts_mentioned", []))
    }

    concepts_admitted = kb_result.get("concepts_admitted", 0)
    evidence_created = kb_result.get("evidence_created", 0)
    graph_edges = graph_result.get("edges_created", 0)
    semantic_edges = graph_result.get("semantic_edges", 0)
    cooccurrence_edges = graph_result.get("cooccurrence_edges", 0)

    avg_concepts = total_concepts / chunk_count if chunk_count else 0.0
    avg_taught = total_taught / chunk_count if chunk_count else 0.0
    avg_mentioned = total_mentioned / chunk_count if chunk_count else 0.0
    avg_neighbors = graph_edges / concepts_admitted if concepts_admitted else 0.0
    semantic_ratio = semantic_edges / graph_edges if graph_edges else 0.0

    min_concepts = 1 if chunk_count <= 2 else 3
    checks = {
        "has_chunks": chunk_count > 0,
        "embedding_coverage": embedding_count >= int(chunk_count * 0.8) if chunk_count else False,
        "concept_count_ok": concepts_admitted >= min_concepts,
        "evidence_ok": evidence_created >= concepts_admitted if concepts_admitted else True,
        "graph_edges_ok": graph_edges > 0 if concepts_admitted >= 2 else True,
        "has_semantic_rels": semantic_edges > 0 if concepts_admitted >= 2 else True,
    }
    warnings = [name for name, passed in checks.items() if not passed]

    return {
        "chunks_created": chunk_count,
        "embeddings_created": embedding_count,
        "enrichments_created": enrichment_count,
        "enriched_chunks": non_empty_enrichments,
        "skipped_chunks": skipped_chunks,
        "concepts_admitted": concepts_admitted,
        "evidence_created": evidence_created,
        "prereq_hints_created": kb_result.get("prereq_hints_created", 0),
        "graph_edges_created": graph_edges,
        "semantic_edges": semantic_edges,
        "cooccurrence_edges": cooccurrence_edges,
        "semantic_relationships_extracted": total_semantic_rels,
        "bundles_created": bundle_result.get("bundles_created", 0),
        "topic_bundles_created": bundle_result.get("topic_bundles_created", 0),
        "avg_concepts_per_chunk": round(avg_concepts, 3),
        "avg_taught_per_chunk": round(avg_taught, 3),
        "avg_mentioned_per_chunk": round(avg_mentioned, 3),
        "distinct_concepts_extracted": len(distinct_concepts),
        "avg_neighbors": round(avg_neighbors, 3),
        "semantic_edge_ratio": round(semantic_ratio, 3),
        "qa_checks": checks,
        "qa_warnings": warnings,
    }


async def update_resource_status(
    db: AsyncSession,
    resource_id: uuid.UUID,
    status: str,
    pipeline_version: str,
    error_message: Optional[str] = None,
) -> None:
    """Update resource status fields for ingestion progress."""
    update_data = {
        "status": status,
        "pipeline_version": pipeline_version,
    }

    if status == "ready":
        update_data["processed_at"] = datetime.utcnow()
        update_data["study_ready_at"] = datetime.utcnow()
        update_data["processing_profile"] = "core_only"

        current_resource = await db.get(Resource, resource_id)
        existing_capabilities = current_resource.capabilities_json if current_resource else None
        update_data["capabilities_json"] = study_ready_capabilities(existing_capabilities)

    if error_message:
        update_data["error_message"] = error_message

    await db.execute(
        update(Resource)
        .where(Resource.id == resource_id)
        .values(**update_data)
    )
    await db.flush()


async def update_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    status: str,
    stage,
    progress: Optional[int],
    error_message: Optional[str] = None,
    metrics: Optional[dict] = None,
) -> None:
    """Update ingestion job status and metrics."""
    stage_value = stage.value if hasattr(stage, "value") else stage

    update_data = {"status": status}

    if stage_value:
        update_data["current_stage"] = stage_value

    if progress is not None:
        update_data["progress_percent"] = progress

    if status == "running" and progress == 0:
        update_data["started_at"] = datetime.utcnow()

    if status in ("completed", "failed"):
        update_data["completed_at"] = datetime.utcnow()

    if error_message:
        update_data["error_message"] = error_message
        update_data["error_stage"] = stage_value

    if metrics is not None:
        update_data["metrics"] = metrics

    await db.execute(
        update(IngestionJob)
        .where(IngestionJob.id == job_id)
        .values(**update_data)
    )
    await db.flush()
