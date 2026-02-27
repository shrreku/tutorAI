from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.repositories.resource_repo import ResourceRepository
from app.db.repositories.chunk_repo import ChunkRepository
from app.models.resource import Resource
from app.models.knowledge_base import ResourceTopicBundle, ResourceConceptStats
from app.schemas.api import (
    ResourceResponse,
    ResourceDetailResponse,
    PaginatedResponse,
)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=PaginatedResponse[ResourceResponse])
async def list_resources(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all resources with optional status filter."""
    repo = ResourceRepository(db)
    resources = await repo.list_resources(status=status, limit=limit, offset=offset)
    
    # Get total count
    total = len(resources)  # Simplified; should use count query for large datasets
    
    return PaginatedResponse(
        items=[
            ResourceResponse(
                id=r.id,
                filename=r.filename,
                topic=r.topic,
                status=r.status,
                uploaded_at=r.uploaded_at,
                processed_at=r.processed_at,
            )
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
):
    """Get a resource by ID with details."""
    repo = ResourceRepository(db)
    resource = await repo.get_resource_detail(resource_id)
    
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )
    
    # Count chunks
    chunk_repo = ChunkRepository(db)
    chunk_count = await chunk_repo.count_by_resource(resource_id)
    
    return ResourceDetailResponse(
        id=resource.id,
        filename=resource.filename,
        topic=resource.topic,
        status=resource.status,
        uploaded_at=resource.uploaded_at,
        processed_at=resource.processed_at,
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
    )


@router.get("/{resource_id}/topics")
async def get_resource_topics(
    resource_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get topic bundles for a resource, used for topic selection UI."""
    from sqlalchemy import select

    repo = ResourceRepository(db)
    resource = await repo.get_by_id(resource_id)

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )

    # Get topic bundles
    result = await db.execute(
        select(ResourceTopicBundle)
        .where(ResourceTopicBundle.resource_id == resource_id)
    )
    bundles = result.scalars().all()

    # Get concept stats for concept count + importance
    result2 = await db.execute(
        select(ResourceConceptStats.concept_id, ResourceConceptStats.teach_count, ResourceConceptStats.importance_score)
        .where(ResourceConceptStats.resource_id == resource_id)
    )
    concept_map = {row.concept_id: {"teach_count": row.teach_count, "importance": row.importance_score} for row in result2.all()}

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
        topics.append({
            "topic_id": b.topic_id,
            "topic_name": b.topic_name,
            "primary_concepts": primary,
            "support_concepts": support,
            "concept_count": len(all_concepts),
            "concept_details": concept_details,
            "prereq_topic_ids": b.prereq_topic_ids or [],
        })

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
    db: AsyncSession = Depends(get_db),
):
    """Delete a resource and all associated data."""
    repo = ResourceRepository(db)
    resource = await repo.get_by_id(resource_id)
    
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )
    
    await repo.delete(resource_id)
