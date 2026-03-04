import pytest
from pydantic import ValidationError

from app.schemas.api import (
    KnowledgeBaseConceptOverride,
    KnowledgeBaseTopicBundleUpdate,
    KnowledgeBaseUpdateRequest,
)


def test_kb_concept_override_validates_required_concept_id():
    payload = KnowledgeBaseConceptOverride(
        concept_id="newton_second_law",
        concept_type="principle",
        bloom_level="apply",
        importance_score=0.85,
        topo_order=2,
    )

    assert payload.concept_id == "newton_second_law"
    assert payload.importance_score == 0.85


def test_kb_concept_override_rejects_empty_concept_id():
    with pytest.raises(ValidationError):
        KnowledgeBaseConceptOverride(concept_id="")


def test_kb_topic_bundle_update_defaults_lists():
    payload = KnowledgeBaseTopicBundleUpdate(topic_id="forces", topic_name="Forces")

    assert payload.primary_concepts == []
    assert payload.support_concepts == []
    assert payload.prereq_topic_ids == []


def test_kb_update_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        KnowledgeBaseUpdateRequest(
            topic="Mechanics",
            concept_overrides=[],
            unknown_field="nope",
        )
