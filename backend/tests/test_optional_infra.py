import asyncio
import uuid

from app.config import settings
import app.services.neo4j.client as neo4j_client_module
import app.services.ingestion.pipeline as ingestion_pipeline_module


def _reset_neo4j_singleton() -> None:
    neo4j_client_module._neo4j_client = None


def test_get_neo4j_client_returns_none_when_disabled(monkeypatch):
    _reset_neo4j_singleton()
    monkeypatch.setattr(settings, "NEO4J_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "NEO4J_URI", "bolt://localhost:7687", raising=False)

    client = asyncio.run(neo4j_client_module.get_neo4j_client())

    assert client is None


def test_get_neo4j_client_returns_none_without_uri(monkeypatch):
    _reset_neo4j_singleton()
    monkeypatch.setattr(settings, "NEO4J_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "NEO4J_URI", None, raising=False)

    client = asyncio.run(neo4j_client_module.get_neo4j_client())

    assert client is None


class _GraphBuilderStub:
    def __init__(self, result: dict):
        self._result = result

    async def build(self, resource_id, force_rebuild=True, ontology_relations=None):
        return dict(self._result)


class _Neo4jClientStub:
    def __init__(self, is_connected: bool):
        self.is_connected = is_connected


def _pipeline_for_graph_stage(result: dict):
    pipeline = object.__new__(ingestion_pipeline_module.IngestionPipeline)
    pipeline.graph_builder = _GraphBuilderStub(result)
    pipeline.db = None
    return pipeline


def test_graph_stage_skips_neo4j_client_when_feature_disabled(monkeypatch):
    async def _should_not_run():
        raise AssertionError("get_neo4j_client should not be called when disabled")

    monkeypatch.setattr(settings, "NEO4J_ENABLED", False, raising=False)
    monkeypatch.setattr(
        ingestion_pipeline_module,
        "get_neo4j_client",
        _should_not_run,
    )
    pipeline = _pipeline_for_graph_stage({"topo_order": {}})

    result = asyncio.run(pipeline._run_graph_stage(uuid.uuid4()))

    assert result["neo4j_sync"]["reason"] == "disabled"


def test_graph_stage_marks_client_unavailable_when_enabled(monkeypatch):
    async def _no_client():
        return None

    monkeypatch.setattr(settings, "NEO4J_ENABLED", True, raising=False)
    monkeypatch.setattr(ingestion_pipeline_module, "get_neo4j_client", _no_client)
    pipeline = _pipeline_for_graph_stage({"topo_order": {}})

    result = asyncio.run(pipeline._run_graph_stage(uuid.uuid4()))

    assert result["neo4j_sync"] == {
        "synced": False,
        "reason": "client_unavailable",
    }


def test_graph_stage_marks_not_connected_when_client_disconnected(monkeypatch):
    async def _disconnected_client():
        return _Neo4jClientStub(is_connected=False)

    monkeypatch.setattr(settings, "NEO4J_ENABLED", True, raising=False)
    monkeypatch.setattr(
        ingestion_pipeline_module,
        "get_neo4j_client",
        _disconnected_client,
    )
    pipeline = _pipeline_for_graph_stage({"topo_order": {}})

    result = asyncio.run(pipeline._run_graph_stage(uuid.uuid4()))

    assert result["neo4j_sync"] == {
        "synced": False,
        "reason": "not_connected",
    }
