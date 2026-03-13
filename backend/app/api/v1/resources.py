from uuid import UUID
from typing import Optional
import logging
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.config import settings
from app.db.database import get_db
from app.db.repositories.resource_repo import ResourceRepository
from app.db.repositories.resource_artifact_repo import ResourceArtifactRepository
from app.db.repositories.chunk_repo import ChunkRepository
from app.db.repositories.ingestion_repo import IngestionJobRepository
from app.models.session import UserProfile
from app.models.knowledge_base import (
    ResourceTopicBundle,
    ResourceConceptStats,
    ResourceConceptGraph,
)
from app.api.deps import require_auth
from app.services.resource_readiness import normalized_resource_capabilities
from app.services.storage.factory import create_storage_provider
from app.schemas.api import (
    IngestionAsyncByokStatusResponse,
    ResourceResponse,
    ResourceArtifactResponse,
    ResourceDetailResponse,
    PaginatedResponse,
    ResourceKnowledgeBaseResponse,
    KnowledgeBaseConceptResponse,
    KnowledgeBaseEdgeResponse,
    KnowledgeBaseTopicBundleResponse,
    KnowledgeBaseUpdateRequest,
    IngestionStatusResponse,
)

router = APIRouter(prefix="/resources", tags=["resources"])
logger = logging.getLogger(__name__)

_DAG_RELATION_TYPES = {"PREREQUISITE", "REQUIRES", "BUILDS_ON", "PART_OF"}
_DISPLAY_RELATION_TYPES = {
    "REQUIRES",
    "ENABLES",
    "DERIVES_FROM",
    "PART_OF",
    "IS_A",
    "APPLIES_TO",
}
_DISPLAY_MIN_CONFIDENCE = 0.55
_DISPLAY_MAX_EDGES_PER_CONCEPT = 4


def _resource_response_payload(resource, latest_job=None) -> dict:
    return {
        "id": resource.id,
        "filename": resource.filename,
        "topic": resource.topic,
        "status": resource.status,
        "lifecycle_status": resource.status,
        "processing_profile": getattr(resource, "processing_profile", None),
        "capabilities": normalized_resource_capabilities(
            resource, latest_job=latest_job
        ),
        "uploaded_at": resource.uploaded_at,
        "processed_at": resource.processed_at,
        "latest_job": _job_status_payload(latest_job)
        if latest_job is not None
        else None,
    }


def _job_status_payload(job) -> IngestionStatusResponse:
    metrics = getattr(job, "metrics", None) or {}
    billing = metrics.get("billing") if isinstance(metrics, dict) else None
    curriculum_billing = (
        metrics.get("curriculum_billing") if isinstance(metrics, dict) else None
    )
    async_byok = metrics.get("async_byok") if isinstance(metrics, dict) else None
    document = metrics.get("document") if isinstance(metrics, dict) else None
    capability_progress = (
        metrics.get("capability_progress") if isinstance(metrics, dict) else None
    )
    return IngestionStatusResponse(
        job_id=job.id,
        resource_id=job.resource_id,
        status=job.status,
        job_kind=getattr(job, "job_kind", "core_ingest"),
        requested_capability=getattr(job, "requested_capability", None),
        scope_type=getattr(job, "scope_type", None),
        scope_key=getattr(job, "scope_key", None),
        current_stage=job.current_stage,
        progress_percent=job.progress_percent,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        document_metrics=document if isinstance(document, dict) else None,
        capability_progress=capability_progress
        if isinstance(capability_progress, dict)
        else None,
        billing={
            "uses_platform_credits": bool(billing.get("uses_platform_credits", False)),
            "estimated_credits": int(billing.get("estimated_credits") or 0),
            "reserved_credits": int(billing.get("reserved_credits") or 0),
            "actual_credits": int(billing.get("actual_credits"))
            if billing and billing.get("actual_credits") is not None
            else None,
            "status": str(billing.get("status") or "not_applicable")
            if billing
            else "not_applicable",
            "release_reason": billing.get("release_reason") if billing else None,
            "file_size_bytes": int(billing.get("file_size_bytes") or 0)
            if billing
            else 0,
        }
        if isinstance(billing, dict)
        else None,
        curriculum_billing={
            "estimated_credits_low": int(
                curriculum_billing.get("estimated_credits_low") or 0
            ),
            "estimated_credits_high": int(
                curriculum_billing.get("estimated_credits_high") or 0
            ),
            "reserved_credits": int(curriculum_billing.get("reserved_credits") or 0),
            "actual_credits": int(curriculum_billing.get("actual_credits"))
            if curriculum_billing
            and curriculum_billing.get("actual_credits") is not None
            else None,
            "status": str(curriculum_billing.get("status") or "pending")
            if curriculum_billing
            else "pending",
            "operation_id": str(curriculum_billing.get("operation_id"))
            if curriculum_billing and curriculum_billing.get("operation_id")
            else None,
            "release_reason": curriculum_billing.get("release_reason")
            if curriculum_billing
            else None,
        }
        if isinstance(curriculum_billing, dict)
        else None,
        async_byok=IngestionAsyncByokStatusResponse(
            enabled=bool(async_byok.get("enabled", False)),
            escrow_id=UUID(async_byok["escrow_id"])
            if async_byok.get("escrow_id")
            else None,
            provider_name=async_byok.get("provider_name"),
            status=str(async_byok.get("status") or "disabled"),
            expires_at=datetime.fromisoformat(async_byok["expires_at"])
            if async_byok.get("expires_at")
            else None,
            revoked_at=datetime.fromisoformat(async_byok["revoked_at"])
            if async_byok.get("revoked_at")
            else None,
        )
        if isinstance(async_byok, dict)
        else None,
    )


def _resource_artifact_payload(artifact) -> ResourceArtifactResponse:
    source_chunk_ids = [str(item) for item in (artifact.source_chunk_ids or [])]
    return ResourceArtifactResponse(
        id=artifact.id,
        resource_id=artifact.resource_id,
        notebook_id=artifact.notebook_id,
        scope_type=artifact.scope_type,
        scope_key=artifact.scope_key,
        artifact_kind=artifact.artifact_kind,
        status=artifact.status,
        version=artifact.version,
        payload_json=artifact.payload_json,
        source_chunk_ids=source_chunk_ids or None,
        content_hash=artifact.content_hash,
        generated_at=artifact.generated_at,
        error_message=artifact.error_message,
    )


def _normalize_concept_id(value: str) -> str:
    return "_".join(value.strip().lower().split())


def _normalize_relation_type(value: str) -> str:
    return value.strip().upper().replace(" ", "_")


def _validate_prerequisite_dag(edges: list[ResourceConceptGraph]) -> bool:
    dag_edges = [
        edge
        for edge in edges
        if (edge.relation_type or "").upper() in _DAG_RELATION_TYPES
    ]
    if not dag_edges:
        return True

    adjacency: dict[str, set[str]] = {}
    indegree: dict[str, int] = {}

    for edge in dag_edges:
        source = edge.source_concept_id
        target = edge.target_concept_id
        if source not in adjacency:
            adjacency[source] = set()
        if target not in adjacency:
            adjacency[target] = set()

        if target not in adjacency[source]:
            adjacency[source].add(target)
            indegree[target] = indegree.get(target, 0) + 1
        indegree[source] = indegree.get(source, 0)

    queue = [node for node, degree in indegree.items() if degree == 0]
    visited = 0

    while queue:
        node = queue.pop()
        visited += 1
        for nxt in adjacency.get(node, set()):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    return visited == len(indegree)


def _edge_display_priority(edge: ResourceConceptGraph) -> float:
    confidence = float(edge.confidence or 0.0)
    assoc_weight = float(edge.assoc_weight or 0.0)
    relation_type = (edge.relation_type or "").upper()
    source_bonus = (
        0.08
        if (edge.source or "") in {"ontology_relation", "prereq_hint", "manual"}
        else 0.0
    )
    relation_bonus = (
        0.1 if relation_type in {"REQUIRES", "DERIVES_FROM", "IS_A"} else 0.0
    )
    return confidence + (assoc_weight * 0.08) + source_bonus + relation_bonus


def _curate_display_edges(
    edges: list[ResourceConceptGraph],
) -> list[ResourceConceptGraph]:
    concept_ids = {edge.source_concept_id for edge in edges} | {
        edge.target_concept_id for edge in edges
    }

    filtered = [
        edge
        for edge in edges
        if (edge.relation_type or "").upper() in _DISPLAY_RELATION_TYPES
        and float(edge.confidence or 0.0) >= _DISPLAY_MIN_CONFIDENCE
    ]

    filtered.sort(key=_edge_display_priority, reverse=True)

    degree: dict[str, int] = defaultdict(int)
    curated: list[ResourceConceptGraph] = []
    curated_keys: set[tuple[str, str, str]] = set()
    for edge in filtered:
        source = edge.source_concept_id
        target = edge.target_concept_id
        if (
            degree[source] >= _DISPLAY_MAX_EDGES_PER_CONCEPT
            or degree[target] >= _DISPLAY_MAX_EDGES_PER_CONCEPT
        ):
            continue
        curated.append(edge)
        curated_keys.add((source, target, (edge.relation_type or "").upper()))
        degree[source] += 1
        degree[target] += 1

    # Rescue isolated concepts with the best available edge from full graph.
    # This keeps the rendered graph legible while ensuring each concept has at least one relation,
    # when the source graph contains any relation touching that concept.
    candidate_edges = sorted(edges, key=_edge_display_priority, reverse=True)
    for concept_id in concept_ids:
        if degree[concept_id] > 0:
            continue

        for edge in candidate_edges:
            if (
                edge.source_concept_id != concept_id
                and edge.target_concept_id != concept_id
            ):
                continue

            key = (
                edge.source_concept_id,
                edge.target_concept_id,
                (edge.relation_type or "").upper(),
            )
            if key in curated_keys:
                continue

            source = edge.source_concept_id
            target = edge.target_concept_id
            if (
                degree[source] >= _DISPLAY_MAX_EDGES_PER_CONCEPT + 1
                or degree[target] >= _DISPLAY_MAX_EDGES_PER_CONCEPT + 1
            ):
                continue

            curated.append(edge)
            curated_keys.add(key)
            degree[source] += 1
            degree[target] += 1
            break

    return curated


@router.get("", response_model=PaginatedResponse[ResourceResponse])
async def list_resources(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """List all resources with optional status filter."""
    repo = ResourceRepository(db)
    resources = await repo.list_resources(
        status=status,
        owner_user_id=user.id,
        limit=limit,
        offset=offset,
    )
    job_repo = IngestionJobRepository(db)
    latest_jobs = await job_repo.get_latest_by_resource_ids(
        [resource.id for resource in resources]
    )

    # Get total count
    total = len(resources)  # Simplified; should use count query for large datasets

    return PaginatedResponse(
        items=[
            ResourceResponse(**_resource_response_payload(r, latest_jobs.get(r.id)))
            for r in resources
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{resource_id}", response_model=ResourceDetailResponse)
async def get_resource(
    resource_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get a resource by ID with details."""
    repo = ResourceRepository(db)
    resource = await repo.get_resource_detail(resource_id, owner_user_id=user.id)

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )

    # Count chunks
    chunk_repo = ChunkRepository(db)
    chunk_count = await chunk_repo.count_by_resource(resource_id)
    artifact_repo = ResourceArtifactRepository(db)
    artifacts = await artifact_repo.list_by_resource(resource_id, limit=10, offset=0)
    latest_job = await IngestionJobRepository(db).get_by_resource(resource_id)

    return ResourceDetailResponse(
        **_resource_response_payload(resource, latest_job),
        chunk_count=chunk_count,
        concept_count=len(resource.concept_stats) if resource.concept_stats else 0,
        topic_bundles=[
            {
                "topic_id": tb.topic_id,
                "topic_name": tb.topic_name,
                "primary_concepts": tb.primary_concepts,
            }
            for tb in (resource.topic_bundles or [])
        ],
        artifacts=[_resource_artifact_payload(artifact) for artifact in artifacts],
    )


@router.get(
    "/{resource_id}/artifacts",
    response_model=PaginatedResponse[ResourceArtifactResponse],
)
async def list_resource_artifacts(
    resource_id: UUID,
    artifact_kind: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    repo = ResourceRepository(db)
    resource = await repo.get_by_id(resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )
    if resource.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    artifact_repo = ResourceArtifactRepository(db)
    artifacts = await artifact_repo.list_by_resource(
        resource_id,
        artifact_kind=artifact_kind,
        limit=limit,
        offset=offset,
    )
    total = await artifact_repo.count_by_resource(
        resource_id, artifact_kind=artifact_kind
    )
    return PaginatedResponse(
        items=[_resource_artifact_payload(artifact) for artifact in artifacts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{resource_id}/topics")
async def get_resource_topics(
    resource_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get topic bundles for a resource, used for topic selection UI."""
    repo = ResourceRepository(db)
    resource = await repo.get_by_id(resource_id)

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )

    if resource.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Get topic bundles
    result = await db.execute(
        select(ResourceTopicBundle).where(
            ResourceTopicBundle.resource_id == resource_id
        )
    )
    bundles = result.scalars().all()

    # Get concept stats for concept count + importance
    result2 = await db.execute(
        select(
            ResourceConceptStats.concept_id,
            ResourceConceptStats.teach_count,
            ResourceConceptStats.importance_score,
        ).where(ResourceConceptStats.resource_id == resource_id)
    )
    concept_map = {
        row.concept_id: {
            "teach_count": row.teach_count,
            "importance": row.importance_score,
        }
        for row in result2.all()
    }

    topics = []
    for b in bundles:
        primary = b.primary_concepts or []
        support = b.support_concepts or []
        all_concepts = primary + support
        concept_details = [
            {
                "concept_id": c,
                "teach_count": concept_map.get(c, {}).get("teach_count", 0),
                "importance": concept_map.get(c, {}).get("importance"),
                "role": "primary" if c in primary else "support",
            }
            for c in all_concepts
        ]
        topics.append(
            {
                "topic_id": b.topic_id,
                "topic_name": b.topic_name,
                "primary_concepts": primary,
                "support_concepts": support,
                "concept_count": len(all_concepts),
                "concept_details": concept_details,
                "prereq_topic_ids": b.prereq_topic_ids or [],
            }
        )

    return {
        "resource_id": str(resource_id),
        "resource_name": resource.filename,
        "topic": resource.topic,
        "total_concepts": len(concept_map),
        "topics": topics,
    }


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: UUID,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Delete a resource and all associated data."""
    repo = ResourceRepository(db)
    resource = await repo.get_by_id(resource_id)

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )

    if resource.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if resource.status in {"processing", "pending"} and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resource is currently being ingested. Use force=true to delete anyway.",
        )

    file_uri = resource.file_path_or_uri

    await repo.delete(resource_id)

    if file_uri:
        storage = create_storage_provider(settings)
        try:
            await storage.delete_file(file_uri)
        except Exception as exc:
            logger.warning("Failed to delete resource file '%s': %s", file_uri, exc)


@router.get(
    "/{resource_id}/knowledge-base", response_model=ResourceKnowledgeBaseResponse
)
async def get_resource_knowledge_base(
    resource_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get detailed, editable KB data for a specific resource."""
    repo = ResourceRepository(db)
    resource = await repo.get_by_id(resource_id)

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )

    if resource.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    chunk_repo = ChunkRepository(db)
    chunk_count = await chunk_repo.count_by_resource(resource_id)

    concepts_result = await db.execute(
        select(ResourceConceptStats)
        .where(ResourceConceptStats.resource_id == resource_id)
        .order_by(
            ResourceConceptStats.teach_count.desc(),
            ResourceConceptStats.concept_id.asc(),
        )
    )
    concepts = list(concepts_result.scalars().all())

    bundles_result = await db.execute(
        select(ResourceTopicBundle)
        .where(ResourceTopicBundle.resource_id == resource_id)
        .order_by(ResourceTopicBundle.topic_name.asc())
    )
    bundles = list(bundles_result.scalars().all())

    edges_result = await db.execute(
        select(ResourceConceptGraph)
        .where(ResourceConceptGraph.resource_id == resource_id)
        .order_by(
            ResourceConceptGraph.source_concept_id.asc(),
            ResourceConceptGraph.target_concept_id.asc(),
            ResourceConceptGraph.relation_type.asc(),
        )
    )
    edges = list(edges_result.scalars().all())
    curated_edges = _curate_display_edges(edges)

    latest_job_payload = None
    job_repo = IngestionJobRepository(db)
    latest_job = await job_repo.get_by_resource(resource_id)
    if latest_job:
        latest_job_payload = _job_status_payload(latest_job)

    return ResourceKnowledgeBaseResponse(
        resource_id=resource.id,
        resource_name=resource.filename,
        topic=resource.topic,
        status=resource.status,
        chunk_count=chunk_count,
        concept_count=len(concepts),
        graph_edge_count=len(curated_edges),
        concepts=[
            KnowledgeBaseConceptResponse(
                concept_id=item.concept_id,
                teach_count=item.teach_count,
                mention_count=item.mention_count,
                importance_score=item.importance_score,
                concept_type=item.concept_type,
                bloom_level=item.bloom_level,
                topo_order=item.topo_order,
            )
            for item in concepts
        ],
        edges=[
            KnowledgeBaseEdgeResponse(
                source_concept_id=edge.source_concept_id,
                target_concept_id=edge.target_concept_id,
                relation_type=edge.relation_type,
                assoc_weight=edge.assoc_weight,
                confidence=edge.confidence,
            )
            for edge in curated_edges
        ],
        topic_bundles=[
            KnowledgeBaseTopicBundleResponse(
                topic_id=b.topic_id,
                topic_name=b.topic_name,
                primary_concepts=b.primary_concepts or [],
                support_concepts=b.support_concepts or [],
                prereq_topic_ids=b.prereq_topic_ids or [],
            )
            for b in bundles
        ],
        latest_job=latest_job_payload,
    )


@router.patch(
    "/{resource_id}/knowledge-base", response_model=ResourceKnowledgeBaseResponse
)
async def update_resource_knowledge_base(
    resource_id: UUID,
    payload: KnowledgeBaseUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Update curated KB metadata for a resource (concept overrides and topic bundles)."""
    repo = ResourceRepository(db)
    resource = await repo.get_by_id(resource_id)

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )

    if resource.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if payload.topic is not None:
        resource.topic = payload.topic

    if payload.graph_ops is not None:
        for concept_name in payload.graph_ops.add_concepts:
            concept_id = _normalize_concept_id(concept_name)
            concept_result = await db.execute(
                select(ResourceConceptStats)
                .where(ResourceConceptStats.resource_id == resource_id)
                .where(ResourceConceptStats.concept_id == concept_id)
                .limit(1)
            )
            concept = concept_result.scalar_one_or_none()
            if concept is None:
                db.add(
                    ResourceConceptStats(
                        resource_id=resource_id,
                        concept_id=concept_id,
                        teach_count=0,
                        mention_count=0,
                        chunk_count=0,
                    )
                )

        for rename in payload.graph_ops.rename_concepts:
            old_id = _normalize_concept_id(rename.from_concept_id)
            new_id = _normalize_concept_id(rename.to_concept_id)

            if old_id == new_id:
                continue

            existing_target_result = await db.execute(
                select(ResourceConceptStats)
                .where(ResourceConceptStats.resource_id == resource_id)
                .where(ResourceConceptStats.concept_id == new_id)
                .limit(1)
            )
            if existing_target_result.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot rename concept '{old_id}' to '{new_id}' because target already exists.",
                )

            source_result = await db.execute(
                select(ResourceConceptStats)
                .where(ResourceConceptStats.resource_id == resource_id)
                .where(ResourceConceptStats.concept_id == old_id)
                .limit(1)
            )
            source_concept = source_result.scalar_one_or_none()
            if source_concept is None:
                continue

            source_concept.concept_id = new_id

            outgoing_edges_result = await db.execute(
                select(ResourceConceptGraph)
                .where(ResourceConceptGraph.resource_id == resource_id)
                .where(ResourceConceptGraph.source_concept_id == old_id)
            )
            for edge in outgoing_edges_result.scalars().all():
                edge.source_concept_id = new_id

            incoming_edges_result = await db.execute(
                select(ResourceConceptGraph)
                .where(ResourceConceptGraph.resource_id == resource_id)
                .where(ResourceConceptGraph.target_concept_id == old_id)
            )
            for edge in incoming_edges_result.scalars().all():
                edge.target_concept_id = new_id

            bundle_rows_result = await db.execute(
                select(ResourceTopicBundle).where(
                    ResourceTopicBundle.resource_id == resource_id
                )
            )
            for bundle_row in bundle_rows_result.scalars().all():
                primary = [
                    new_id if item == old_id else item
                    for item in (bundle_row.primary_concepts or [])
                ]
                support = [
                    new_id if item == old_id else item
                    for item in (bundle_row.support_concepts or [])
                ]
                bundle_row.primary_concepts = primary
                bundle_row.support_concepts = support

        for concept_name in payload.graph_ops.remove_concepts:
            concept_id = _normalize_concept_id(concept_name)

            await db.execute(
                delete(ResourceConceptGraph)
                .where(ResourceConceptGraph.resource_id == resource_id)
                .where(
                    (ResourceConceptGraph.source_concept_id == concept_id)
                    | (ResourceConceptGraph.target_concept_id == concept_id)
                )
            )
            await db.execute(
                delete(ResourceConceptStats)
                .where(ResourceConceptStats.resource_id == resource_id)
                .where(ResourceConceptStats.concept_id == concept_id)
            )

            bundle_rows_result = await db.execute(
                select(ResourceTopicBundle).where(
                    ResourceTopicBundle.resource_id == resource_id
                )
            )
            for bundle_row in bundle_rows_result.scalars().all():
                bundle_row.primary_concepts = [
                    item
                    for item in (bundle_row.primary_concepts or [])
                    if item != concept_id
                ]
                bundle_row.support_concepts = [
                    item
                    for item in (bundle_row.support_concepts or [])
                    if item != concept_id
                ]

        for edge_payload in payload.graph_ops.remove_edges:
            source_id = _normalize_concept_id(edge_payload.source_concept_id)
            target_id = _normalize_concept_id(edge_payload.target_concept_id)
            relation_type = _normalize_relation_type(edge_payload.relation_type)
            await db.execute(
                delete(ResourceConceptGraph)
                .where(ResourceConceptGraph.resource_id == resource_id)
                .where(ResourceConceptGraph.source_concept_id == source_id)
                .where(ResourceConceptGraph.target_concept_id == target_id)
                .where(ResourceConceptGraph.relation_type == relation_type)
            )

        for edge_payload in payload.graph_ops.add_edges:
            source_id = _normalize_concept_id(edge_payload.source_concept_id)
            target_id = _normalize_concept_id(edge_payload.target_concept_id)
            relation_type = _normalize_relation_type(edge_payload.relation_type)

            if source_id == target_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Graph edges cannot be self-referential.",
                )

            for concept_id in (source_id, target_id):
                concept_result = await db.execute(
                    select(ResourceConceptStats)
                    .where(ResourceConceptStats.resource_id == resource_id)
                    .where(ResourceConceptStats.concept_id == concept_id)
                    .limit(1)
                )
                if concept_result.scalar_one_or_none() is None:
                    db.add(
                        ResourceConceptStats(
                            resource_id=resource_id,
                            concept_id=concept_id,
                            teach_count=0,
                            mention_count=0,
                            chunk_count=0,
                        )
                    )

            edge_result = await db.execute(
                select(ResourceConceptGraph)
                .where(ResourceConceptGraph.resource_id == resource_id)
                .where(ResourceConceptGraph.source_concept_id == source_id)
                .where(ResourceConceptGraph.target_concept_id == target_id)
                .where(ResourceConceptGraph.relation_type == relation_type)
                .limit(1)
            )
            edge = edge_result.scalar_one_or_none()
            if edge is None:
                db.add(
                    ResourceConceptGraph(
                        resource_id=resource_id,
                        source_concept_id=source_id,
                        target_concept_id=target_id,
                        relation_type=relation_type,
                        assoc_weight=edge_payload.assoc_weight
                        if edge_payload.assoc_weight is not None
                        else 0.0,
                        confidence=edge_payload.confidence
                        if edge_payload.confidence is not None
                        else 0.5,
                        source="manual",
                    )
                )

    for override in payload.concept_overrides:
        concept_id = _normalize_concept_id(override.concept_id)
        concept_result = await db.execute(
            select(ResourceConceptStats)
            .where(ResourceConceptStats.resource_id == resource_id)
            .where(ResourceConceptStats.concept_id == concept_id)
            .limit(1)
        )
        concept = concept_result.scalar_one_or_none()
        if not concept:
            concept = ResourceConceptStats(
                resource_id=resource_id,
                concept_id=concept_id,
                teach_count=0,
                mention_count=0,
                chunk_count=0,
            )
            db.add(concept)

        if override.importance_score is not None:
            concept.importance_score = override.importance_score
        if override.concept_type is not None:
            concept.concept_type = override.concept_type
        if override.bloom_level is not None:
            concept.bloom_level = override.bloom_level
        if override.topo_order is not None:
            concept.topo_order = override.topo_order

    if payload.topic_bundles is not None:
        await db.execute(
            delete(ResourceTopicBundle).where(
                ResourceTopicBundle.resource_id == resource_id
            )
        )

        for bundle in payload.topic_bundles:
            db.add(
                ResourceTopicBundle(
                    resource_id=resource_id,
                    topic_id=bundle.topic_id,
                    topic_name=bundle.topic_name,
                    primary_concepts=[
                        _normalize_concept_id(item) for item in bundle.primary_concepts
                    ],
                    support_concepts=[
                        _normalize_concept_id(item) for item in bundle.support_concepts
                    ],
                    prereq_topic_ids=bundle.prereq_topic_ids,
                )
            )

    all_edges_result = await db.execute(
        select(ResourceConceptGraph).where(
            ResourceConceptGraph.resource_id == resource_id
        )
    )
    all_edges = list(all_edges_result.scalars().all())
    if not _validate_prerequisite_dag(all_edges):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prerequisite-like edges must form a DAG. Remove cyclic edges and try again.",
        )

    await db.flush()

    return await get_resource_knowledge_base(resource_id=resource_id, db=db, user=user)
