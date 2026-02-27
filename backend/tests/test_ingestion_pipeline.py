import asyncio
import uuid
from types import SimpleNamespace

import app.services.ingestion.pipeline as pipeline_module


class _OntologyFixture:
    main_topics = [{"name": "heat transfer", "subtopics": ["conduction"]}]
    concept_taxonomy = [{"concept": "conduction"}]
    prerequisites = [{"source": "temperature", "target": "conduction"}]
    semantic_relations = [
        {
            "source_concept": "temperature",
            "target_concept": "conduction",
            "relation_type": "REQUIRES",
            "confidence": 0.9,
        }
    ]
    learning_objectives = [{"objective": "Explain conduction", "specificity": "medium"}]
    window_count = 1


def test_ingestion_pipeline_run_completes_with_fixture_resource(monkeypatch):
    updates: list[tuple[str, str]] = []

    async def _update_resource_status(db, resource_id, status, pipeline_version, error_message=None):
        updates.append((str(resource_id), status))

    async def _get_resource(self, resource_id):
        return SimpleNamespace(
            id=resource_id,
            filename="fixture.pdf",
            file_path_or_uri="/tmp/fixture.pdf",
        )

    async def _run_parse_stage(self, resource):
        return SimpleNamespace(
            sections=[{"heading": "Intro", "text": "Conduction transfers heat."}],
            status="success",
            warnings=[],
            errors=[],
            metadata={"profile": "balanced"},
        )

    async def _run_chunk_stage(self, parse_result):
        return SimpleNamespace(
            chunks=["chunk-1", "chunk-2"],
            strategy="docling_hybrid",
            metadata={"embedding_strategy": "contextualized"},
        )

    async def _run_ontology_stage(self, sections, resource_title=None):
        return _OntologyFixture()

    async def _run_embed_stage(self, chunks):
        return [[0.1, 0.2], [0.3, 0.4]]

    async def _run_enrich_stage(self, chunks, ontology=None):
        return [
            {
                "concepts_taught": ["conduction"],
                "concepts_mentioned": ["temperature"],
                "semantic_relationships": [
                    {"source": "temperature", "target": "conduction", "type": "REQUIRES"}
                ],
                "prereq_hints": ["temperature"],
                "skipped": False,
            },
            {
                "concepts_taught": ["heat_flux"],
                "concepts_mentioned": ["conduction"],
                "semantic_relationships": [],
                "prereq_hints": [],
                "skipped": False,
            },
        ]

    async def _save_chunks(
        self,
        resource_id,
        chunks,
        embeddings,
        enrichments,
        conversion_metadata=None,
        chunking_metadata=None,
    ):
        return None

    async def _run_kb_stage(self, resource_id, ontology=None):
        return {
            "concepts_admitted": 3,
            "evidence_created": 3,
            "prereq_hints_created": 1,
        }

    async def _run_graph_stage(self, resource_id, ontology=None):
        return {
            "edges_created": 2,
            "semantic_edges": 1,
            "cooccurrence_edges": 1,
            "neo4j_sync": {"synced": False, "reason": "disabled"},
        }

    async def _run_bundle_stage(self, resource_id):
        return {"bundles_created": 2, "topic_bundles_created": 1}

    monkeypatch.setattr(pipeline_module, "update_resource_status", _update_resource_status)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_get_resource", _get_resource)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_parse_stage", _run_parse_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_chunk_stage", _run_chunk_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_ontology_stage", _run_ontology_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_embed_stage", _run_embed_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_enrich_stage", _run_enrich_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_save_chunks", _save_chunks)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_kb_stage", _run_kb_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_graph_stage", _run_graph_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_bundle_stage", _run_bundle_stage)

    pipeline = object.__new__(pipeline_module.IngestionPipeline)
    pipeline.db = object()

    resource_id = uuid.uuid4()
    result = asyncio.run(pipeline.run(resource_id=resource_id))

    assert result["status"] == "success"
    assert result["stages"]["parse"]["sections"] == 1
    assert result["stages"]["chunk"]["chunks"] == 2
    assert result["stages"]["build_graph"]["neo4j_sync"]["reason"] == "disabled"
    assert result["quality"]["chunks_created"] == 2
    assert updates[-1] == (str(resource_id), "ready")
