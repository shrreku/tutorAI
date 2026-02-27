"""
Ontology Extractor - High-level document ontology extraction.

Performs a rolling scan of the document to extract:
- Main topics and subtopics
- Learning objectives
- Prerequisite concepts (external knowledge assumed)
- Key terminology and definitions
- Concept taxonomy (how concepts relate hierarchically)

This ontological context is used to guide chunk enrichment for better
pedagogical accuracy and consistency.
"""
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from langfuse import observe

from app.prompts.ingestion.ontology import ONTOLOGY_SYSTEM_PROMPT
from app.services.llm.base import BaseLLMProvider
from app.services.ingestion.ingestion_types import SectionData, token_len
from app.services.ingestion.ontology_schemas import OntologyWindowResponse

logger = logging.getLogger(__name__)

# Token-based extraction configuration
DEFAULT_MAX_TOKENS_PER_CALL = 100_000  # 100K input token budget per LLM call
DEFAULT_OVERLAP_TOKENS = 5_000         # 5K token overlap between batches


@dataclass
class ResourceOntology:
    """Aggregated ontology for an entire resource."""
    main_topics: list[dict] = field(default_factory=list)
    learning_objectives: list[dict] = field(default_factory=list)
    prerequisites: list[dict] = field(default_factory=list)
    concept_taxonomy: list[dict] = field(default_factory=list)
    terminology: list[dict] = field(default_factory=list)
    semantic_relations: list[dict] = field(default_factory=list)
    content_summaries: list[str] = field(default_factory=list)
    
    # Derived fields
    topic_hierarchy: dict = field(default_factory=dict)
    concept_to_topic: dict = field(default_factory=dict)
    prereq_chain: list[str] = field(default_factory=list)
    
    # Metadata
    window_count: int = 0
    total_pages: int = 0
    extraction_errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def get_enrichment_context(self, max_tokens: int = 800) -> str:
        """Generate a concise context string for enrichment prompts."""
        parts = []
        
        # Main topics
        if self.main_topics:
            topic_names = [t.get("name", "") for t in self.main_topics[:5]]
            parts.append(f"DOCUMENT TOPICS: {', '.join(topic_names)}")
        
        # Key prerequisites
        if self.prerequisites:
            prereq_names = [p.get("concept", "") for p in self.prerequisites[:5] 
                          if p.get("importance") in ("essential", "helpful")]
            if prereq_names:
                parts.append(f"ASSUMED PREREQUISITES: {', '.join(prereq_names)}")
        
        # Key concepts with types
        if self.concept_taxonomy:
            concept_strs = []
            for c in self.concept_taxonomy[:10]:
                name = c.get("name", "")
                ctype = c.get("concept_type", "")
                if name:
                    concept_strs.append(f"{name} ({ctype})" if ctype else name)
            if concept_strs:
                parts.append(f"KEY CONCEPTS: {', '.join(concept_strs)}")
        
        # Learning objectives (abbreviated)
        if self.learning_objectives:
            obj_strs = [o.get("objective", "")[:80] for o in self.learning_objectives[:3]]
            if obj_strs:
                parts.append(f"LEARNING GOALS: {'; '.join(obj_strs)}")
        
        context = "\n".join(parts)
        
        # Truncate if too long
        if token_len(context) > max_tokens:
            # Rough truncation
            words = context.split()
            target_words = int(max_tokens * 0.75)
            context = " ".join(words[:target_words]) + "..."
        
        return context


class OntologyExtractor:
    """
    Extracts high-level ontological structure from a document.
    
    Uses token-based batching: single-pass for documents ≤ max_tokens_per_call,
    token-based batches with overlap for larger documents. No content truncation.
    """
    
    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        max_tokens_per_call: int = DEFAULT_MAX_TOKENS_PER_CALL,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
        ontology_model: str | None = None,
        embed_fn=None,
    ):
        self.llm = llm_provider
        self.max_tokens_per_call = max_tokens_per_call
        self.overlap_tokens = overlap_tokens
        self.ontology_model = ontology_model
        self._embed_fn = embed_fn  # async fn: list[str] -> list[list[float]]
    
    @observe(name="ontology-extraction", capture_input=False)
    async def extract(
        self,
        sections: list[SectionData],
        resource_title: Optional[str] = None,
    ) -> ResourceOntology:
        """
        Extract ontology from parsed document sections.
        
        For documents ≤ max_tokens_per_call: single LLM call, full content.
        For larger documents: token-based batches with cross-batch accumulation.
        No content truncation.
        """
        if not sections:
            logger.warning("No sections provided for ontology extraction")
            return ResourceOntology()
        
        # Build token-based batches
        batches = self._build_token_batches(sections)
        total_tokens = sum(token_len(s.text) for s in sections)
        logger.info(
            f"[ONTOLOGY] {len(batches)} batch(es) from {len(sections)} sections "
            f"(~{total_tokens} tokens, model={self.ontology_model or 'default'})"
        )
        
        if not batches:
            return ResourceOntology()
        
        # Extract ontology from each batch with cross-batch accumulation
        batch_results: list[OntologyWindowResponse] = []
        accumulated_objectives: list[dict] = []
        accumulated_topics: list[dict] = []
        total_batches = len(batches)
        
        for i, batch in enumerate(batches):
            batch_pages = self._get_window_page_range(batch)
            batch_tokens = sum(token_len(s.text) for s in batch)
            logger.info(
                f"[ONTOLOGY] Processing batch {i+1}/{total_batches} "
                f"(pages {batch_pages}, ~{batch_tokens} tokens)"
            )
            try:
                result = await self._extract_batch(
                    batch, i, total_batches, resource_title,
                    accumulated_objectives=accumulated_objectives if i > 0 else None,
                    accumulated_topics=accumulated_topics if i > 0 else None,
                )
                topics_found = len(result.main_topics)
                concepts_found = len(result.concept_taxonomy)
                logger.info(f"[ONTOLOGY] Batch {i+1}: {topics_found} topics, {concepts_found} concepts")
                batch_results.append(result)
                
                # Accumulate for cross-batch context
                for obj in result.learning_objectives:
                    obj_dict = obj.model_dump() if hasattr(obj, 'model_dump') else dict(obj)
                    accumulated_objectives.append(obj_dict)
                for topic in result.main_topics:
                    topic_dict = topic.model_dump() if hasattr(topic, 'model_dump') else dict(topic)
                    accumulated_topics.append(topic_dict)
            except Exception as e:
                logger.warning(f"[ONTOLOGY] Batch {i+1} failed: {e}")
                batch_results.append(OntologyWindowResponse())
        
        # Merge batch results (single-batch = no merge needed)
        ontology = await self._merge_results(batch_results, sections)
        ontology.window_count = len(batches)
        ontology.total_pages = self._count_pages(sections)
        
        logger.info(
            f"[ONTOLOGY] ✓ Extraction complete: "
            f"{len(ontology.main_topics)} topics, "
            f"{len(ontology.learning_objectives)} objectives, "
            f"{len(ontology.concept_taxonomy)} concepts, "
            f"{len(ontology.prerequisites)} prerequisites, "
            f"{len(ontology.terminology)} terms, "
            f"{len(ontology.semantic_relations)} relations"
        )
        
        return ontology
    
    def _build_token_batches(self, sections: list[SectionData]) -> list[list[SectionData]]:
        """Build batches by token count. Single pass when document fits."""
        if not sections:
            return []
        
        total_tokens = sum(token_len(s.text) for s in sections)
        
        # Single pass if entire document fits within token budget
        if total_tokens <= self.max_tokens_per_call:
            return [sections]
        
        # Token-based batching for very large documents
        batches = []
        current_batch = []
        current_tokens = 0
        
        for section in sections:
            section_tokens = token_len(section.text)
            
            if current_tokens + section_tokens > self.max_tokens_per_call and current_batch:
                batches.append(current_batch)
                # Overlap: carry last N tokens of sections into next batch
                overlap_sections = []
                overlap_tok = 0
                for s in reversed(current_batch):
                    s_tok = token_len(s.text)
                    if overlap_tok + s_tok > self.overlap_tokens:
                        break
                    overlap_sections.insert(0, s)
                    overlap_tok += s_tok
                current_batch = list(overlap_sections)
                current_tokens = overlap_tok
            
            current_batch.append(section)
            current_tokens += section_tokens
        
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    def _count_pages(self, sections: list[SectionData]) -> int:
        """Count total pages from sections."""
        if not sections:
            return 0
        return max((s.page_end or s.page_start or 0) for s in sections)
    
    @observe(name="ontology-batch", capture_input=False)
    async def _extract_batch(
        self,
        batch_sections: list[SectionData],
        batch_idx: int,
        total_batches: int,
        resource_title: Optional[str],
        accumulated_objectives: Optional[list[dict]] = None,
        accumulated_topics: Optional[list[dict]] = None,
    ) -> OntologyWindowResponse:
        """Extract ontology from a single batch. No content truncation."""
        # Build full batch text with section headings — NO TRUNCATION
        parts = []
        for section in batch_sections:
            if section.heading:
                parts.append(f"## {section.heading}")
            parts.append(section.text)
        
        batch_text = "\n\n".join(parts)
        
        # Build user message
        context_info = []
        if resource_title:
            context_info.append(f"Document: {resource_title}")
        if total_batches > 1:
            context_info.append(f"Section {batch_idx + 1} of {total_batches}")
        
        page_range = self._get_page_range(batch_sections)
        if page_range:
            context_info.append(f"Pages: {page_range}")
        
        # Cross-batch accumulation: tell LLM what was already extracted
        if accumulated_objectives or accumulated_topics:
            already_extracted = []
            if accumulated_topics:
                topic_names = [t.get("name", "") for t in accumulated_topics[:15]]
                already_extracted.append(f"TOPICS ALREADY IDENTIFIED: {', '.join(topic_names)}")
            if accumulated_objectives:
                obj_list = [o.get("objective", "")[:100] for o in accumulated_objectives[:10]]
                already_extracted.append(
                    "OBJECTIVES ALREADY EXTRACTED (do NOT repeat these):\n"
                    + "\n".join(f"- {o}" for o in obj_list)
                )
            context_info.append("\n".join(already_extracted))
        
        user_message = "\n".join(context_info) + "\n\n---\n\n" + batch_text
        
        from app.config import settings
        
        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        
        response = await self.llm.generate_json(
            messages=messages,
            schema=OntologyWindowResponse,
            temperature=0.3,
            max_tokens=settings.ONTOLOGY_MAX_OUTPUT_TOKENS,
            model=self.ontology_model,
        )
        
        return response
    
    def _get_page_range(self, sections: list[SectionData]) -> Optional[str]:
        """Get page range string for sections."""
        starts = [s.page_start for s in sections if s.page_start]
        ends = [s.page_end for s in sections if s.page_end]
        
        if not starts:
            return None
        
        min_page = min(starts)
        max_page = max(ends) if ends else max(starts)
        
        if min_page == max_page:
            return str(min_page)
        return f"{min_page}-{max_page}"
    
    def _get_window_page_range(self, window_sections: list[SectionData]) -> str:
        """Get page range string for a window, for logging."""
        page_range = self._get_page_range(window_sections)
        return page_range if page_range else "unknown"
    
    async def _merge_results(
        self,
        window_results: list[OntologyWindowResponse],
        sections: list[SectionData],
    ) -> ResourceOntology:
        """Merge ontology results from all batches with semantic dedup."""
        ontology = ResourceOntology()
        
        # Track seen items for fast string-based dedup
        seen_topics = set()
        seen_objectives = set()
        seen_prereqs = set()
        seen_concepts = set()
        seen_terms = set()
        seen_relations = set()
        
        for result in window_results:
            # Merge topics
            for topic in result.main_topics:
                topic_dict = topic.model_dump() if hasattr(topic, 'model_dump') else dict(topic)
                key = topic_dict.get("name", "").lower()
                if key and key not in seen_topics:
                    seen_topics.add(key)
                    ontology.main_topics.append(topic_dict)
            
            # Merge learning objectives (use full text, not first 50 chars)
            for obj in result.learning_objectives:
                obj_dict = obj.model_dump() if hasattr(obj, 'model_dump') else dict(obj)
                key = obj_dict.get("objective", "").lower().strip()
                if key and key not in seen_objectives:
                    seen_objectives.add(key)
                    ontology.learning_objectives.append(obj_dict)
            
            # Merge prerequisites
            for prereq in result.prerequisites:
                prereq_dict = prereq.model_dump() if hasattr(prereq, 'model_dump') else dict(prereq)
                key = prereq_dict.get("concept", "").lower()
                if key and key not in seen_prereqs:
                    seen_prereqs.add(key)
                    ontology.prerequisites.append(prereq_dict)
            
            # Merge concept taxonomy
            for concept in result.concept_taxonomy:
                concept_dict = concept.model_dump() if hasattr(concept, 'model_dump') else dict(concept)
                key = concept_dict.get("name", "").lower()
                if key and key not in seen_concepts:
                    seen_concepts.add(key)
                    ontology.concept_taxonomy.append(concept_dict)
            
            # Merge terminology
            for term in result.terminology:
                term_dict = term.model_dump() if hasattr(term, 'model_dump') else dict(term)
                key = term_dict.get("term", "").lower()
                if key and key not in seen_terms:
                    seen_terms.add(key)
                    ontology.terminology.append(term_dict)

            # Merge semantic relations with evidence-level dedup
            for relation in result.semantic_relations:
                relation_dict = relation.model_dump() if hasattr(relation, 'model_dump') else dict(relation)
                source = relation_dict.get("source_concept", "").lower().strip()
                target = relation_dict.get("target_concept", "").lower().strip()
                rel_type = relation_dict.get("relation_type", "").upper().strip()
                page_range = (relation_dict.get("page_range") or "").strip()
                section_heading = (relation_dict.get("section_heading") or "").strip().lower()
                key = (source, target, rel_type, page_range, section_heading)
                if source and target and rel_type and key not in seen_relations:
                    seen_relations.add(key)
                    ontology.semantic_relations.append(relation_dict)
            
            # Collect summaries
            if result.content_summary:
                ontology.content_summaries.append(result.content_summary)
        
        # Semantic dedup pass (if embedding function available)
        if self._embed_fn and len(window_results) > 1:
            from app.utils.semantic_dedup import semantic_dedup
            ontology.learning_objectives = await semantic_dedup(
                ontology.learning_objectives, "objective", self._embed_fn, 0.85, "keep_longer"
            )
            ontology.main_topics = await semantic_dedup(
                ontology.main_topics, "name", self._embed_fn, 0.90, "keep_longer"
            )
            ontology.prerequisites = await semantic_dedup(
                ontology.prerequisites, "concept", self._embed_fn, 0.90, "keep_first"
            )
            ontology.concept_taxonomy = await semantic_dedup(
                ontology.concept_taxonomy, "name", self._embed_fn, 0.90, "keep_longer"
            )
            ontology.terminology = await semantic_dedup(
                ontology.terminology, "term", self._embed_fn, 0.90, "keep_longer"
            )
        
        # Build derived structures
        ontology.topic_hierarchy = self._build_topic_hierarchy(ontology.main_topics)
        ontology.concept_to_topic = self._build_concept_topic_map(
            ontology.concept_taxonomy, ontology.main_topics
        )
        ontology.prereq_chain = self._build_prereq_chain(ontology.prerequisites)
        
        return ontology
    
    def _build_topic_hierarchy(self, topics: list[dict]) -> dict:
        """Build a topic hierarchy from extracted topics."""
        hierarchy = {}
        for topic in topics:
            name = topic.get("name", "")
            subtopics = topic.get("subtopics", [])
            if name:
                hierarchy[name] = {
                    "subtopics": subtopics,
                    "importance": topic.get("importance", "primary"),
                }
        return hierarchy
    
    def _build_concept_topic_map(
        self,
        concepts: list[dict],
        topics: list[dict],
    ) -> dict:
        """Map concepts to their likely parent topics."""
        # Simple heuristic: use parent_concept or first related topic
        concept_map = {}
        topic_names = {t.get("name", "").lower() for t in topics}
        
        for concept in concepts:
            name = concept.get("name", "")
            parent = concept.get("parent_concept", "")
            
            if parent and parent.lower() in topic_names:
                concept_map[name] = parent
            elif parent:
                concept_map[name] = parent
        
        return concept_map
    
    def _build_prereq_chain(self, prerequisites: list[dict]) -> list[str]:
        """Build ordered list of prerequisites by importance."""
        # Sort by importance: essential > helpful > optional
        importance_order = {"essential": 0, "helpful": 1, "optional": 2}
        sorted_prereqs = sorted(
            prerequisites,
            key=lambda p: importance_order.get(p.get("importance", "helpful"), 1)
        )
        return [p.get("concept", "") for p in sorted_prereqs if p.get("concept")]
