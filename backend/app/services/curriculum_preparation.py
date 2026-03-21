import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk, ChunkConcept
from app.models.sub_chunk import SubChunk
from app.models.knowledge_base import (
    ResourceBundle,
    ResourceTopicBundle,
)
from app.models.resource import Resource
from app.models.resource_artifact import ResourceArtifactState
from app.services.ingestion.bundle_builder import BundleBuilder
from app.services.ingestion.enricher import ChunkEnricher
from app.services.ingestion.graph_builder import ConceptGraphBuilder
from app.services.ingestion.ingestion_types import ChunkData, SectionData
from app.services.ingestion.kb_builder import ResourceKBBuilder
from app.services.ingestion.ontology_extractor import OntologyExtractor
from app.services.ingestion.pipeline_support import save_ontology_data
from app.utils.canonicalization import canonicalize_concept_id


class CurriculumPreparationService:
    """Build deferred richer KB artifacts when a study session truly needs them."""

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        ontology_extractor: OntologyExtractor,
        enricher: ChunkEnricher,
        kb_builder: Optional[ResourceKBBuilder] = None,
        graph_builder: Optional[ConceptGraphBuilder] = None,
        bundle_builder: Optional[BundleBuilder] = None,
    ):
        self.db = db_session
        self.ontology_extractor = ontology_extractor
        self.enricher = enricher
        self.kb_builder = kb_builder or ResourceKBBuilder(db_session)
        self.graph_builder = graph_builder or ConceptGraphBuilder(db_session)
        self.bundle_builder = bundle_builder or BundleBuilder(db_session)

    async def ensure_curriculum_ready(
        self,
        resource_id: uuid.UUID,
        progress_callback: Optional[Callable[[str, int], Awaitable[None]]] = None,
    ) -> dict:
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
                f"Resource {resource_id} has no chunks available for curriculum preparation"
            )

        if progress_callback is not None:
            await progress_callback("curriculum_ontology", 78)

        sections = self._build_sections(chunks)
        chunk_data = self._build_chunk_data(chunks)

        ontology = await self.ontology_extractor.extract(
            sections=sections, resource_title=resource.filename
        )
        ontology_context = (
            ontology.get_enrichment_context(max_tokens=800) if ontology else None
        )

        if progress_callback is not None:
            await progress_callback("curriculum_enrichment", 86)

        enrichments = await self.enricher.enrich_batch(
            chunk_data, ontology_context=ontology_context
        )
        enrichments_dict = [item.to_dict() for item in enrichments]

        await self._persist_enrichments(chunks, enrichments_dict)

        if progress_callback is not None:
            await progress_callback("curriculum_kb", 92)

        kb_result = await self.kb_builder.build(
            resource_id,
            force_rebuild=True,
            ontology_relations=(ontology.semantic_relations if ontology else None),
        )
        if ontology:
            await save_ontology_data(self.db, resource_id, ontology)

        graph_result = await self.graph_builder.build(
            resource_id,
            force_rebuild=True,
            ontology_relations=(ontology.semantic_relations if ontology else None),
        )

        if progress_callback is not None:
            await progress_callback("curriculum_bundles", 96)

        bundle_result = await self._build_bundles(resource_id)
        await self._mark_resource_ready(
            resource, kb_result, graph_result, bundle_result
        )
        ontology_artifact = await self._upsert_ontology_overview_artifact(
            resource=resource,
            ontology=ontology,
            source_chunk_ids=[chunk.id for chunk in chunks],
        )
        concept_catalog_artifact = await self._upsert_concept_catalog_artifact(
            resource=resource,
            chunks=chunks,
            enrichments=enrichments_dict,
            kb_result=kb_result,
            graph_result=graph_result,
            ontology=ontology,
            source_chunk_ids=[chunk.id for chunk in chunks],
        )
        artifact = await self._upsert_curriculum_artifact(
            resource,
            kb_result,
            graph_result,
            bundle_result,
            source_chunk_ids=[chunk.id for chunk in chunks],
            related_artifact_ids={
                "ontology_overview": str(ontology_artifact.id),
                "concept_catalog": str(concept_catalog_artifact.id),
            },
        )

        if progress_callback is not None:
            await progress_callback("curriculum_finalize", 99)

        await self.db.commit()
        return {
            "prepared": True,
            "artifact_id": str(artifact.id),
            "concepts_admitted": kb_result.get("concepts_admitted", 0),
            "graph_edges": graph_result.get("edges_created", 0),
            "topic_bundles": bundle_result.get("topic_bundles_created", 0),
        }

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
            delete(ChunkConcept).where(
                ChunkConcept.chunk_id.in_(chunk_ids)
            )
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
            chunk.id: enrichment
            for chunk, enrichment in zip(chunks, enrichments)
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

    async def _mark_resource_ready(
        self,
        resource: Resource,
        kb_result: dict,
        graph_result: dict,
        bundle_result: dict,
    ) -> None:
        capabilities = dict(resource.capabilities_json or {})
        has_concepts = kb_result.get("concepts_admitted", 0) > 0
        has_graph = graph_result.get("edges_created", 0) > 0
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
                "can_start_learn_session": has_topic_bundles,
                "can_start_practice_session": has_topic_bundles,
                "can_start_revision_session": has_topic_bundles,
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

    async def _upsert_curriculum_artifact(
        self,
        resource: Resource,
        kb_result: dict,
        graph_result: dict,
        bundle_result: dict,
        source_chunk_ids: list[uuid.UUID],
        related_artifact_ids: Optional[dict[str, str]] = None,
    ) -> ResourceArtifactState:
        result = await self.db.execute(
            select(ResourceArtifactState)
            .where(ResourceArtifactState.resource_id == resource.id)
            .where(ResourceArtifactState.scope_type == "resource")
            .where(ResourceArtifactState.scope_key == str(resource.id))
            .where(ResourceArtifactState.artifact_kind == "curriculum_prepare")
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        payload = {
            "artifact_kind": "curriculum_prepare",
            "artifact_version": "1.0",
            "concepts_admitted": kb_result.get("concepts_admitted", 0),
            "graph_edges": graph_result.get("edges_created", 0),
            "topic_bundles": bundle_result.get("topic_bundles_created", 0),
            "source_chunk_ids": [str(chunk_id) for chunk_id in source_chunk_ids],
            "related_artifact_ids": related_artifact_ids or {},
        }
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if existing:
            existing.status = "ready"
            existing.version = "1.0"
            existing.payload_json = payload
            existing.content_hash = payload_hash
            existing.source_chunk_ids = [
                str(chunk_id) for chunk_id in payload.get("source_chunk_ids", [])
            ]
            existing.error_message = None
            await self.db.flush()
            return existing
        artifact = ResourceArtifactState(
            resource_id=resource.id,
            scope_type="resource",
            scope_key=str(resource.id),
            artifact_kind="curriculum_prepare",
            status="ready",
            version="1.0",
            payload_json=payload,
            source_chunk_ids=[
                str(chunk_id) for chunk_id in payload.get("source_chunk_ids", [])
            ],
            content_hash=payload_hash,
        )
        self.db.add(artifact)
        await self.db.flush()
        return artifact

    async def _upsert_ontology_overview_artifact(
        self,
        *,
        resource: Resource,
        ontology,
        source_chunk_ids: list[uuid.UUID],
    ) -> ResourceArtifactState:
        payload = {
            "artifact_kind": "ontology_overview",
            "artifact_version": "1.0",
            "resource_id": str(resource.id),
            "resource_title": resource.filename,
            "window_count": ontology.window_count,
            "total_pages": ontology.total_pages,
            "main_topics": ontology.main_topics,
            "learning_objectives": ontology.learning_objectives,
            "prerequisites": ontology.prerequisites,
            "concept_taxonomy": ontology.concept_taxonomy,
            "terminology": ontology.terminology,
            "semantic_relations": ontology.semantic_relations,
            "topic_hierarchy": ontology.topic_hierarchy,
            "concept_to_topic": ontology.concept_to_topic,
            "prereq_chain": ontology.prereq_chain,
            "content_summaries": ontology.content_summaries,
            "extraction_errors": ontology.extraction_errors,
            "source_chunk_ids": [str(chunk_id) for chunk_id in source_chunk_ids],
        }
        return await self._upsert_resource_artifact(
            resource_id=resource.id,
            artifact_kind="ontology_overview",
            payload=payload,
            source_chunk_ids=source_chunk_ids,
        )

    async def _upsert_concept_catalog_artifact(
        self,
        *,
        resource: Resource,
        chunks: list[Chunk],
        enrichments: list[dict],
        kb_result: dict,
        graph_result: dict,
        ontology,
        source_chunk_ids: list[uuid.UUID],
    ) -> ResourceArtifactState:
        concept_rows: dict[str, dict] = defaultdict(
            lambda: {
                "raw_names": set(),
                "taught_count": 0,
                "mentioned_count": 0,
                "chunk_ids": set(),
                "chunk_indices": set(),
                "section_headings": set(),
                "pedagogy_roles": set(),
                "difficulties": set(),
                "concept_types": set(),
                "bloom_levels": set(),
                "importance_labels": set(),
                "relationship_count": 0,
                "prereq_targets": set(),
                "prereq_sources": set(),
            }
        )

        ontology_topic_map = {
            str(name).strip().lower(): topic
            for name, topic in (ontology.concept_to_topic or {}).items()
            if str(name).strip()
        }
        ontology_type_map = {
            str(item.get("name", "")).strip().lower(): item.get("concept_type")
            for item in (ontology.concept_taxonomy or [])
            if str(item.get("name", "")).strip()
        }
        ontology_prereqs = {
            canonicalize_concept_id(item.get("concept", ""))
            for item in (ontology.prerequisites or [])
            if canonicalize_concept_id(item.get("concept", ""))
        }

        for chunk, enrichment in zip(chunks, enrichments):
            concept_meta_lookup = {
                meta.get("concept_id"): meta
                for meta in enrichment.get("concept_metadata", [])
                if isinstance(meta, dict) and meta.get("concept_id")
            }

            for concept_id in enrichment.get("concepts_taught", []):
                row = concept_rows[concept_id]
                row["taught_count"] += 1
                row["chunk_ids"].add(str(chunk.id))
                row["chunk_indices"].add(chunk.chunk_index)
                if chunk.section_heading:
                    row["section_headings"].add(chunk.section_heading)
                if enrichment.get("pedagogy_role"):
                    row["pedagogy_roles"].add(enrichment.get("pedagogy_role"))
                if enrichment.get("difficulty"):
                    row["difficulties"].add(enrichment.get("difficulty"))
                meta = concept_meta_lookup.get(concept_id) or {}
                if meta.get("raw_name"):
                    row["raw_names"].add(meta.get("raw_name"))
                if meta.get("concept_type"):
                    row["concept_types"].add(meta.get("concept_type"))
                if meta.get("bloom_level"):
                    row["bloom_levels"].add(meta.get("bloom_level"))
                if meta.get("importance"):
                    row["importance_labels"].add(meta.get("importance"))

            for concept_id in enrichment.get("concepts_mentioned", []):
                row = concept_rows[concept_id]
                row["mentioned_count"] += 1
                row["chunk_ids"].add(str(chunk.id))
                row["chunk_indices"].add(chunk.chunk_index)
                if chunk.section_heading:
                    row["section_headings"].add(chunk.section_heading)
                if enrichment.get("pedagogy_role"):
                    row["pedagogy_roles"].add(enrichment.get("pedagogy_role"))
                if enrichment.get("difficulty"):
                    row["difficulties"].add(enrichment.get("difficulty"))
                meta = concept_meta_lookup.get(concept_id) or {}
                if meta.get("raw_name"):
                    row["raw_names"].add(meta.get("raw_name"))
                if meta.get("concept_type"):
                    row["concept_types"].add(meta.get("concept_type"))
                if meta.get("bloom_level"):
                    row["bloom_levels"].add(meta.get("bloom_level"))
                if meta.get("importance"):
                    row["importance_labels"].add(meta.get("importance"))

            for rel in enrichment.get("semantic_relationships", []):
                if not isinstance(rel, dict):
                    continue
                source_id = canonicalize_concept_id(rel.get("source_id", ""))
                target_id = canonicalize_concept_id(rel.get("target_id", ""))
                if source_id:
                    concept_rows[source_id]["relationship_count"] += 1
                if target_id:
                    concept_rows[target_id]["relationship_count"] += 1
                relation_type = str(rel.get("relation_type", "")).upper().strip()
                if relation_type in {"REQUIRES", "ENABLES", "DERIVES_FROM"}:
                    if source_id and target_id:
                        concept_rows[source_id]["prereq_targets"].add(target_id)
                        concept_rows[target_id]["prereq_sources"].add(source_id)

            raw_names = enrichment.get("raw_concept_names", {}) or {}
            for concept_id, names in raw_names.items():
                if concept_id not in concept_rows:
                    concept_rows[concept_id]
                for name in names or []:
                    if name:
                        concept_rows[concept_id]["raw_names"].add(name)

        concepts = []
        for concept_id in sorted(concept_rows.keys()):
            row = concept_rows[concept_id]
            candidate_names = sorted(row["raw_names"])
            label = candidate_names[0] if candidate_names else concept_id.replace("_", " ")
            normalized_label = str(label).strip().lower()
            concepts.append(
                {
                    "concept_id": concept_id,
                    "label": label,
                    "aliases": candidate_names,
                    "taught_count": row["taught_count"],
                    "mentioned_count": row["mentioned_count"],
                    "chunk_count": len(row["chunk_ids"]),
                    "chunk_indices": sorted(row["chunk_indices"]),
                    "chunk_ids": sorted(row["chunk_ids"]),
                    "section_headings": sorted(row["section_headings"]),
                    "pedagogy_roles": sorted(row["pedagogy_roles"]),
                    "difficulties": sorted(row["difficulties"]),
                    "concept_types": sorted(row["concept_types"]),
                    "bloom_levels": sorted(row["bloom_levels"]),
                    "importance_labels": sorted(row["importance_labels"]),
                    "relationship_count": row["relationship_count"],
                    "prereq_sources": sorted(row["prereq_sources"]),
                    "prereq_targets": sorted(row["prereq_targets"]),
                    "topic_hint": ontology_topic_map.get(normalized_label),
                    "ontology_concept_type": ontology_type_map.get(normalized_label),
                    "is_external_prerequisite": concept_id in ontology_prereqs,
                }
            )

        payload = {
            "artifact_kind": "concept_catalog",
            "artifact_version": "1.0",
            "resource_id": str(resource.id),
            "resource_title": resource.filename,
            "concept_count": len(concepts),
            "concepts_admitted": kb_result.get("concepts_admitted", 0),
            "graph_edges": graph_result.get("edges_created", 0),
            "concepts": concepts,
            "source_chunk_ids": [str(chunk_id) for chunk_id in source_chunk_ids],
        }
        return await self._upsert_resource_artifact(
            resource_id=resource.id,
            artifact_kind="concept_catalog",
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
        normalized_source_chunk_ids = [str(chunk_id) for chunk_id in source_chunk_ids]

        if existing:
            existing.status = "ready"
            existing.version = payload.get("artifact_version", "1.0")
            existing.payload_json = payload
            existing.content_hash = payload_hash
            existing.source_chunk_ids = normalized_source_chunk_ids
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
            source_chunk_ids=normalized_source_chunk_ids,
            content_hash=payload_hash,
        )
        self.db.add(artifact)
        await self.db.flush()
        return artifact
