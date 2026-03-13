from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Maximum concepts to extract per chunk to reduce noise
MAX_CONCEPTS_TAUGHT = 5
MAX_CONCEPTS_MENTIONED = 5
MAX_RELATIONSHIPS = 8

# Valid concept types for ontological classification
CONCEPT_TYPES = [
    "principle",
    "formula",
    "technique",
    "entity",
    "process",
    "property",
    "law",
    "theorem",
    "function",
    "concept",
    "definition",
    "method",
    "algorithm",
    "rule",
    "pattern",
    "model",
    "system",
    "structure",
    "operation",
    "variable",
    "constant",
    "parameter",
    "condition",
]

# Valid relationship types for knowledge graph edges
RELATIONSHIP_TYPES = [
    "REQUIRES",
    "IS_A",
    "PART_OF",
    "APPLIES_TO",
    "RELATED_TO",
    "DERIVES_FROM",
    "ENABLES",
    "HAS_PART",
    "ENABLED_BY",
    "PREREQUISITE_FOR",
    "INSTANCE_OF",
    "SUBCLASS_OF",
    "COMPOSED_OF",
    "COMPONENT_OF",
    "USES",
    "USED_BY",
    "SIMILAR_TO",
    "OPPOSITE_OF",
]

# Bloom's taxonomy levels for pedagogical sequencing
BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]


class ConceptMetadataSchema(BaseModel):
    """Schema for rich concept metadata with ontological classification."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Concept name in lowercase with spaces")
    concept_type: Literal[
        "principle",
        "formula",
        "technique",
        "entity",
        "process",
        "property",
        "law",
        "theorem",
        "function",
        "concept",
        "definition",
        "method",
        "algorithm",
        "rule",
        "pattern",
        "model",
        "system",
        "structure",
        "operation",
        "variable",
        "constant",
        "parameter",
        "condition",
    ] = Field(
        default="principle",
        description="Ontological type of the concept",
    )
    bloom_level: Literal[
        "remember", "understand", "apply", "analyze", "evaluate", "create"
    ] = Field(
        default="understand",
        description="Bloom's taxonomy level for this concept in this chunk",
    )
    importance: Literal["core", "supporting", "peripheral"] = Field(
        default="core",
        description="How central this concept is to the chunk's teaching",
    )


class SemanticRelationshipSchema(BaseModel):
    """Schema for typed semantic relationships between concepts."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Source concept name")
    target: str = Field(..., description="Target concept name")
    relation_type: Literal[
        "REQUIRES",
        "IS_A",
        "PART_OF",
        "APPLIES_TO",
        "RELATED_TO",
        "DERIVES_FROM",
        "ENABLES",
        "HAS_PART",
        "ENABLED_BY",
        "PREREQUISITE_FOR",
        "INSTANCE_OF",
        "SUBCLASS_OF",
        "COMPOSED_OF",
        "COMPONENT_OF",
        "USES",
        "USED_BY",
        "SIMILAR_TO",
        "OPPOSITE_OF",
    ] = Field(..., description="Type of semantic relationship")
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence in this relationship (0-1)",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Brief text evidence supporting this relationship",
    )


class PrereqHintSchema(BaseModel):
    """Schema for prerequisite hints (backward compatible)."""

    model_config = ConfigDict(extra="forbid")

    source_concept: str = Field(
        ..., description="Concept that requires the prerequisite"
    )
    target_concept: str = Field(..., description="Prerequisite concept")
    confidence: Optional[float] = Field(default=0.8, ge=0.0, le=1.0)


class EnrichmentResponseSchema(BaseModel):
    """Enhanced schema for LLM enrichment with ontological structure."""

    model_config = ConfigDict(extra="forbid")

    concepts_taught: list[ConceptMetadataSchema] = Field(
        default_factory=list,
        description="Main concepts directly taught with full metadata (max 5)",
    )
    concepts_mentioned: list[str] = Field(
        default_factory=list,
        description="Concepts referenced but not taught (max 5)",
    )
    semantic_relationships: list[SemanticRelationshipSchema] = Field(
        default_factory=list,
        description="Typed semantic relationships between concepts",
    )
    pedagogy_role: Literal[
        "definition",
        "explanation",
        "example",
        "exercise",
        "summary",
        "derivation",
        "proof",
    ] = Field(
        default="explanation",
        description="Pedagogical role of this chunk",
    )
    difficulty: Literal["beginner", "intermediate", "advanced"] = Field(
        default="intermediate",
        description="Difficulty level of the content",
    )
    quality_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Quality rating 0-1 for how well it explains concepts",
    )
    learning_sequence_hint: list[str] = Field(
        default_factory=list,
        description="Suggested order for learning the taught concepts",
    )

    @field_validator("concepts_taught", mode="before")
    @classmethod
    def limit_concepts_taught(cls, value):
        if isinstance(value, list):
            return value[:MAX_CONCEPTS_TAUGHT]
        return value

    @field_validator("concepts_mentioned", mode="before")
    @classmethod
    def limit_concepts_mentioned(cls, value):
        if isinstance(value, list):
            return value[:MAX_CONCEPTS_MENTIONED]
        return value

    @field_validator("semantic_relationships", mode="before")
    @classmethod
    def limit_relationships(cls, value):
        if isinstance(value, list):
            return value[:MAX_RELATIONSHIPS]
        return value
