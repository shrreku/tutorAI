import asyncio
import uuid
from types import SimpleNamespace

import app.services.ingestion.pipeline as pipeline_module


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
            chunks=[
                SimpleNamespace(text="Definition: Conduction transfers heat.", metadata={}, section_heading="Intro", page_start=1, page_end=1),
                SimpleNamespace(text="Example: Heat flows through a rod.", metadata={}, section_heading="Intro", page_start=1, page_end=1),
            ],
            strategy="docling_hybrid",
            metadata={"embedding_strategy": "contextualized"},
        )

    async def _run_embed_stage(self, chunks):
        return [[0.1, 0.2], [0.3, 0.4]]

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

    async def _persist_core_artifacts(self, resource, sections, chunks, chunking_metadata=None):
        return 1

    monkeypatch.setattr(pipeline_module, "update_resource_status", _update_resource_status)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_get_resource", _get_resource)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_parse_stage", _run_parse_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_chunk_stage", _run_chunk_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_run_embed_stage", _run_embed_stage)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_save_chunks", _save_chunks)
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_persist_core_artifacts", _persist_core_artifacts)

    pipeline = object.__new__(pipeline_module.IngestionPipeline)
    pipeline.db = object()
    pipeline.embedding = SimpleNamespace(model_id="test-embed")

    resource_id = uuid.uuid4()
    result = asyncio.run(pipeline.run(resource_id=resource_id))

    assert result["status"] == "success"
    assert result["stages"]["parse"]["sections"] == 1
    assert result["stages"]["chunk"]["chunks"] == 2
    assert result["stages"]["persist"]["chunks"] == 2
    assert result["stages"]["persist"]["artifacts_created"] == 1
    assert result["quality"]["chunks_created"] == 2
    assert result["quality"]["concepts_admitted"] == 0
    assert updates[-1] == (str(resource_id), "ready")
