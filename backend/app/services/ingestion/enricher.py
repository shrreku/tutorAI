"""
Chunk Enrichment Service - TICKET-014

LLM-based enrichment to extract concepts and metadata from chunks.
"""
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from langfuse import observe

from app.prompts.ingestion.enrichment import (
    ENRICHMENT_SYSTEM_PROMPT_BASE,
    ONTOLOGY_CONTEXT_TEMPLATE,
)
from app.services.ingestion.enrichment_schemas import (
    BLOOM_LEVELS,
    CONCEPT_TYPES,
    RELATIONSHIP_TYPES,
    EnrichmentResponseSchema,
)
from app.services.llm.base import BaseLLMProvider
from app.services.ingestion.ingestion_types import ChunkData, token_len
from app.utils.canonicalization import ConceptIdRegistry

logger = logging.getLogger(__name__)

# Chunk quality thresholds for filtering
MIN_CHUNK_TOKENS = 50  # Skip chunks below this
MAX_NOISE_RATIO = 0.6  # Skip if >60% non-alphanumeric
NOISY_PATTERNS = [
    r'^\s*table\s+of\s+contents',
    r'^\s*index\s*$',
    r'^\s*references\s*$',
    r'^\s*bibliography\s*$',
    r'^\s*appendix\s+[a-z]?\s*$',
    r'^\s*figure\s+\d+',
    r'^\s*table\s+\d+',
    r'^\d+\s*$',  # Just page numbers
]


@dataclass
class ChunkQualityInfo:
    """Quality assessment for a chunk."""
    should_enrich: bool = True
    skip_reason: Optional[str] = None
    token_count: int = 0
    noise_ratio: float = 0.0
    is_structural: bool = False  # TOC, index, etc.


@dataclass
class ChunkEnrichment:
    """Enhanced enrichment data with ontological structure."""
    concepts_taught: list[str] = field(default_factory=list)
    concepts_mentioned: list[str] = field(default_factory=list)
    concept_metadata: list[dict] = field(default_factory=list)
    semantic_relationships: list[dict] = field(default_factory=list)
    pedagogy_role: str = "explanation"
    difficulty: str = "intermediate"
    quality_score: float = 0.5
    learning_sequence: list[str] = field(default_factory=list)
    prereq_hints: list[dict] = field(default_factory=list)
    raw_concept_names: dict = field(default_factory=dict)
    error: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class ChunkEnricher:
    """Enriches chunks with concept extraction and metadata using LLM."""
    
    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        min_tokens: int = MIN_CHUNK_TOKENS,
        max_noise_ratio: float = MAX_NOISE_RATIO,
        enrichment_model: str | None = None,
    ):
        self.llm = llm_provider
        self.concept_registry = ConceptIdRegistry()
        self.min_tokens = min_tokens
        self.max_noise_ratio = max_noise_ratio
        self.enrichment_model = enrichment_model
    
    def assess_chunk_quality(self, chunk: ChunkData) -> ChunkQualityInfo:
        """
        Assess whether a chunk should be enriched.
        
        Returns ChunkQualityInfo with should_enrich=False for:
        - Very small chunks (< min_tokens)
        - High noise ratio (tables, formulas without context)
        - Structural content (TOC, index, references)
        """
        import re
        
        text = chunk.text.strip()
        tokens = token_len(text)
        
        # Check minimum size
        if tokens < self.min_tokens:
            return ChunkQualityInfo(
                should_enrich=False,
                skip_reason=f"too_small ({tokens} tokens)",
                token_count=tokens,
            )
        
        # Check noise ratio (non-alphanumeric characters)
        alphanumeric = sum(1 for c in text if c.isalnum() or c.isspace())
        total = len(text)
        noise_ratio = 1 - (alphanumeric / total) if total > 0 else 0
        
        if noise_ratio > self.max_noise_ratio:
            return ChunkQualityInfo(
                should_enrich=False,
                skip_reason=f"high_noise ({noise_ratio:.2f})",
                token_count=tokens,
                noise_ratio=noise_ratio,
            )
        
        # Check for structural/noisy patterns
        text_lower = text.lower()
        for pattern in NOISY_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return ChunkQualityInfo(
                    should_enrich=False,
                    skip_reason="structural_content",
                    token_count=tokens,
                    is_structural=True,
                )
        
        return ChunkQualityInfo(
            should_enrich=True,
            token_count=tokens,
            noise_ratio=noise_ratio,
        )
    
    @observe(name="chunk-enrichment-batch", capture_input=False)
    async def enrich_batch(
        self,
        chunks: list[ChunkData],
        context_window: int = 1,
        ontology_context: Optional[str] = None,
    ) -> list[ChunkEnrichment]:
        """
        Enrich a batch of chunks with concept extraction.
        
        Args:
            chunks: List of chunks to enrich
            context_window: Number of neighboring chunks to include for context
            ontology_context: Optional document-level ontology context string
            
        Returns:
            List of enrichments corresponding to each chunk
        """
        results = []
        enriched_count = 0
        skipped_count = 0
        error_count = 0
        total_chunks = len(chunks)
        total_concepts_taught = 0
        total_concepts_mentioned = 0
        
        logger.info(f"[ENRICHMENT] Starting enrichment of {total_chunks} chunks")
        if ontology_context:
            logger.info(f"[ENRICHMENT] Using ontology context ({len(ontology_context)} chars)")
        
        # Log progress every N chunks
        log_interval = max(1, total_chunks // 10)  # ~10 progress updates
        
        for i, chunk in enumerate(chunks):
            # Assess chunk quality first
            quality = self.assess_chunk_quality(chunk)
            
            if not quality.should_enrich:
                # Skip low-quality chunks
                results.append(ChunkEnrichment(
                    skipped=True,
                    skip_reason=quality.skip_reason,
                    quality_score=0.1,  # Low score for skipped
                ))
                skipped_count += 1
                if (i + 1) % log_interval == 0 or i == total_chunks - 1:
                    logger.info(
                        f"[ENRICHMENT] Progress: {i+1}/{total_chunks} "
                        f"(enriched: {enriched_count}, skipped: {skipped_count})"
                    )
                continue
            
            # Get full neighbor chunks (no truncation)
            prev_chunk = chunks[i-1] if i > 0 else None
            next_chunk = chunks[i+1] if i < len(chunks) - 1 else None
            
            try:
                enrichment = await self._enrich_single(
                    chunk, prev_chunk, next_chunk, ontology_context
                )
                results.append(enrichment)
                enriched_count += 1
                total_concepts_taught += len(enrichment.concepts_taught)
                total_concepts_mentioned += len(enrichment.concepts_mentioned)
            except Exception as e:
                logger.warning(f"[ENRICHMENT] Chunk {i+1} failed: {e}")
                results.append(ChunkEnrichment(error=str(e)))
                error_count += 1
            
            # Log progress
            if (i + 1) % log_interval == 0 or i == total_chunks - 1:
                logger.info(
                    f"[ENRICHMENT] Progress: {i+1}/{total_chunks} "
                    f"(enriched: {enriched_count}, skipped: {skipped_count}, errors: {error_count})"
                )
        
        logger.info(
            f"[ENRICHMENT] ✓ Complete: {enriched_count}/{total_chunks} enriched, "
            f"{skipped_count} skipped, {error_count} errors"
        )
        logger.info(
            f"[ENRICHMENT] Concepts extracted: {total_concepts_taught} taught, "
            f"{total_concepts_mentioned} mentioned"
        )
        return results
    
    async def _enrich_single(
        self,
        chunk: ChunkData,
        prev_chunk: Optional[ChunkData],
        next_chunk: Optional[ChunkData],
        ontology_context: Optional[str] = None,
    ) -> ChunkEnrichment:
        """Enrich a single chunk with ontological and pedagogical metadata."""
        # Build system prompt with optional ontology context
        system_prompt = ENRICHMENT_SYSTEM_PROMPT_BASE
        if ontology_context:
            system_prompt += ONTOLOGY_CONTEXT_TEMPLATE.format(
                ontology_context=ontology_context
            )
        
        # Build user message with full context (no truncation)
        context_parts = []
        if prev_chunk:
            context_parts.append(f"[PREVIOUS CHUNK]\n{prev_chunk.text}\n")
        context_parts.append(f"[MAIN CHUNK \u2014 ANALYZE THIS]\n{chunk.text}\n")
        if next_chunk:
            context_parts.append(f"[NEXT CHUNK]\n{next_chunk.text}")
        
        user_message = "\n".join(context_parts)
        
        if chunk.section_heading:
            user_message = f"Section: {chunk.section_heading}\n\n{user_message}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        
        # Call LLM with configurable output tokens and per-task model
        from app.config import settings
        try:
            enrichment_response = await self.llm.generate_json(
                messages=messages,
                schema=EnrichmentResponseSchema,
                temperature=0.3,
                max_tokens=settings.ENRICHMENT_MAX_OUTPUT_TOKENS,
                model=self.enrichment_model,
            )
            
            # Convert to dict for processing
            enrichment_data = enrichment_response.model_dump()
            
            # Canonicalize concepts and track raw names + metadata
            raw_names = {}
            concept_metadata = []
            
            # Process concepts_taught (now contains full metadata)
            canonical_taught = []
            for concept_obj in enrichment_data.get("concepts_taught", []):
                if isinstance(concept_obj, dict):
                    raw_name = concept_obj.get("name", "")
                else:
                    raw_name = str(concept_obj)
                    concept_obj = {"name": raw_name}
                
                canonical_id = self.concept_registry.register(raw_name)
                if canonical_id:
                    canonical_taught.append(canonical_id)
                    if canonical_id not in raw_names:
                        raw_names[canonical_id] = []
                    raw_names[canonical_id].append(raw_name)
                    
                    # Store rich metadata
                    concept_metadata.append({
                        "concept_id": canonical_id,
                        "raw_name": raw_name,
                        "concept_type": self._validate_concept_type(concept_obj.get("concept_type", "principle")),
                        "bloom_level": self._validate_bloom_level(concept_obj.get("bloom_level", "understand")),
                        "importance": concept_obj.get("importance", "core"),
                    })
            
            # Process concepts_mentioned (simple strings)
            canonical_mentioned = []
            for raw_name in enrichment_data.get("concepts_mentioned", []):
                if isinstance(raw_name, dict):
                    raw_name = raw_name.get("name", str(raw_name))
                canonical_id = self.concept_registry.register(raw_name)
                if canonical_id:
                    canonical_mentioned.append(canonical_id)
                    if canonical_id not in raw_names:
                        raw_names[canonical_id] = []
                    raw_names[canonical_id].append(raw_name)
            
            # Process semantic relationships (new ontological structure)
            semantic_relationships = []
            prereq_hints = []
            for rel in enrichment_data.get("semantic_relationships", []):
                if isinstance(rel, dict) and "source" in rel and "target" in rel:
                    source_id = self.concept_registry.register(rel["source"])
                    target_id = self.concept_registry.register(rel["target"])
                    rel_type = rel.get("relation_type", "RELATED_TO")
                    confidence = rel.get("confidence", 0.8)
                    
                    if source_id and target_id:
                        semantic_relationships.append({
                            "source_id": source_id,
                            "target_id": target_id,
                            "relation_type": self._validate_relation_type(rel_type),
                            "confidence": min(1.0, max(0.0, confidence)),
                            "evidence": rel.get("evidence"),
                        })
                        
                        # Extract prereq hints from REQUIRES and ENABLES relationships
                        if rel_type in ("REQUIRES", "ENABLES", "DERIVES_FROM"):
                            prereq_hints.append({
                                "source_concept": source_id,
                                "target_concept": target_id,
                                "confidence": confidence,
                                "relation_type": rel_type,
                            })
            
            # Process learning sequence hint
            learning_sequence = []
            for raw_name in enrichment_data.get("learning_sequence_hint", []):
                canonical_id = self.concept_registry.register(raw_name)
                if canonical_id:
                    learning_sequence.append(canonical_id)
            
            return ChunkEnrichment(
                concepts_taught=canonical_taught,
                concepts_mentioned=canonical_mentioned,
                concept_metadata=concept_metadata,
                semantic_relationships=semantic_relationships,
                pedagogy_role=self._validate_pedagogy_role(enrichment_data.get("pedagogy_role", "explanation")),
                difficulty=self._validate_difficulty(enrichment_data.get("difficulty", "intermediate")),
                quality_score=self._validate_quality_score(enrichment_data.get("quality_score", 0.5)),
                learning_sequence=learning_sequence,
                prereq_hints=prereq_hints,
                raw_concept_names=raw_names,
            )
            
        except Exception as e:
            logger.warning(f"LLM enrichment failed: {e}")
            return ChunkEnrichment(error=str(e))
    
    def _validate_pedagogy_role(self, role: str) -> str:
        """Validate and normalize pedagogy role."""
        valid_roles = {"definition", "explanation", "example", "exercise", "summary", "derivation", "proof"}
        role = role.lower().strip()
        return role if role in valid_roles else "explanation"
    
    def _validate_difficulty(self, difficulty: str) -> str:
        """Validate and normalize difficulty."""
        valid_difficulties = {"beginner", "intermediate", "advanced"}
        difficulty = difficulty.lower().strip()
        return difficulty if difficulty in valid_difficulties else "intermediate"
    
    def _validate_quality_score(self, score) -> float:
        """Validate and clamp quality score to [0, 1]."""
        try:
            score = float(score)
            return max(0.0, min(1.0, score))
        except (TypeError, ValueError):
            return 0.5
    
    def _validate_concept_type(self, concept_type: str) -> str:
        """Validate and normalize concept type."""
        valid_types = set(CONCEPT_TYPES)
        concept_type = concept_type.lower().strip()
        return concept_type if concept_type in valid_types else "principle"
    
    def _validate_bloom_level(self, bloom_level: str) -> str:
        """Validate and normalize Bloom's taxonomy level."""
        valid_levels = set(BLOOM_LEVELS)
        bloom_level = bloom_level.lower().strip()
        return bloom_level if bloom_level in valid_levels else "understand"
    
    def _validate_relation_type(self, relation_type: str) -> str:
        """Validate and normalize semantic relationship type."""
        valid_types = set(RELATIONSHIP_TYPES)
        relation_type = relation_type.upper().strip()
        return relation_type if relation_type in valid_types else "RELATED_TO"
    
    def get_collisions(self) -> dict:
        """Get all concept ID collisions detected during enrichment."""
        return self.concept_registry.get_collisions()
