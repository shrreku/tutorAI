import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.services.curriculum_preparation import CurriculumPreparationService


class _FakeDb:
    def __init__(self, resource):
        self.resource = resource
        self.added = []
        self.committed = False

    async def get(self, _model, resource_id):
        if resource_id == self.resource.id:
            return self.resource
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True


class _FakeOntology:
    semantic_relations = [{"source_id": "heat", "target_id": "conduction", "relation_type": "RELATED_TO"}]

    def get_enrichment_context(self, max_tokens=800):
        assert max_tokens == 800
        return "DOCUMENT TOPICS: heat transfer"


class _FakeExtractor:
    def __init__(self):
        self.calls = 0

    async def extract(self, *, sections, resource_title=None):
        self.calls += 1
        assert sections
        assert resource_title == "heat.pdf"
        return _FakeOntology()


class _FakeEnrichment:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


class _FakeEnricher:
    def __init__(self):
        self.calls = 0

    async def enrich_batch(self, chunks, ontology_context=None):
        self.calls += 1
        assert chunks
        assert ontology_context
        return [
            _FakeEnrichment(
                {
                    "concepts_taught": ["Conduction"],
                    "concepts_mentioned": ["Heat"],
                    "pedagogy_role": "explanation",
                    "difficulty": "intermediate",
                    "prereq_hints": [],
                    "semantic_relationships": [],
                }
            )
            for _ in chunks
        ]


class _FakeKBBuilder:
    async def build(self, *_args, **_kwargs):
        return {"concepts_admitted": 3, "evidence_created": 4, "prereq_hints_created": 1}


class _FakeGraphBuilder:
    async def build(self, *_args, **_kwargs):
        return {"edges_created": 2, "semantic_edges": 1, "cooccurrence_edges": 1}


def test_curriculum_preparation_marks_resource_ready(monkeypatch):
    resource_id = uuid4()
    resource = SimpleNamespace(
        id=resource_id,
        filename="heat.pdf",
        capabilities_json={"curriculum_ready": False, "has_topic_bundles": False},
        curriculum_ready_at=None,
        tutoring_ready_at=None,
        graph_ready_at=None,
        processing_profile="core_only",
    )
    chunks = [
        SimpleNamespace(
            id=uuid4(),
            chunk_index=0,
            text="Conduction transfers heat through matter.",
            section_heading="Conduction",
            page_start=1,
            page_end=1,
            enrichment_metadata={},
            pedagogy_role=None,
            difficulty=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            chunk_index=1,
            text="Metals conduct heat faster than wood.",
            section_heading="Examples",
            page_start=1,
            page_end=2,
            enrichment_metadata={},
            pedagogy_role=None,
            difficulty=None,
        ),
    ]
    db = _FakeDb(resource)
    service = CurriculumPreparationService(
        db,
        ontology_extractor=_FakeExtractor(),
        enricher=_FakeEnricher(),
        kb_builder=_FakeKBBuilder(),
        graph_builder=_FakeGraphBuilder(),
    )

    async def _get_chunks(_resource_id):
        assert _resource_id == resource_id
        return chunks

    async def _persist_enrichments(_chunks, _enrichments):
        assert len(_chunks) == 2
        assert len(_enrichments) == 2

    async def _build_bundles(_resource_id):
        assert _resource_id == resource_id
        return {"bundles_created": 3, "topic_bundles_created": 2}

    async def _upsert_curriculum_artifact(_resource, kb_result, graph_result, bundle_result, source_chunk_ids):
        assert _resource is resource
        assert kb_result["concepts_admitted"] == 3
        assert graph_result["edges_created"] == 2
        assert bundle_result["topic_bundles_created"] == 2
        assert source_chunk_ids == [chunks[0].id, chunks[1].id]
        return SimpleNamespace(id=uuid4())

    async def _save_ontology_data(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_get_chunks", _get_chunks)
    monkeypatch.setattr(service, "_persist_enrichments", _persist_enrichments)
    monkeypatch.setattr(service, "_build_bundles", _build_bundles)
    monkeypatch.setattr(service, "_upsert_curriculum_artifact", _upsert_curriculum_artifact)
    monkeypatch.setattr("app.services.curriculum_preparation.save_ontology_data", _save_ontology_data)

    summary = asyncio.run(service.ensure_curriculum_ready(resource_id))

    assert summary["prepared"] is True
    assert summary["concepts_admitted"] == 3
    assert resource.capabilities_json["curriculum_ready"] is True
    assert resource.capabilities_json["has_concepts"] is True
    assert resource.capabilities_json["has_prereq_graph"] is True
    assert resource.processing_profile == "prepared_for_curriculum"
    assert db.committed is True


def test_curriculum_preparation_skips_already_ready_resource():
    resource_id = uuid4()
    resource = SimpleNamespace(
        id=resource_id,
        filename="heat.pdf",
        capabilities_json={"curriculum_ready": True, "has_topic_bundles": True},
    )
    service = CurriculumPreparationService(
        _FakeDb(resource),
        ontology_extractor=_FakeExtractor(),
        enricher=_FakeEnricher(),
        kb_builder=_FakeKBBuilder(),
        graph_builder=_FakeGraphBuilder(),
    )

    summary = asyncio.run(service.ensure_curriculum_ready(resource_id))

    assert summary == {"prepared": False, "reason": "already_ready"}
