from types import SimpleNamespace

from app.services.topic_preparation import build_topic_preparation_artifact


def test_build_topic_preparation_artifact_selects_relevant_chunks_for_mode():
    chunks = [
        SimpleNamespace(
            id="c1",
            text="Definition: Conduction is heat transfer through matter.",
            section_heading="Conduction Basics",
            pedagogy_role="definition",
            chunk_index=0,
        ),
        SimpleNamespace(
            id="c2",
            text="Example: A metal rod transfers heat faster than wood.",
            section_heading="Conduction Examples",
            pedagogy_role="example",
            chunk_index=1,
        ),
        SimpleNamespace(
            id="c3",
            text="Exercise: Compute heat flux using Fourier law.",
            section_heading="Practice Problems",
            pedagogy_role="exercise",
            chunk_index=2,
        ),
    ]

    artifact = build_topic_preparation_artifact(
        mode="practice",
        topic="conduction",
        selected_topics=["heat transfer"],
        resource_profile={
            "document_type": "study_notes",
            "topic_seeds": ["conduction", "heat"],
        },
        chunks=chunks,
    )

    assert artifact["artifact_kind"] == "topic_prepare"
    assert artifact["mode"] == "practice"
    assert artifact["focus_terms"]
    assert artifact["chunk_count_selected"] >= 1
    assert "c3" in artifact["selected_chunk_ids"]
    assert artifact["document_type"] == "study_notes"
    assert artifact["content_hash"]
