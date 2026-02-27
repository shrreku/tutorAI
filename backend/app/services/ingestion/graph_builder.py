"""
Concept Graph Builder - TICKET-016 (Enhanced)

Build ontologically-accurate, pedagogy-aware concept graphs from:
1. Explicit semantic relationships extracted during enrichment
2. Co-occurrence patterns (supplementary)
3. Prerequisite hints with transitive closure
"""
import logging
import uuid
from collections import defaultdict
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.chunk import Chunk
from app.models.knowledge_base import (
    ResourceConceptEvidence,
    ResourceConceptGraph,
    ResourcePrereqHint,
)
from app.services.ingestion.graph_algorithms import (
    compute_direction,
    compute_qhat_vectors,
    compute_topo_order_from_map,
    cosine_similarity,
    enforce_dag_on_map,
    ppmi_score,
)
from app.utils.canonicalization import canonicalize_concept_id

logger = logging.getLogger(__name__)

# Relationship types and their directionality properties
RELATIONSHIP_PROPERTIES = {
    "REQUIRES": {"directed": True, "dir_forward": 0.95, "prereq": True},
    "IS_A": {"directed": True, "dir_forward": 0.90, "prereq": False},
    "PART_OF": {"directed": True, "dir_forward": 0.85, "prereq": False},
    "DERIVES_FROM": {"directed": True, "dir_forward": 0.90, "prereq": True},
    "ENABLES": {"directed": True, "dir_forward": 0.85, "prereq": True},
    "EQUIVALENT_TO": {"directed": False, "dir_forward": 0.50, "prereq": False},
    "CONTRASTS_WITH": {"directed": False, "dir_forward": 0.50, "prereq": False},
    "APPLIES_TO": {"directed": True, "dir_forward": 0.75, "prereq": False},
    "RELATED_TO": {"directed": False, "dir_forward": 0.50, "prereq": False},
}


def _score_ontology_relation(relation: dict) -> tuple[float, dict]:
    """Compute confidence from relation confidence + evidence richness."""
    base_confidence = float(relation.get("confidence", 0.75) or 0.75)
    evidence_bits = {
        "has_quote": bool(relation.get("evidence_quote")),
        "has_page_range": bool(relation.get("page_range")),
        "has_section_heading": bool(relation.get("section_heading")),
    }
    evidence_count = sum(1 for present in evidence_bits.values() if present)

    # Small bounded boost for richer evidence to keep ontology edges calibrated.
    evidence_boost = evidence_count * 0.04
    scored_confidence = min(1.0, max(0.0, base_confidence + evidence_boost))

    score_detail = {
        "base_confidence": base_confidence,
        "evidence_boost": evidence_boost,
        "evidence_fields": evidence_bits,
    }
    return scored_confidence, score_detail


class ConceptGraphBuilder:
    """Builds ontologically-accurate concept graphs with typed semantic edges."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def build(
        self,
        resource_id: uuid.UUID,
        top_k: int = 4,
        min_similarity: float = 0.25,
        min_cooccurrence: int = 2,
        mutual_knn: bool = True,
        adaptive: bool = True,
        use_ppmi: bool = True,
        force_rebuild: bool = False,
        ontology_relations: Optional[list[dict]] = None,
    ) -> dict:
        """
        Build ontologically-accurate concept graph for a resource.
        
        The graph is built in two phases:
        1. Explicit semantic relationships from enrichment (high confidence)
        2. Co-occurrence relationships via PPMI (supplementary)
        
        Args:
            resource_id: UUID of the resource
            top_k: Maximum co-occurrence neighbors per concept
            min_similarity: Minimum similarity threshold for co-occurrence edges
            use_ppmi: Use PPMI scoring instead of raw cosine
            force_rebuild: If True, clear existing graph before rebuilding
            
        Returns:
            Dict with build metrics
        """
        if force_rebuild:
            await self._clear_graph(resource_id)
        
        # Get evidence and chunks with enrichment
        evidence = await self._get_evidence(resource_id)
        if not evidence:
            logger.warning(f"No evidence found for resource {resource_id}")
            return {"edges_created": 0, "semantic_edges": 0, "cooccurrence_edges": 0}
        
        # Get chunks with enrichment metadata for semantic relationships
        chunks = await self._get_chunks_with_enrichment(resource_id)
        
        # Get prereq hints
        prereq_lookup = await self._get_prereq_lookup(resource_id)

        # Build Q-hat vectors for co-occurrence
        qhat = compute_qhat_vectors(evidence)
        admitted_concepts = set(qhat.keys())
        
        if len(admitted_concepts) < 2:
            logger.info(f"Only {len(admitted_concepts)} concepts, skipping graph building")
            return {"edges_created": 0, "semantic_edges": 0, "cooccurrence_edges": 0}
        
        # Track edges to avoid duplicates
        edge_map: dict[tuple[str, str], dict] = {}
        
        # ============================================================
        # PHASE 1: Build edges from explicit semantic relationships
        # ============================================================
        semantic_edge_count = 0
        ontology_edges_seeded = 0
        ontology_edges_boosted = 0
        for chunk in chunks:
            enrichment = chunk.enrichment_metadata or {}
            for rel in enrichment.get("semantic_relationships", []):
                source_id = rel.get("source_id")
                target_id = rel.get("target_id")
                rel_type = rel.get("relation_type", "RELATED_TO")
                confidence = rel.get("confidence", 0.8)
                
                # Only include edges between admitted concepts
                if not source_id or not target_id:
                    continue
                if source_id not in admitted_concepts or target_id not in admitted_concepts:
                    continue
                if source_id == target_id:
                    continue
                
                # Get relationship properties
                rel_props = RELATIONSHIP_PROPERTIES.get(rel_type, RELATIONSHIP_PROPERTIES["RELATED_TO"])
                
                # Create edge key (ordered for directed, unordered for undirected)
                if rel_props["directed"]:
                    edge_key = (source_id, target_id)
                else:
                    edge_key = tuple(sorted([source_id, target_id]))
                
                # Merge with existing edge or create new
                if edge_key in edge_map:
                    existing = edge_map[edge_key]
                    # Upgrade confidence if this is a stronger relationship
                    if confidence > existing["confidence"]:
                        existing["confidence"] = confidence
                    # Keep the more specific relationship type
                    if rel_type != "RELATED_TO" and existing["relation_type"] == "RELATED_TO":
                        existing["relation_type"] = rel_type
                        existing["dir_forward"] = rel_props["dir_forward"]
                        existing["dir_backward"] = 1.0 - rel_props["dir_forward"]
                else:
                    edge_map[edge_key] = {
                        "source": edge_key[0],
                        "target": edge_key[1],
                        "relation_type": rel_type,
                        "assoc_weight": confidence,
                        "confidence": confidence,
                        "dir_forward": rel_props["dir_forward"],
                        "dir_backward": 1.0 - rel_props["dir_forward"],
                        "source_type": "semantic",
                    }
                    semantic_edge_count += 1

        # Seed semantic graph with ontology relation inventory (Docling ticket DL-008)
        for relation in ontology_relations or []:
            source_id = canonicalize_concept_id(relation.get("source_concept", ""))
            target_id = canonicalize_concept_id(relation.get("target_concept", ""))
            rel_type = str(relation.get("relation_type", "RELATED_TO")).upper().strip()
            confidence, score_detail = _score_ontology_relation(relation)

            if not source_id or not target_id or source_id == target_id:
                continue
            if source_id not in admitted_concepts or target_id not in admitted_concepts:
                continue

            rel_props = RELATIONSHIP_PROPERTIES.get(rel_type, RELATIONSHIP_PROPERTIES["RELATED_TO"])
            edge_key = (source_id, target_id) if rel_props["directed"] else tuple(sorted([source_id, target_id]))

            if edge_key in edge_map:
                existing = edge_map[edge_key]
                if confidence > existing["confidence"]:
                    existing["confidence"] = confidence
                    existing["assoc_weight"] = max(existing["assoc_weight"], confidence)
                    existing["score_details"] = score_detail
                existing["source_type"] = "ontology_relation"
                if rel_type != "RELATED_TO" and existing["relation_type"] == "RELATED_TO":
                    existing["relation_type"] = rel_type
                    existing["dir_forward"] = rel_props["dir_forward"]
                    existing["dir_backward"] = 1.0 - rel_props["dir_forward"]
                ontology_edges_boosted += 1
                continue

            edge_map[edge_key] = {
                "source": edge_key[0],
                "target": edge_key[1],
                "relation_type": rel_type,
                "assoc_weight": confidence,
                "confidence": confidence,
                "dir_forward": rel_props["dir_forward"],
                "dir_backward": 1.0 - rel_props["dir_forward"],
                "source_type": "ontology_relation",
                "score_details": score_detail,
            }
            semantic_edge_count += 1
            ontology_edges_seeded += 1
        
        # ============================================================
        # PHASE 2: Build edges from prereq hints (if not already covered)
        # ============================================================
        for (source, target), support in prereq_lookup.items():
            if source not in admitted_concepts or target not in admitted_concepts:
                continue
            if source == target:
                continue
            
            edge_key = (source, target)
            if edge_key not in edge_map:
                confidence = min(1.0, 0.5 + 0.1 * support)
                edge_map[edge_key] = {
                    "source": source,
                    "target": target,
                    "relation_type": "REQUIRES",
                    "assoc_weight": confidence,
                    "confidence": confidence,
                    "dir_forward": 0.90,
                    "dir_backward": 0.10,
                    "source_type": "prereq_hint",
                }
                semantic_edge_count += 1
        
        # ============================================================
        # PHASE 3: Supplement with co-occurrence edges (PPMI)
        # ============================================================
        concepts = list(admitted_concepts)
        total_chunks = len(set(str(e.chunk_id) for e in evidence))
        concept_chunk_counts = {c: len(qhat[c]) for c in concepts}
        
        # Adaptive thresholds based on graph size
        effective_top_k = top_k
        effective_min_similarity = min_similarity
        if adaptive:
            if len(concepts) >= 25:
                effective_top_k = min(effective_top_k, 2)
                effective_min_similarity = max(effective_min_similarity, 0.35)
            elif len(concepts) >= 15:
                effective_top_k = min(effective_top_k, 3)
                effective_min_similarity = max(effective_min_similarity, 0.30)
        
        # Compute co-occurrence for concepts not yet connected
        cooccurrence_edge_count = 0
        for i, c1 in enumerate(concepts):
            # Count existing edges for this concept
            existing_neighbors = sum(
                1 for k in edge_map 
                if k[0] == c1 or k[1] == c1
            )
            
            # Skip if concept already has enough edges from semantic phase
            if existing_neighbors >= effective_top_k:
                continue
            
            candidates = []
            for c2 in concepts[i+1:]:
                edge_key = tuple(sorted([c1, c2]))
                if edge_key in edge_map:
                    continue
                
                if use_ppmi:
                    sim = ppmi_score(
                        qhat[c1], qhat[c2],
                        concept_chunk_counts[c1],
                        concept_chunk_counts[c2],
                        total_chunks,
                        min_cooccurrence,
                    )
                else:
                    sim = cosine_similarity(qhat[c1], qhat[c2])
                
                if sim >= effective_min_similarity:
                    candidates.append((c2, sim))
            
            # Take top-k candidates
            candidates.sort(key=lambda x: -x[1])
            slots_available = effective_top_k - existing_neighbors
            
            for c2, sim in candidates[:slots_available]:
                edge_key = tuple(sorted([c1, c2]))
                if edge_key in edge_map:
                    continue
                
                # Compute directionality from document order
                dir_fwd, dir_bwd = compute_direction(c1, c2, evidence, prereq_lookup)
                
                # Determine if this looks like a prerequisite relationship
                rel_type = "RELATED_TO"
                if dir_fwd >= 0.75:
                    rel_type = "ENABLES"  # c1 likely enables c2
                elif dir_bwd >= 0.75:
                    rel_type = "REQUIRES"  # c1 likely requires c2
                
                edge_map[edge_key] = {
                    "source": edge_key[0],
                    "target": edge_key[1],
                    "relation_type": rel_type,
                    "assoc_weight": sim,
                    "confidence": sim * 0.7,  # Lower confidence for co-occurrence
                    "dir_forward": dir_fwd,
                    "dir_backward": dir_bwd,
                    "source_type": "cooccurrence",
                }
                cooccurrence_edge_count += 1
        
        # ============================================================
        # PHASE 4: Enforce DAG on prerequisite edges (before DB insert)
        # ============================================================
        prereq_rel_types = {"REQUIRES", "ENABLES", "DERIVES_FROM"}
        cycles_broken = enforce_dag_on_map(edge_map, prereq_rel_types, logger=logger)
        
        # Compute topological ordering on the cleaned edge_map
        topo_order = compute_topo_order_from_map(edge_map, admitted_concepts)
        
        # ============================================================
        # PHASE 5: Create database edges
        # ============================================================
        edges = []
        for edge_data in edge_map.values():
            edges.append(ResourceConceptGraph(
                resource_id=resource_id,
                source_concept_id=edge_data["source"],
                target_concept_id=edge_data["target"],
                relation_type=edge_data["relation_type"],
                assoc_weight=edge_data["assoc_weight"],
                confidence=edge_data["confidence"],
                dir_forward=edge_data["dir_forward"],
                dir_backward=edge_data["dir_backward"],
                source=edge_data["source_type"],
            ))
        
        # Bulk insert
        self.db.add_all(edges)
        await self.db.flush()
        
        logger.info(
            f"Created {len(edges)} graph edges for resource {resource_id} "
            f"(semantic: {semantic_edge_count}, cooccurrence: {cooccurrence_edge_count}, "
            f"cycles_broken: {cycles_broken})"
        )
        
        return {
            "edges_created": len(edges),
            "semantic_edges": semantic_edge_count,
            "cooccurrence_edges": cooccurrence_edge_count,
            "ontology_edges_seeded": ontology_edges_seeded,
            "ontology_edges_boosted": ontology_edges_boosted,
            "cycles_broken": cycles_broken,
            "topo_order": topo_order,
        }
    
    async def _get_chunks_with_enrichment(self, resource_id: uuid.UUID) -> list[Chunk]:
        """Get all chunks for a resource with their enrichment metadata."""
        result = await self.db.execute(
            select(Chunk)
            .where(Chunk.resource_id == resource_id)
            .order_by(Chunk.chunk_index)
        )
        return list(result.scalars().all())
    
    async def _get_evidence(self, resource_id: uuid.UUID) -> list[ResourceConceptEvidence]:
        """Get all evidence for a resource."""
        result = await self.db.execute(
            select(ResourceConceptEvidence)
            .where(ResourceConceptEvidence.resource_id == resource_id)
        )
        return list(result.scalars().all())

    async def _get_prereq_lookup(self, resource_id: uuid.UUID) -> dict[tuple[str, str], int]:
        """Build prereq hint lookup keyed by (source, target)."""
        result = await self.db.execute(
            select(ResourcePrereqHint)
            .where(ResourcePrereqHint.resource_id == resource_id)
        )
        prereq_lookup: dict[tuple[str, str], int] = defaultdict(int)
        for hint in result.scalars().all():
            if hint.source_concept_id and hint.target_concept_id:
                prereq_lookup[(hint.source_concept_id, hint.target_concept_id)] += max(
                    hint.support_count or 0,
                    1,
                )

        return prereq_lookup
    
    async def _clear_graph(self, resource_id: uuid.UUID) -> None:
        """Clear existing graph for a resource."""
        await self.db.execute(
            delete(ResourceConceptGraph).where(ResourceConceptGraph.resource_id == resource_id)
        )
        await self.db.flush()
