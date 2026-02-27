from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TopicNode(BaseModel):
    """A topic with optional subtopics."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Topic name")
    subtopics: list[str] = Field(default_factory=list, description="Child subtopics")
    importance: Literal["primary", "secondary", "tertiary"] = Field(
        default="primary",
        description="Importance level of this topic",
    )


class LearningObjective(BaseModel):
    """A learning objective with Bloom's level."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(..., description="What the learner should be able to do")
    bloom_level: Literal["remember", "understand", "apply", "analyze", "evaluate", "create"] = Field(
        default="understand",
        description="Bloom's taxonomy level",
    )
    related_concepts: list[str] = Field(
        default_factory=list,
        description="Concepts this objective covers",
    )
    specificity: Literal["course_level", "chapter_level", "section_level"] = Field(
        default="section_level",
        description="Granularity level of this objective",
    )


class PrerequisiteConcept(BaseModel):
    """A prerequisite concept assumed by the content."""

    model_config = ConfigDict(extra="forbid")

    concept: str = Field(..., description="Prerequisite concept name")
    domain: Optional[str] = Field(default=None, description="Domain/subject area")
    importance: Literal["essential", "helpful", "optional"] = Field(
        default="essential",
        description="How important this prerequisite is",
    )


class ConceptTaxonomyItem(BaseModel):
    """A concept with its taxonomic position."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Concept name")
    concept_type: str = Field(
        default="concept",
        description=(
            "Type of concept (e.g., principle, formula, technique, entity, "
            "process, property, law, theorem, definition, method, system, "
            "function, concept, object, model, algorithm)"
        ),
    )
    parent_concept: Optional[str] = Field(
        default=None,
        description="Parent concept in the taxonomy",
    )
    related_concepts: list[str] = Field(
        default_factory=list,
        description="Related concepts at the same level",
    )


class TermDefinition(BaseModel):
    """A key term and its definition."""

    model_config = ConfigDict(extra="forbid")

    term: str = Field(..., description="The term")
    definition: str = Field(..., description="Brief definition")
    context: Optional[str] = Field(default=None, description="Context where this term applies")


class OntologySemanticRelation(BaseModel):
    """Document-level semantic relation with traceable evidence."""

    model_config = ConfigDict(extra="forbid")

    source_concept: str = Field(..., description="Source concept name")
    target_concept: str = Field(..., description="Target concept name")
    relation_type: Literal[
        "REQUIRES",
        "ENABLES",
        "IS_A",
        "PART_OF",
        "EQUIVALENT_TO",
        "DERIVES_FROM",
        "CONTRASTS_WITH",
    ] = Field(..., description="Typed semantic relation")
    evidence_quote: Optional[str] = Field(
        default=None,
        description="Short quoted snippet supporting the relation",
    )
    page_range: Optional[str] = Field(
        default=None,
        description="Source page range, e.g. '3-4'",
    )
    section_heading: Optional[str] = Field(
        default=None,
        description="Nearest section heading for relation evidence",
    )
    confidence: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence score for this relation",
    )


class OntologyWindowResponse(BaseModel):
    """Response schema for a single ontology extraction window."""

    model_config = ConfigDict(extra="forbid")

    main_topics: list[TopicNode] = Field(
        default_factory=list,
        description="Main topics with subtopics (max 5)",
    )
    learning_objectives: list[LearningObjective] = Field(
        default_factory=list,
        description="Learning objectives (max 8)",
    )
    prerequisites: list[PrerequisiteConcept] = Field(
        default_factory=list,
        description="Prerequisite concepts assumed (max 10)",
    )
    concept_taxonomy: list[ConceptTaxonomyItem] = Field(
        default_factory=list,
        description="Key concepts with taxonomy (max 15)",
    )
    terminology: list[TermDefinition] = Field(
        default_factory=list,
        description="Key terms and definitions (max 10)",
    )
    semantic_relations: list[OntologySemanticRelation] = Field(
        default_factory=list,
        description="Typed relation inventory with evidence (max 20)",
    )
    content_summary: str = Field(
        default="",
        description="One-sentence summary of this content section",
    )

    @field_validator("main_topics", mode="before")
    @classmethod
    def limit_topics(cls, value):
        return value[:5] if isinstance(value, list) else value

    @field_validator("learning_objectives", mode="before")
    @classmethod
    def limit_objectives(cls, value):
        return value[:8] if isinstance(value, list) else value

    @field_validator("prerequisites", mode="before")
    @classmethod
    def limit_prereqs(cls, value):
        return value[:10] if isinstance(value, list) else value

    @field_validator("concept_taxonomy", mode="before")
    @classmethod
    def limit_concepts(cls, value):
        return value[:15] if isinstance(value, list) else value

    @field_validator("terminology", mode="before")
    @classmethod
    def limit_terms(cls, value):
        return value[:10] if isinstance(value, list) else value

    @field_validator("semantic_relations", mode="before")
    @classmethod
    def limit_relations(cls, value):
        return value[:20] if isinstance(value, list) else value
