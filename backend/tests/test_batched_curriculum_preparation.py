"""Tests for BatchedCurriculumPreparationService and progressive readiness."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.models.resource import (
    default_resource_capabilities,
    progressive_ready_capabilities,
)
from app.services.resource_readiness import (
    is_resource_study_ready,
    is_resource_progressively_ready,
    get_batch_progress,
)
from app.services.batched_curriculum_preparation import (
    BatchedCurriculumPreparationService,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeDb:
    def __init__(self, resource):
        self.resource = resource
        self.added = []
        self.committed = False
        self._execute_results = []
        self.executed = []

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

    async def execute(self, _stmt):
        self.executed.append(str(_stmt))
        return _FakeResult([])


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeOntology:
    window_count = 1
    total_pages = 2
    main_topics = [{"name": "Heat Transfer", "subtopics": ["Conduction"]}]
    learning_objectives = [{"objective": "Explain conduction"}]
    prerequisites = [{"concept": "temperature", "importance": "essential"}]
    concept_taxonomy = [
        {"name": "Conduction", "concept_type": "principle"},
    ]
    terminology = [{"term": "conduction", "definition": "heat transfer through matter"}]
    semantic_relations = [
        {
            "source_concept": "Heat",
            "target_concept": "Conduction",
            "relation_type": "RELATED_TO",
        }
    ]
    topic_hierarchy = {"Heat Transfer": {"subtopics": ["Conduction"]}}
    concept_to_topic = {"conduction": "Heat Transfer"}
    prereq_chain = ["temperature"]
    content_summaries = ["Heat transfer overview"]
    extraction_errors = []

    def get_enrichment_context(self, max_tokens=800):
        return "DOCUMENT TOPICS: heat transfer"


class _FakeExtractor:
    def __init__(self):
        self.calls = 0

    async def extract(self, *, sections, resource_title=None):
        self.calls += 1
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
    def __init__(self):
        self.calls = []

    async def build(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return {
            "concepts_admitted": 3,
            "evidence_created": 4,
            "prereq_hints_created": 1,
        }


class _FakeGraphBuilder:
    def __init__(self):
        self.calls = []

    async def build(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return {"edges_created": 2, "semantic_edges": 1, "cooccurrence_edges": 1}


# ---------------------------------------------------------------------------
# Tests: progressive_ready_capabilities
# ---------------------------------------------------------------------------


def test_default_capabilities_include_progressive_fields():
    caps = default_resource_capabilities()
    assert caps["has_partial_curriculum"] is False
    assert caps["progressive_study_ready"] is False
    assert caps["supports_incremental_curriculum"] is False
    assert caps["ready_batch_count"] == 0
    assert caps["total_batch_count"] == 0


def test_progressive_ready_capabilities_with_one_batch():
    caps = progressive_ready_capabilities(
        ready_batch_count=1,
        total_batch_count=3,
        has_concepts=True,
    )
    assert caps["has_partial_curriculum"] is True
    assert caps["progressive_study_ready"] is True
    assert caps["can_start_learn_session"] is True
    assert caps["can_start_practice_session"] is True
    assert caps["can_start_revision_session"] is True
    assert caps["ready_batch_count"] == 1
    assert caps["total_batch_count"] == 3
    # Not fully ready yet
    assert caps["study_ready"] is True  # has_concepts is True


def test_progressive_ready_capabilities_fully_ready():
    caps = progressive_ready_capabilities(
        ready_batch_count=3,
        total_batch_count=3,
        has_concepts=True,
    )
    assert caps["study_ready"] is True
    assert caps["progressive_study_ready"] is True


def test_progressive_ready_capabilities_zero_batches():
    caps = progressive_ready_capabilities(
        ready_batch_count=0,
        total_batch_count=3,
        has_concepts=False,
    )
    assert caps["has_partial_curriculum"] is False
    assert caps["progressive_study_ready"] is False
    assert caps["can_start_learn_session"] is False


# ---------------------------------------------------------------------------
# Tests: resource_readiness
# ---------------------------------------------------------------------------


def test_is_resource_study_ready_with_progressive():
    resource = SimpleNamespace(
        status="processing",
        capabilities_json={
            "progressive_study_ready": True,
            "ready_batch_count": 1,
            "total_batch_count": 3,
        },
    )
    assert is_resource_study_ready(resource) is True


def test_is_resource_progressively_ready():
    resource = SimpleNamespace(
        status="processing",
        capabilities_json={
            "progressive_study_ready": True,
            "has_partial_curriculum": True,
            "ready_batch_count": 2,
        },
    )
    assert is_resource_progressively_ready(resource) is True


def test_is_resource_not_progressively_ready():
    resource = SimpleNamespace(
        status="processing",
        capabilities_json={
            "progressive_study_ready": False,
            "has_partial_curriculum": False,
            "ready_batch_count": 0,
        },
    )
    assert is_resource_progressively_ready(resource) is False


def test_get_batch_progress():
    resource = SimpleNamespace(
        capabilities_json={
            "ready_batch_count": 2,
            "total_batch_count": 5,
            "progressive_study_ready": True,
            "has_partial_curriculum": True,
            "supports_incremental_curriculum": True,
        },
    )
    progress = get_batch_progress(resource)
    assert progress["ready_batch_count"] == 2
    assert progress["total_batch_count"] == 5
    assert progress["progressive_study_ready"] is True


# ---------------------------------------------------------------------------
# Tests: BatchedCurriculumPreparationService
# ---------------------------------------------------------------------------


def test_batched_service_processes_resource(monkeypatch):
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
            chunk_index=i,
            text=f"Chunk {i} text about heat conduction in materials. " * 10,
            section_heading="Conduction" if i < 3 else "Radiation",
            page_start=i,
            page_end=i + 1,
            enrichment_metadata={},
            pedagogy_role=None,
            difficulty=None,
        )
        for i in range(6)
    ]
    db = _FakeDb(resource)
    service = BatchedCurriculumPreparationService(
        db,
        ontology_extractor=_FakeExtractor(),
        enricher=_FakeEnricher(),
        kb_builder=_FakeKBBuilder(),
        graph_builder=_FakeGraphBuilder(),
        batch_token_target=200,  # small target to force multiple batches
    )

    async def _get_chunks(_resource_id):
        return chunks

    async def _persist_enrichments(_chunks, _enrichments):
        return None

    async def _build_bundles(_resource_id):
        return {"bundles_created": 2, "topic_bundles_created": 1}

    async def _plan_batches(_resource_id, _chunks):
        """Return pre-built batches to avoid DB execute calls."""
        batch1 = SimpleNamespace(
            id=uuid4(),
            resource_id=_resource_id,
            batch_index=0,
            status="pending",
            chunk_index_start=0,
            chunk_index_end=2,
            section_headings=["Conduction"],
            chunk_ids=[str(c.id) for c in _chunks[:3]],
            token_estimate=300,
            ontology_status="pending",
            enrichment_status="pending",
            kb_merge_status="pending",
            graph_merge_status="pending",
            is_retrieval_ready=False,
            is_study_ready=False,
            concepts_admitted=0,
            graph_edges_created=0,
            ontology_context=None,
            result_json=None,
            error_message=None,
            ontology_completed_at=None,
            enrichment_completed_at=None,
            kb_merge_completed_at=None,
            completed_at=None,
        )
        batch2 = SimpleNamespace(
            id=uuid4(),
            resource_id=_resource_id,
            batch_index=1,
            status="pending",
            chunk_index_start=3,
            chunk_index_end=5,
            section_headings=["Radiation"],
            chunk_ids=[str(c.id) for c in _chunks[3:]],
            token_estimate=300,
            ontology_status="pending",
            enrichment_status="pending",
            kb_merge_status="pending",
            graph_merge_status="pending",
            is_retrieval_ready=False,
            is_study_ready=False,
            concepts_admitted=0,
            graph_edges_created=0,
            ontology_context=None,
            result_json=None,
            error_message=None,
            ontology_completed_at=None,
            enrichment_completed_at=None,
            kb_merge_completed_at=None,
            completed_at=None,
        )
        return [batch1, batch2]

    async def _upsert_processing_manifest_artifact(**_kwargs):
        return SimpleNamespace(id=uuid4())

    async def _upsert_curriculum_artifact(
        _resource, _kb, _bundle, source_chunk_ids, related_artifact_ids=None
    ):
        return SimpleNamespace(id=uuid4())

    async def _save_ontology_data(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_get_chunks", _get_chunks)
    monkeypatch.setattr(service, "_persist_enrichments", _persist_enrichments)
    monkeypatch.setattr(service, "_build_bundles", _build_bundles)
    monkeypatch.setattr(service, "_plan_batches", _plan_batches)
    monkeypatch.setattr(
        service,
        "_upsert_processing_manifest_artifact",
        _upsert_processing_manifest_artifact,
    )
    monkeypatch.setattr(
        service, "_upsert_curriculum_artifact", _upsert_curriculum_artifact
    )
    monkeypatch.setattr(
        "app.services.batched_curriculum_preparation.save_ontology_data",
        _save_ontology_data,
    )

    summary = asyncio.run(service.ensure_curriculum_ready(resource_id))

    assert summary["prepared"] is True
    assert summary["total_batches"] == 2
    assert summary["batches_completed"] == 2
    assert summary["batches_failed"] == 0
    assert summary["concepts_admitted"] == 6  # 3 per batch × 2
    assert summary["graph_edges"] == 4  # 2 per batch × 2
    assert db.committed is True


def test_batched_service_skips_already_ready():
    resource_id = uuid4()
    resource = SimpleNamespace(
        id=resource_id,
        filename="heat.pdf",
        capabilities_json={"curriculum_ready": True, "has_topic_bundles": True},
    )
    service = BatchedCurriculumPreparationService(
        _FakeDb(resource),
        ontology_extractor=_FakeExtractor(),
        enricher=_FakeEnricher(),
        kb_builder=_FakeKBBuilder(),
        graph_builder=_FakeGraphBuilder(),
    )

    summary = asyncio.run(service.ensure_curriculum_ready(resource_id))
    assert summary == {"prepared": False, "reason": "already_ready"}


def test_batched_service_reports_progress(monkeypatch):
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
    ]
    db = _FakeDb(resource)
    service = BatchedCurriculumPreparationService(
        db,
        ontology_extractor=_FakeExtractor(),
        enricher=_FakeEnricher(),
        kb_builder=_FakeKBBuilder(),
        graph_builder=_FakeGraphBuilder(),
    )
    progress_events = []

    async def _get_chunks(_resource_id):
        return chunks

    async def _persist_enrichments(_chunks, _enrichments):
        return None

    async def _build_bundles(_resource_id):
        return {"bundles_created": 1, "topic_bundles_created": 1}

    async def _plan_batches(_resource_id, _chunks):
        batch = SimpleNamespace(
            id=uuid4(),
            resource_id=_resource_id,
            batch_index=0,
            status="pending",
            chunk_index_start=0,
            chunk_index_end=0,
            section_headings=["Conduction"],
            chunk_ids=[str(c.id) for c in _chunks],
            token_estimate=50,
            ontology_status="pending",
            enrichment_status="pending",
            kb_merge_status="pending",
            graph_merge_status="pending",
            is_retrieval_ready=False,
            is_study_ready=False,
            concepts_admitted=0,
            graph_edges_created=0,
            ontology_context=None,
            result_json=None,
            error_message=None,
            ontology_completed_at=None,
            enrichment_completed_at=None,
            kb_merge_completed_at=None,
            completed_at=None,
        )
        return [batch]

    async def _upsert_processing_manifest_artifact(**_kwargs):
        return SimpleNamespace(id=uuid4())

    async def _upsert_curriculum_artifact(
        _resource, _kb, _bundle, source_chunk_ids, related_artifact_ids=None
    ):
        return SimpleNamespace(id=uuid4())

    async def _save_ontology_data(*_args, **_kwargs):
        return None

    async def _progress(stage: str, progress: int):
        progress_events.append((stage, progress))

    monkeypatch.setattr(service, "_get_chunks", _get_chunks)
    monkeypatch.setattr(service, "_persist_enrichments", _persist_enrichments)
    monkeypatch.setattr(service, "_build_bundles", _build_bundles)
    monkeypatch.setattr(service, "_plan_batches", _plan_batches)
    monkeypatch.setattr(
        service,
        "_upsert_processing_manifest_artifact",
        _upsert_processing_manifest_artifact,
    )
    monkeypatch.setattr(
        service, "_upsert_curriculum_artifact", _upsert_curriculum_artifact
    )
    monkeypatch.setattr(
        "app.services.batched_curriculum_preparation.save_ontology_data",
        _save_ontology_data,
    )

    asyncio.run(
        service.ensure_curriculum_ready(resource_id, progress_callback=_progress)
    )

    stages = [e[0] for e in progress_events]
    assert "batch_planning" in stages
    assert "final_merge_bundles" in stages
    assert "curriculum_finalize" in stages


def test_estimate_tokens():
    service = BatchedCurriculumPreparationService.__new__(
        BatchedCurriculumPreparationService
    )
    assert service._estimate_tokens("hello world") >= 2
    assert service._estimate_tokens("") >= 1


def test_batched_service_resets_curriculum_state_before_rebuild(monkeypatch):
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
    chunk = SimpleNamespace(
        id=uuid4(),
        chunk_index=0,
        text="Chunk text about heat conduction. " * 10,
        section_heading="Conduction",
        page_start=1,
        page_end=1,
        enrichment_metadata={},
        pedagogy_role=None,
        difficulty=None,
    )
    db = _FakeDb(resource)
    service = BatchedCurriculumPreparationService(
        db,
        ontology_extractor=_FakeExtractor(),
        enricher=_FakeEnricher(),
        kb_builder=_FakeKBBuilder(),
        graph_builder=_FakeGraphBuilder(),
    )
    seen = {"reset": 0}

    async def _get_chunks(_resource_id):
        return [chunk]

    async def _reset_curriculum_state(_resource_id):
        assert _resource_id == resource_id
        seen["reset"] += 1

    async def _plan_batches(_resource_id, _chunks):
        return [
            SimpleNamespace(
                id=uuid4(),
                resource_id=_resource_id,
                batch_index=0,
                status="pending",
                chunk_index_start=0,
                chunk_index_end=0,
                section_headings=["Conduction"],
                chunk_ids=[str(chunk.id)],
                token_estimate=100,
                ontology_status="pending",
                enrichment_status="pending",
                kb_merge_status="pending",
                graph_merge_status="pending",
                is_retrieval_ready=False,
                is_study_ready=False,
                concepts_admitted=0,
                graph_edges_created=0,
                ontology_context=None,
                result_json=None,
                error_message=None,
                ontology_completed_at=None,
                enrichment_completed_at=None,
                kb_merge_completed_at=None,
                completed_at=None,
            )
        ]

    async def _persist_enrichments(_chunks, _enrichments):
        return None

    async def _build_bundles(_resource_id):
        return {"bundles_created": 1, "topic_bundles_created": 1}

    async def _upsert_processing_manifest_artifact(**_kwargs):
        return SimpleNamespace(id=uuid4())

    async def _upsert_curriculum_artifact(
        _resource, _kb, _bundle, source_chunk_ids, related_artifact_ids=None
    ):
        return SimpleNamespace(id=uuid4())

    async def _save_ontology_data(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_get_chunks", _get_chunks)
    monkeypatch.setattr(service, "_reset_curriculum_state", _reset_curriculum_state)
    monkeypatch.setattr(service, "_plan_batches", _plan_batches)
    monkeypatch.setattr(service, "_persist_enrichments", _persist_enrichments)
    monkeypatch.setattr(service, "_build_bundles", _build_bundles)
    monkeypatch.setattr(
        service,
        "_upsert_processing_manifest_artifact",
        _upsert_processing_manifest_artifact,
    )
    monkeypatch.setattr(
        service, "_upsert_curriculum_artifact", _upsert_curriculum_artifact
    )
    monkeypatch.setattr(
        "app.services.batched_curriculum_preparation.save_ontology_data",
        _save_ontology_data,
    )

    summary = asyncio.run(service.ensure_curriculum_ready(resource_id))

    assert summary["prepared"] is True
    assert seen["reset"] == 1


def test_batched_service_rebuilds_kb_and_graph_each_batch(monkeypatch):
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
            chunk_index=i,
            text=f"Chunk {i} text about heat conduction in materials. " * 10,
            section_heading="Conduction" if i < 3 else "Radiation",
            page_start=i,
            page_end=i + 1,
            enrichment_metadata={},
            pedagogy_role=None,
            difficulty=None,
        )
        for i in range(6)
    ]
    db = _FakeDb(resource)
    kb_builder = _FakeKBBuilder()
    graph_builder = _FakeGraphBuilder()
    service = BatchedCurriculumPreparationService(
        db,
        ontology_extractor=_FakeExtractor(),
        enricher=_FakeEnricher(),
        kb_builder=kb_builder,
        graph_builder=graph_builder,
        batch_token_target=200,
    )

    async def _get_chunks(_resource_id):
        return chunks

    async def _persist_enrichments(_chunks, _enrichments):
        return None

    async def _build_bundles(_resource_id):
        return {"bundles_created": 2, "topic_bundles_created": 1}

    async def _plan_batches(_resource_id, _chunks):
        batch1 = SimpleNamespace(
            id=uuid4(),
            resource_id=_resource_id,
            batch_index=0,
            status="pending",
            chunk_index_start=0,
            chunk_index_end=2,
            section_headings=["Conduction"],
            chunk_ids=[str(c.id) for c in _chunks[:3]],
            token_estimate=300,
            ontology_status="pending",
            enrichment_status="pending",
            kb_merge_status="pending",
            graph_merge_status="pending",
            is_retrieval_ready=False,
            is_study_ready=False,
            concepts_admitted=0,
            graph_edges_created=0,
            ontology_context=None,
            result_json=None,
            error_message=None,
            ontology_completed_at=None,
            enrichment_completed_at=None,
            kb_merge_completed_at=None,
            completed_at=None,
        )
        batch2 = SimpleNamespace(
            id=uuid4(),
            resource_id=_resource_id,
            batch_index=1,
            status="pending",
            chunk_index_start=3,
            chunk_index_end=5,
            section_headings=["Radiation"],
            chunk_ids=[str(c.id) for c in _chunks[3:]],
            token_estimate=300,
            ontology_status="pending",
            enrichment_status="pending",
            kb_merge_status="pending",
            graph_merge_status="pending",
            is_retrieval_ready=False,
            is_study_ready=False,
            concepts_admitted=0,
            graph_edges_created=0,
            ontology_context=None,
            result_json=None,
            error_message=None,
            ontology_completed_at=None,
            enrichment_completed_at=None,
            kb_merge_completed_at=None,
            completed_at=None,
        )
        return [batch1, batch2]

    async def _upsert_processing_manifest_artifact(**_kwargs):
        return SimpleNamespace(id=uuid4())

    async def _upsert_curriculum_artifact(
        _resource, _kb, _bundle, source_chunk_ids, related_artifact_ids=None
    ):
        return SimpleNamespace(id=uuid4())

    async def _save_ontology_data(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_get_chunks", _get_chunks)
    monkeypatch.setattr(service, "_persist_enrichments", _persist_enrichments)
    monkeypatch.setattr(service, "_build_bundles", _build_bundles)
    monkeypatch.setattr(service, "_plan_batches", _plan_batches)
    monkeypatch.setattr(
        service,
        "_upsert_processing_manifest_artifact",
        _upsert_processing_manifest_artifact,
    )
    monkeypatch.setattr(
        service, "_upsert_curriculum_artifact", _upsert_curriculum_artifact
    )
    monkeypatch.setattr(
        "app.services.batched_curriculum_preparation.save_ontology_data",
        _save_ontology_data,
    )

    summary = asyncio.run(service.ensure_curriculum_ready(resource_id))

    assert summary["prepared"] is True
    assert all(call["kwargs"].get("force_rebuild") is True for call in kb_builder.calls)
    assert all(
        call["kwargs"].get("force_rebuild") is True for call in graph_builder.calls
    )


def test_batched_persist_enrichments_updates_child_sub_chunks():
    parent_chunk = SimpleNamespace(
        id=uuid4(),
        chunk_index=0,
        text="Conduction transfers heat through matter.",
        section_heading="Conduction",
        page_start=1,
        page_end=1,
        enrichment_metadata={"docling": {"source": "docling_hybrid"}},
        pedagogy_role=None,
        difficulty=None,
    )
    child_sub_chunk = SimpleNamespace(
        parent_chunk_id=parent_chunk.id,
        enrichment_metadata={"metadata_level": "core_lightweight"},
    )

    class _DbWithSubChunks:
        def __init__(self):
            self.added = []
            self.deleted = []

        async def execute(self, stmt):
            stmt_text = str(stmt)
            if "DELETE FROM chunk_concept" in stmt_text:
                self.deleted.append(stmt_text)
                return _FakeResult([])
            if "FROM sub_chunk" in stmt_text:
                return _FakeResult([child_sub_chunk])
            return _FakeResult([])

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

    service = BatchedCurriculumPreparationService(
        _DbWithSubChunks(),
        ontology_extractor=_FakeExtractor(),
        enricher=_FakeEnricher(),
        kb_builder=_FakeKBBuilder(),
        graph_builder=_FakeGraphBuilder(),
    )

    enrichment = {
        "concepts_taught": ["Conduction"],
        "concepts_mentioned": ["Heat"],
        "pedagogy_role": "explanation",
        "difficulty": "intermediate",
        "prereq_hints": [],
        "semantic_relationships": [],
    }

    asyncio.run(service._persist_enrichments([parent_chunk], [enrichment]))

    assert parent_chunk.enrichment_metadata["metadata_level"] == "curriculum_prepare"
    assert parent_chunk.enrichment_metadata["docling"]["source"] == "docling_hybrid"
    assert child_sub_chunk.enrichment_metadata["metadata_level"] == "curriculum_prepare"
    assert child_sub_chunk.enrichment_metadata["concepts_taught"] == ["Conduction"]
