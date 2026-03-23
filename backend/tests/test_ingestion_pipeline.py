import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import app.services.ingestion.pipeline as pipeline_module


def test_ingestion_pipeline_run_completes_with_fixture_resource(monkeypatch):
    updates: list[tuple[str, str, bool]] = []

    async def _update_resource_status(
        db,
        resource_id,
        status,
        pipeline_version,
        error_message=None,
        study_ready=True,
    ):
        updates.append((str(resource_id), status, study_ready))

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
            metadata={
                "llamaparse": {"pages": [{"page_number": 1}]},
                "profile": "balanced",
            },
        )

    async def _run_chunk_stage(self, parse_result):
        return SimpleNamespace(
            chunks=[
                SimpleNamespace(
                    text="Definition: Conduction transfers heat.",
                    metadata={},
                    section_heading="Intro",
                    page_start=1,
                    page_end=1,
                ),
                SimpleNamespace(
                    text="Example: Heat flows through a rod.",
                    metadata={},
                    section_heading="Intro",
                    page_start=1,
                    page_end=1,
                ),
            ],
            strategy="section_markdown",
            metadata={"embedding_strategy": "raw"},
        )

    async def _save_chunks(
        self,
        resource_id,
        chunks,
        enrichments,
        chunking_metadata=None,
    ):
        return {0: uuid.uuid4(), 1: uuid.uuid4()}

    async def _save_sub_chunks(
        self,
        resource_id,
        sub_chunks,
        embeddings,
        chunk_id_map,
        enrichment_by_chunk_index,
    ):
        del resource_id, sub_chunks, embeddings, chunk_id_map, enrichment_by_chunk_index
        return None

    async def _load_chunk_checkpoint(self, resource_id):
        del resource_id
        return None

    async def _upsert_chunk_checkpoint(
        self, *, resource, sections, chunks, chunking_metadata, document_metrics
    ):
        del resource, sections, chunks, chunking_metadata, document_metrics
        return None

    async def _persist_core_artifacts(
        self, resource, sections, chunks, chunking_metadata=None
    ):
        return 1

    monkeypatch.setattr(
        pipeline_module, "update_resource_status", _update_resource_status
    )
    monkeypatch.setattr(
        pipeline_module.IngestionPipeline, "_get_resource", _get_resource
    )
    monkeypatch.setattr(
        pipeline_module.IngestionPipeline, "_run_parse_stage", _run_parse_stage
    )
    monkeypatch.setattr(
        pipeline_module.IngestionPipeline, "_run_chunk_stage", _run_chunk_stage
    )
    monkeypatch.setattr(pipeline_module.IngestionPipeline, "_save_chunks", _save_chunks)
    monkeypatch.setattr(
        pipeline_module.IngestionPipeline, "_save_sub_chunks", _save_sub_chunks
    )
    monkeypatch.setattr(
        pipeline_module.IngestionPipeline,
        "_load_chunk_checkpoint",
        _load_chunk_checkpoint,
    )
    monkeypatch.setattr(
        pipeline_module.IngestionPipeline,
        "_upsert_chunk_checkpoint",
        _upsert_chunk_checkpoint,
    )
    monkeypatch.setattr(
        pipeline_module.IngestionPipeline,
        "_persist_core_artifacts",
        _persist_core_artifacts,
    )

    pipeline = object.__new__(pipeline_module.IngestionPipeline)
    pipeline.db = object()
    pipeline.embedding = SimpleNamespace(model_id="test-embed")
    pipeline.sub_chunker = SimpleNamespace(
        sub_chunk=lambda chunks: SimpleNamespace(
            sub_chunks=[],
            metadata={"sub_chunks_created": 0},
        )
    )

    resource_id = uuid.uuid4()
    result = asyncio.run(pipeline.run(resource_id=resource_id))

    assert result["status"] == "success"
    assert result["stages"]["parse"]["sections"] == 1
    assert result["stages"]["chunk"]["chunks"] == 2
    assert result["stages"]["persist"]["chunks"] == 2
    assert result["stages"]["persist"]["artifacts_created"] == 1
    assert result["quality"]["chunks_created"] == 2
    assert result["quality"]["concepts_admitted"] == 0
    assert updates[-1] == (str(resource_id), "ready", False)


def test_ingestion_pipeline_merge_job_metrics_preserves_dispatch_state():
    job_id = uuid.uuid4()

    class _Db:
        async def get(self, model, requested_job_id):
            del model
            assert requested_job_id == job_id
            return SimpleNamespace(
                metrics={
                    "billing": {"status": "reserved", "reserved_credits": 750},
                    "page_allowance": {"status": "reserved", "reserved_pages": 12},
                    "async_byok": {"enabled": False, "status": "disabled"},
                }
            )

    pipeline = object.__new__(pipeline_module.IngestionPipeline)
    pipeline.db = _Db()

    merged = asyncio.run(
        pipeline._merge_job_metrics(
            job_id,
            {
                "status": "success",
                "stages": {"persist": {"chunks": 2}},
            },
        )
    )

    assert merged["billing"]["status"] == "reserved"
    assert merged["billing"]["reserved_credits"] == 750
    assert merged["page_allowance"]["status"] == "reserved"
    assert merged["page_allowance"]["reserved_pages"] == 12
    assert merged["async_byok"]["status"] == "disabled"
    assert merged["status"] == "success"
    assert merged["stages"]["persist"]["chunks"] == 2


def test_run_parse_stage_materializes_s3_uri_for_parser(monkeypatch):
    seen = {}

    class _Storage:
        async def open_file(self, file_uri):
            assert file_uri == "s3://studyagent-prod/uploads/fixture.pdf"
            return b"pdf-bytes"

    class _Adapter:
        async def convert(self, source):
            path = Path(source)
            seen["source"] = source
            seen["exists_during_convert"] = path.exists()
            seen["bytes"] = path.read_bytes()
            return SimpleNamespace(
                sections=[{"heading": "Intro", "text": "Stored remotely"}],
                status="success",
                warnings=[],
                errors=[],
                metadata={},
            )

    pipeline = object.__new__(pipeline_module.IngestionPipeline)
    pipeline.storage = _Storage()
    pipeline.parser_adapter = _Adapter()

    resource = SimpleNamespace(
        id=uuid.uuid4(),
        filename="fixture.pdf",
        file_path_or_uri="s3://studyagent-prod/uploads/fixture.pdf",
    )

    result = asyncio.run(pipeline._run_parse_stage(resource))

    assert result.sections
    assert seen["exists_during_convert"] is True
    assert seen["bytes"] == b"pdf-bytes"
    assert seen["source"].endswith(".pdf")
    assert not Path(seen["source"]).exists()
