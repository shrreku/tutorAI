from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.chunk_repo import ChunkRepository
from app.db.repositories.notebook_repo import NotebookResourceRepository
from app.db.repositories.resource_artifact_repo import ResourceArtifactRepository
from app.db.repositories.resource_repo import ResourceRepository
from app.models.resource_artifact import ResourceArtifactState
from app.services.ingestion.resource_profile import build_resource_profile
from app.services.resource_readiness import is_resource_doubt_ready, is_resource_study_ready, normalized_resource_capabilities
from app.services.topic_preparation import build_topic_preparation_artifact


def required_capabilities_for_mode(mode: str) -> list[str]:
    normalized = (mode or "learn").strip().lower()
    if normalized == "doubt":
        return ["can_answer_doubts"]
    if normalized in {"learn", "practice", "revision"}:
        return ["can_answer_doubts", "has_resource_profile"]
    return ["can_answer_doubts", "has_resource_profile"]


def resolve_session_scope(
    anchor_resource_id: UUID,
    *,
    active_resource_ids: list[UUID],
    selected_resource_ids: Optional[list[UUID]] = None,
    notebook_wide: bool = False,
) -> tuple[str, list[UUID]]:
    active_set = set(active_resource_ids)
    if anchor_resource_id not in active_set:
        raise ValueError("Anchor resource is not active in this notebook")

    if notebook_wide:
        return "notebook", list(active_resource_ids)

    if selected_resource_ids:
        resolved: list[UUID] = []
        seen: set[UUID] = set()
        for resource_id in selected_resource_ids:
            if resource_id not in active_set:
                raise ValueError("Selected resource is not active in this notebook")
            if resource_id in seen:
                continue
            resolved.append(resource_id)
            seen.add(resource_id)
        if anchor_resource_id not in seen:
            resolved.insert(0, anchor_resource_id)
        return "selected_resources", resolved

    return "single_resource", [anchor_resource_id]


class NotebookPreparationService:
    """Prepare lightweight notebook session context without forcing heavy KB builds."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.resource_repo = ResourceRepository(db)
        self.chunk_repo = ChunkRepository(db)
        self.artifact_repo = ResourceArtifactRepository(db)
        self.notebook_resource_repo = NotebookResourceRepository(db)

    async def prepare_session_context(
        self,
        *,
        notebook_id: UUID,
        request,
        user_id: UUID,
    ) -> dict[str, Any]:
        active_resource_ids = await self.notebook_resource_repo.list_active_resource_ids(notebook_id)
        scope_type, scope_resource_ids = resolve_session_scope(
            request.resource_id,
            active_resource_ids=active_resource_ids,
            selected_resource_ids=getattr(request, "selected_resource_ids", None),
            notebook_wide=getattr(request, "notebook_wide", False),
        )

        session_mode = (request.mode or "learn").strip().lower()
        required = required_capabilities_for_mode(session_mode)
        artifacts_created = 0
        topic_artifacts_created = 0
        resources: list[Any] = []
        blocking_resources: list[dict[str, str]] = []
        topic_scope_keys: list[str] = []

        for resource_id in scope_resource_ids:
            resource = await self.resource_repo.get_by_id(resource_id)
            if not resource or resource.owner_user_id != user_id:
                raise ValueError("Selected resource is not accessible")

            capabilities = normalized_resource_capabilities(resource)
            if capabilities != (resource.capabilities_json or {}):
                resource.capabilities_json = capabilities
                await self.db.flush()

            is_doubt_ready = is_resource_doubt_ready(resource)
            is_study_ready = is_resource_study_ready(resource)

            if session_mode == "doubt":
                is_ready_for_mode = is_doubt_ready
                blocking_reason = "resource_not_doubt_ready"
            else:
                is_ready_for_mode = is_study_ready
                blocking_reason = "resource_not_study_ready"

            if not is_ready_for_mode:
                blocking_resources.append(
                    {
                        "resource_id": str(resource.id),
                        "filename": resource.filename,
                        "reason": blocking_reason,
                    }
                )
                continue

            if "has_resource_profile" in required and not capabilities.get("has_resource_profile", False):
                artifacts_created += await self._ensure_resource_profile(resource)
                capabilities = dict(resource.capabilities_json or {})

            if (request.mode or "learn").lower() in {"learn", "practice", "revision"}:
                created, scope_key = await self._ensure_topic_prepare(resource, request)
                topic_artifacts_created += created
                if scope_key:
                    topic_scope_keys.append(scope_key)

            resources.append(resource)

        if blocking_resources:
            if session_mode == "doubt":
                raise ValueError("Some selected resources are not doubt-ready yet")
            raise ValueError("Some selected resources are not study-ready yet")

        session_brief = await self._upsert_session_brief(
            notebook_id=notebook_id,
            request=request,
            scope_type=scope_type,
            scope_resource_ids=scope_resource_ids,
            resources=resources,
        )

        return {
            "scope_type": scope_type,
            "scope_resource_ids": [str(resource_id) for resource_id in scope_resource_ids],
            "required_capabilities": required,
            "artifacts_created": artifacts_created,
            "topic_artifacts_created": topic_artifacts_created,
            "topic_scope_keys": topic_scope_keys,
            "blocking_resources": blocking_resources,
            "session_brief_artifact_id": str(session_brief.id),
            "resource_profiles_ready": all(
                bool((resource.capabilities_json or {}).get("has_resource_profile"))
                for resource in resources
            ),
        }

    async def _ensure_resource_profile(self, resource) -> int:
        existing = await self.artifact_repo.get_for_scope(
            resource_id=resource.id,
            scope_type="resource",
            scope_key=str(resource.id),
            artifact_kind="resource_profile",
        )
        if existing and existing.status == "ready" and existing.payload_json:
            capabilities = dict(resource.capabilities_json or {})
            capabilities["resource_profile_ready"] = True
            capabilities["has_resource_profile"] = True
            resource.capabilities_json = capabilities
            await self.db.flush()
            return 0

        chunks = await self.chunk_repo.get_by_resource_id(resource.id, limit=256, offset=0)
        if not chunks:
            raise ValueError(f"Resource {resource.id} has no chunks available for preparation")

        seen_headings: set[str] = set()
        sections: list[dict[str, str]] = []
        for chunk in chunks:
            heading = (chunk.section_heading or "").strip()
            if heading and heading not in seen_headings:
                sections.append({"heading": heading})
                seen_headings.add(heading)

        profile_payload = build_resource_profile(
            filename=resource.filename,
            topic=resource.topic,
            sections=sections,
            chunks=chunks,
            chunking_metadata={"prepared_from": "stored_chunks"},
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

    async def _ensure_topic_prepare(self, resource, request) -> tuple[int, Optional[str]]:
        profile_artifact = await self.artifact_repo.get_for_scope(
            resource_id=resource.id,
            scope_type="resource",
            scope_key=str(resource.id),
            artifact_kind="resource_profile",
        )
        profile_payload = (profile_artifact.payload_json if profile_artifact else None) or {}
        topic_parts = list(getattr(request, "selected_topics", None) or [])
        if getattr(request, "topic", None):
            topic_parts.append(request.topic)
        if not topic_parts:
            topic_parts = profile_payload.get("topic_seeds", [])[:3]
        scope_key = ":".join(
            [
                (request.mode or "learn").lower(),
                "-".join(str(part).strip().lower().replace(" ", "-") for part in topic_parts[:4] if str(part).strip()) or "general",
            ]
        )

        existing = await self.artifact_repo.get_for_scope(
            resource_id=resource.id,
            scope_type="resource_topic",
            scope_key=scope_key,
            artifact_kind="topic_prepare",
        )
        if existing and existing.status == "ready" and existing.payload_json:
            return 0, scope_key

        chunks = await self.chunk_repo.get_by_resource_id(resource.id, limit=256, offset=0)
        if not chunks:
            raise ValueError(f"Resource {resource.id} has no chunks available for topic preparation")

        payload = build_topic_preparation_artifact(
            mode=request.mode,
            topic=getattr(request, "topic", None),
            selected_topics=getattr(request, "selected_topics", None),
            resource_profile=profile_payload,
            chunks=chunks,
        )

        if existing:
            existing.status = "ready"
            existing.version = payload.get("artifact_version", "1.0")
            existing.payload_json = payload
            existing.source_chunk_ids = payload.get("selected_chunk_ids", [])
            existing.content_hash = payload.get("content_hash")
            existing.error_message = None
        else:
            self.db.add(
                ResourceArtifactState(
                    resource_id=resource.id,
                    scope_type="resource_topic",
                    scope_key=scope_key,
                    artifact_kind="topic_prepare",
                    status="ready",
                    version=payload.get("artifact_version", "1.0"),
                    payload_json=payload,
                    source_chunk_ids=payload.get("selected_chunk_ids", []),
                    content_hash=payload.get("content_hash"),
                )
            )
        await self.db.flush()
        return 1, scope_key

    async def _upsert_session_brief(
        self,
        *,
        notebook_id: UUID,
        request,
        scope_type: str,
        scope_resource_ids: list[UUID],
        resources: list[Any],
    ) -> ResourceArtifactState:
        scope_key = f"{notebook_id}:{scope_type}:{request.resource_id}"
        resource_profiles: dict[str, dict] = {}
        for resource in resources:
            profile_artifact = await self.artifact_repo.get_for_scope(
                resource_id=resource.id,
                scope_type="resource",
                scope_key=str(resource.id),
                artifact_kind="resource_profile",
            )
            resource_profiles[str(resource.id)] = profile_artifact.payload_json if profile_artifact else {}

        payload = {
            "artifact_kind": "session_brief",
            "artifact_version": "1.0",
            "mode": request.mode,
            "topic": request.topic,
            "selected_topics": request.selected_topics or [],
            "scope_type": scope_type,
            "scope_resource_ids": [str(resource_id) for resource_id in scope_resource_ids],
            "resources": [
                {
                    "resource_id": str(resource.id),
                    "filename": resource.filename,
                    "topic": resource.topic,
                    "processing_profile": getattr(resource, "processing_profile", None),
                    "capabilities": resource.capabilities_json or {},
                    "document_type": (resource_profiles.get(str(resource.id)) or {}).get("document_type"),
                    "topic_seeds": (resource_profiles.get(str(resource.id)) or {}).get("topic_seeds", []),
                }
                for resource in resources
            ],
        }

        existing = await self.artifact_repo.get_for_scope(
            notebook_id=notebook_id,
            scope_type="notebook_session",
            scope_key=scope_key,
            artifact_kind="session_brief",
        )
        if existing:
            existing.status = "ready"
            existing.version = payload["artifact_version"]
            existing.payload_json = payload
            existing.error_message = None
            await self.db.flush()
            return existing

        artifact = ResourceArtifactState(
            notebook_id=notebook_id,
            scope_type="notebook_session",
            scope_key=scope_key,
            artifact_kind="session_brief",
            status="ready",
            version=payload["artifact_version"],
            payload_json=payload,
        )
        self.db.add(artifact)
        await self.db.flush()
        return artifact
