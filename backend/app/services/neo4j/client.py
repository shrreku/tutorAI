"""
Neo4j Client for Concept Graph Storage.

Syncs concept graphs from PostgreSQL to Neo4j for visualization and graph queries.
"""
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Async Neo4j client for concept graph operations."""
    
    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
    ):
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: Optional[Any] = None
    
    async def connect(self) -> bool:
        """Connect to Neo4j and verify connectivity."""
        try:
            from neo4j import AsyncGraphDatabase
            from neo4j.exceptions import AuthError, ServiceUnavailable
        except ImportError:
            logger.info("Neo4j disabled: neo4j driver package not installed")
            return False

        try:
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {self._uri}")
            return True
        except (ServiceUnavailable, AuthError) as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self._driver = None
            return False
        except Exception as e:
            logger.error(f"Neo4j connection error: {e}")
            self._driver = None
            return False
    
    async def close(self):
        """Close the Neo4j driver."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")
    
    @property
    def is_connected(self) -> bool:
        return self._driver is not None
    
    @asynccontextmanager
    async def session(self):
        """Get an async session context manager."""
        if not self._driver:
            raise RuntimeError("Neo4j client not connected")
        async with self._driver.session() as session:
            yield session
    
    async def sync_resource_graph(
        self,
        resource_id: str,
        concepts: list[dict],
        edges: list[dict],
        prereq_hints: Optional[list[dict]] = None,
    ) -> dict:
        """
        Sync a resource's concept graph to Neo4j.
        
        Args:
            resource_id: UUID of the resource
            concepts: List of concept dicts with id, name, teach_count, etc.
            edges: List of edge dicts with source, target, weight, direction
            
        Returns:
            Dict with sync metrics
        """
        if not self._driver:
            logger.warning("Neo4j not connected, skipping sync")
            return {"synced": False, "reason": "not_connected"}
        
        async with self.session() as session:
            # Clear existing graph for this resource
            await session.run(
                """
                MATCH (c:Concept {resource_id: $resource_id})
                DETACH DELETE c
                """,
                resource_id=resource_id,
            )
            
            # Create concept nodes
            for concept in concepts:
                await session.run(
                    """
                    CREATE (c:Concept {
                        concept_id: $concept_id,
                        resource_id: $resource_id,
                        name: $name,
                        teach_count: $teach_count,
                        mention_count: $mention_count,
                        avg_quality: $avg_quality
                    })
                    """,
                    concept_id=concept["concept_id"],
                    resource_id=resource_id,
                    name=concept.get("name", concept["concept_id"]),
                    teach_count=concept.get("teach_count", 0),
                    mention_count=concept.get("mention_count", 0),
                    avg_quality=concept.get("avg_quality", 0.5),
                )
            
            # Create edges
            allowed_rel_types = {
                "RELATED_TO",
                "PRECEDES",
                "REQUIRES",
                "IS_A",
                "PART_OF",
                "DERIVES_FROM",
                "ENABLES",
                "APPLIES_TO",
                "HAS_PART",
                "USES",
                "SIMILAR_TO",
                "DEFINES",
                "EXAMPLE_OF",
                "CONTRASTS_WITH",
                "PREREQ",
            }

            for edge in edges:
                rel_type = (edge.get("rel_type") or "RELATED_TO").upper()
                if rel_type not in allowed_rel_types:
                    rel_type = "RELATED_TO"

                await session.run(
                    """
                    MATCH (a:Concept {concept_id: $source, resource_id: $resource_id})
                    MATCH (b:Concept {concept_id: $target, resource_id: $resource_id})
                    CALL apoc.create.relationship(
                        a,
                        $rel_type,
                        {
                            weight: $weight,
                            dir_forward: $dir_forward,
                            dir_backward: $dir_backward,
                            confidence: $confidence
                        },
                        b
                    ) YIELD rel
                    RETURN 1
                    """,
                    source=edge["source_concept_id"],
                    target=edge["target_concept_id"],
                    resource_id=resource_id,
                    rel_type=rel_type,
                    weight=edge.get("assoc_weight", 0.5),
                    dir_forward=edge.get("dir_forward", 0.5),
                    dir_backward=edge.get("dir_backward", 0.5),
                    confidence=edge.get("confidence", None),
                )

            # Create prerequisite edges (typed)
            for hint in (prereq_hints or []):
                await session.run(
                    """
                    MATCH (a:Concept {concept_id: $source, resource_id: $resource_id})
                    MATCH (b:Concept {concept_id: $target, resource_id: $resource_id})
                    MERGE (a)-[r:PREREQ]->(b)
                    SET r.support_count = $support_count
                    """,
                    source=hint["source_concept_id"],
                    target=hint["target_concept_id"],
                    resource_id=resource_id,
                    support_count=hint.get("support_count", 1),
                )
            
            logger.info(f"Synced {len(concepts)} concepts and {len(edges)} edges to Neo4j for resource {resource_id}")
            return {
                "synced": True,
                "concepts": len(concepts),
                "edges": len(edges),
                "prereq_edges": len(prereq_hints or []),
            }
    
    async def get_concept_neighbors(
        self,
        resource_id: str,
        concept_id: str,
        max_depth: int = 2,
    ) -> list[dict]:
        """Get neighboring concepts up to max_depth hops."""
        if not self._driver:
            return []
        
        async with self.session() as session:
            result = await session.run(
                """
                MATCH path = (start:Concept {concept_id: $concept_id, resource_id: $resource_id})
                      -[r:RELATED_TO|PRECEDES|DEFINES|USES|PART_OF|EXAMPLE_OF|CONTRASTS_WITH|PREREQ*1..$max_depth]-(neighbor:Concept)
                RETURN neighbor.concept_id as concept_id,
                       neighbor.name as name,
                       length(path) as distance,
                       neighbor.teach_count as teach_count
                ORDER BY distance, neighbor.teach_count DESC
                """,
                concept_id=concept_id,
                resource_id=resource_id,
                max_depth=max_depth,
            )
            
            neighbors = []
            async for record in result:
                neighbors.append({
                    "concept_id": record["concept_id"],
                    "name": record["name"],
                    "distance": record["distance"],
                    "teach_count": record["teach_count"],
                })
            return neighbors
    
    async def get_learning_path(
        self,
        resource_id: str,
        start_concept: str,
        end_concept: str,
    ) -> list[str]:
        """Find shortest learning path between concepts."""
        if not self._driver:
            return []
        
        async with self.session() as session:
            result = await session.run(
                """
                MATCH path = shortestPath(
                    (start:Concept {concept_id: $start, resource_id: $resource_id})-
                    [r:RELATED_TO|PRECEDES|DEFINES|USES|PART_OF|EXAMPLE_OF|CONTRASTS_WITH|PREREQ*]->
                    (end:Concept {concept_id: $end, resource_id: $resource_id})
                )
                RETURN [n in nodes(path) | n.concept_id] as path
                """,
                start=start_concept,
                end=end_concept,
                resource_id=resource_id,
            )
            
            record = await result.single()
            if record:
                return record["path"]
            return []


# Singleton client instance
_neo4j_client: Optional[Neo4jClient] = None


async def get_neo4j_client() -> Optional[Neo4jClient]:
    """Get or create the Neo4j client singleton."""
    global _neo4j_client

    if not settings.NEO4J_ENABLED:
        return None

    if not settings.NEO4J_URI:
        logger.warning("Neo4j enabled but NEO4J_URI is not configured")
        return None
    
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient(
            uri=settings.NEO4J_URI,
            user=settings.NEO4J_USER or "neo4j",
            password=settings.NEO4J_PASSWORD or "password",
        )
        connected = await _neo4j_client.connect()
        if not connected:
            _neo4j_client = None
    
    return _neo4j_client
