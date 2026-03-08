from types import SimpleNamespace

from app.services.ingestion.resource_profile import build_resource_profile


def test_build_resource_profile_creates_lightweight_understanding_artifact():
    sections = [
        {"heading": "Heat Transfer Basics", "text": "Intro"},
        {"heading": "Conduction Examples", "text": "Worked examples"},
    ]
    chunks = [
        SimpleNamespace(
            text="Definition: Conduction transfers heat through a material. Example problems follow.",
            page_start=1,
            page_end=1,
        ),
        SimpleNamespace(
            text="Exercise: Apply Fourier law to estimate heat flux in a rod.",
            page_start=2,
            page_end=2,
        ),
    ]

    profile = build_resource_profile(
        filename="heat-transfer-notes.pdf",
        topic="physics",
        sections=sections,
        chunks=chunks,
        chunking_metadata={"embedding_strategy": "contextualized"},
    )

    assert profile["artifact_kind"] == "resource_profile"
    assert profile["document_type"] == "study_notes"
    assert profile["section_count"] == 2
    assert profile["chunk_count"] == 2
    assert "Heat Transfer Basics" in profile["section_headings"]
    assert "conduction" in profile["topic_seeds"]
    assert profile["pedagogy_signals"]["definition"] == 1
    assert profile["pedagogy_signals"]["exercise"] == 1
    assert profile["page_span"] == {"start": 1, "end": 2}
    assert profile["content_hash"]
