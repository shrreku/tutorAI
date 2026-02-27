import asyncio
import uuid
from types import SimpleNamespace

from app.services.ingestion.graph_builder import ConceptGraphBuilder, _score_ontology_relation
from app.services.ingestion.kb_builder import ResourceKBBuilder
from app.services.ingestion.ontology_extractor import OntologyExtractor
from app.services.ingestion.ontology_schemas import OntologyWindowResponse


class _FakeDB:
    def __init__(self):
        self.rows = []

    def add_all(self, rows):
        self.rows.extend(rows)

    async def flush(self):
        return None


def test_ontology_relation_scoring_boosts_confidence_with_evidence_fields():
    confidence, score_details = _score_ontology_relation(
        {
            "confidence": 0.75,
            "evidence_quote": "Conduction requires a gradient.",
            "page_range": "2",
            "section_heading": "Conduction",
        }
    )

    assert confidence > 0.75
    assert score_details["base_confidence"] == 0.75
    assert score_details["evidence_boost"] > 0
    assert all(score_details["evidence_fields"].values())


def test_graph_builder_seeds_ontology_relation_edges_with_evidence_weighting(monkeypatch):
    db = _FakeDB()
    builder = ConceptGraphBuilder(db)

    async def _fake_get_evidence(self, resource_id):
        return [
            SimpleNamespace(
                concept_id="temperature",
                chunk_id=uuid.uuid4(),
                weight=1.0,
                quality_score=0.9,
            ),
            SimpleNamespace(
                concept_id="conduction",
                chunk_id=uuid.uuid4(),
                weight=1.0,
                quality_score=0.85,
            ),
        ]

    async def _fake_get_chunks(self, resource_id):
        return [SimpleNamespace(enrichment_metadata={"semantic_relationships": []})]

    async def _fake_get_prereq_lookup(self, resource_id):
        return {}

    monkeypatch.setattr(ConceptGraphBuilder, "_get_evidence", _fake_get_evidence)
    monkeypatch.setattr(ConceptGraphBuilder, "_get_chunks_with_enrichment", _fake_get_chunks)
    monkeypatch.setattr(ConceptGraphBuilder, "_get_prereq_lookup", _fake_get_prereq_lookup)

    result = asyncio.run(
        builder.build(
            resource_id=uuid.uuid4(),
            top_k=0,
            min_similarity=1.1,
            force_rebuild=False,
            ontology_relations=[
                {
                    "source_concept": "temperature",
                    "target_concept": "conduction",
                    "relation_type": "REQUIRES",
                    "confidence": 0.8,
                    "evidence_quote": "Conduction requires a temperature gradient.",
                    "page_range": "1-2",
                    "section_heading": "Conduction",
                }
            ],
        )
    )

    assert result["ontology_edges_seeded"] == 1
    assert result["ontology_edges_boosted"] == 0
    assert len(db.rows) == 1
    edge = db.rows[0]
    assert edge.source == "ontology_relation"
    assert edge.relation_type == "REQUIRES"
    assert edge.confidence > 0.8


def test_ontology_merge_dedups_semantic_relations_with_evidence_scope():
    extractor = OntologyExtractor(llm_provider=None)

    w1 = OntologyWindowResponse(
        semantic_relations=[
            {
                "source_concept": "temperature",
                "target_concept": "conduction",
                "relation_type": "REQUIRES",
                "evidence_quote": "Conduction requires temperature gradient.",
                "page_range": "2",
                "section_heading": "Conduction",
                "confidence": 0.9,
            }
        ]
    )
    w2 = OntologyWindowResponse(
        semantic_relations=[
            {
                "source_concept": "temperature",
                "target_concept": "conduction",
                "relation_type": "REQUIRES",
                "evidence_quote": "Conduction requires temperature gradient.",
                "page_range": "2",
                "section_heading": "Conduction",
                "confidence": 0.8,
            },
            {
                "source_concept": "conduction",
                "target_concept": "heat_transfer",
                "relation_type": "PART_OF",
                "evidence_quote": "Conduction is a mode of heat transfer.",
                "page_range": "3",
                "section_heading": "Heat Transfer Modes",
                "confidence": 0.85,
            },
        ]
    )

    merged = asyncio.run(extractor._merge_results([w1, w2], sections=[]))

    assert len(merged.semantic_relations) == 2
    assert {r["relation_type"] for r in merged.semantic_relations} == {"REQUIRES", "PART_OF"}


def test_kb_builder_prereq_hints_include_ontology_relation_evidence():
    db = _FakeDB()
    builder = ResourceKBBuilder(db)

    enrichments = [
        {
            "prereq_hints": [
                {
                    "source_concept": "heat_transfer",
                    "target_concept": "conduction",
                    "relation_type": "REQUIRES",
                    "confidence": 0.8,
                }
            ]
        }
    ]
    ontology_relations = [
        {
            "source_concept": "Heat Transfer",
            "target_concept": "Conduction",
            "relation_type": "REQUIRES",
            "confidence": 0.92,
            "evidence_quote": "Heat transfer requires understanding conduction.",
            "page_range": "1-2",
            "section_heading": "Introduction",
        }
    ]

    count = asyncio.run(
        builder._build_prereq_hints(
            resource_id=uuid.uuid4(),
            enrichments=enrichments,
            admitted={"heat_transfer", "conduction"},
            ontology_relations=ontology_relations,
        )
    )

    assert count == 1
    assert len(db.rows) == 1
    row = db.rows[0]
    assert row.support_count == 2
    assert row.sources and "evidence" in row.sources
    sources = row.sources["evidence"]
    assert {s["source"] for s in sources} == {"chunk_enrichment", "ontology_relation"}
