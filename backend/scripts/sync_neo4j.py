"""
One-shot Neo4j sync script.

Reads the concept graph for a given resource from PostgreSQL
and writes it to Neo4j, replacing any stale data.

Usage:
    python scripts/sync_neo4j.py <resource_id>
    python scripts/sync_neo4j.py  # syncs most recent resource
"""

import asyncio
import logging
import sys
import os

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def sync(resource_id: str | None = None) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy import text

    # Use the Docker-internal DB URL
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/studyagent",
    )

    engine = create_async_engine(db_url, echo=False)

    async with AsyncSession(engine) as db:
        # Resolve resource_id
        if resource_id is None:
            row = (await db.execute(text(
                "SELECT id FROM resource ORDER BY created_at DESC LIMIT 1"
            ))).fetchone()
            if not row:
                logger.error("No resources found in database.")
                return
            resource_id = str(row[0])
            logger.info(f"Using most recent resource: {resource_id}")

        # -- Concepts --
        concepts_rows = (await db.execute(text("""
            SELECT concept_id, concept_type, bloom_level,
                   teach_count, mention_count, chunk_count,
                   importance_score, avg_quality, topo_order
            FROM resource_concept_stats
            WHERE resource_id = :rid
        """), {"rid": resource_id})).fetchall()

        if not concepts_rows:
            logger.error(f"No concepts found for resource {resource_id}. Has it been ingested?")
            return

        concepts = [
            {
                "concept_id": r[0],
                "name": r[0].replace("_", " ").title(),
                "concept_type": r[1],
                "bloom_level": r[2],
                "teach_count": r[3] or 0,
                "mention_count": r[4] or 0,
                "chunk_count": r[5] or 0,
                "importance_score": float(r[6]) if r[6] else 0.0,
                "avg_quality": float(r[7]) if r[7] else 0.5,
                "topo_order": r[8] or 0,
            }
            for r in concepts_rows
        ]
        logger.info(f"Found {len(concepts)} concepts")

        # -- Graph edges --
        edges_rows = (await db.execute(text("""
            SELECT source_concept_id, target_concept_id,
                   relation_type, confidence, assoc_weight,
                   dir_forward, dir_backward, source
            FROM resource_concept_graph
            WHERE resource_id = :rid
            ORDER BY confidence DESC NULLS LAST
        """), {"rid": resource_id})).fetchall()

        edges = [
            {
                "source_concept_id": r[0],
                "target_concept_id": r[1],
                "rel_type": r[2] or "RELATED_TO",
                "confidence": float(r[3]) if r[3] else 0.7,
                "assoc_weight": float(r[4]) if r[4] else 0.5,
                "dir_forward": float(r[5]) if r[5] else 0.5,
                "dir_backward": float(r[6]) if r[6] else 0.5,
                "source": r[7] or "semantic",
            }
            for r in edges_rows
        ]
        logger.info(f"Found {len(edges)} graph edges")

        # -- Prereq hints --
        prereq_rows = (await db.execute(text("""
            SELECT source_concept_id, target_concept_id, support_count
            FROM resource_prereq_hint
            WHERE resource_id = :rid
            ORDER BY support_count DESC
        """), {"rid": resource_id})).fetchall()

        prereqs = [
            {
                "source_concept_id": r[0],
                "target_concept_id": r[1],
                "support_count": r[2] or 1,
            }
            for r in prereq_rows
        ]
        logger.info(f"Found {len(prereqs)} prereq hints")

        # -- Topic bundles for PRECEDES edges --
        topic_rows = (await db.execute(text("""
            SELECT topic_id, topic_name, primary_concepts, prereq_topic_ids
            FROM resource_topic_bundle
            WHERE resource_id = :rid
        """), {"rid": resource_id})).fetchall()

        topics = [
            {
                "topic_id": r[0],
                "topic_name": r[1],
                "primary_concepts": r[2] or [],
                "prereq_topic_ids": r[3] or [],
            }
            for r in topic_rows
        ]
        logger.info(f"Found {len(topics)} topic bundles")

    await engine.dispose()

    # -- Connect to Neo4j --
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        logger.error("neo4j Python driver not installed.")
        return

    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        await driver.verify_connectivity()
        logger.info(f"Connected to Neo4j at {neo4j_uri}")
    except Exception as e:
        logger.error(f"Cannot connect to Neo4j: {e}")
        await driver.close()
        return

    async with driver.session() as session:
        # 1. Delete any stale data for this resource
        await session.run(
            "MATCH (c:Concept {resource_id: $rid}) DETACH DELETE c",
            rid=resource_id,
        )
        logger.info(f"Cleared stale Neo4j data for resource {resource_id}")

        # 2. Create concept nodes
        for c in concepts:
            await session.run("""
                CREATE (n:Concept {
                    concept_id:      $concept_id,
                    resource_id:     $resource_id,
                    name:            $name,
                    concept_type:    $concept_type,
                    bloom_level:     $bloom_level,
                    teach_count:     $teach_count,
                    mention_count:   $mention_count,
                    chunk_count:     $chunk_count,
                    importance_score:$importance_score,
                    avg_quality:     $avg_quality,
                    topo_order:      $topo_order
                })
            """,
                concept_id=c["concept_id"],
                resource_id=resource_id,
                name=c["name"],
                concept_type=c["concept_type"],
                bloom_level=c["bloom_level"],
                teach_count=c["teach_count"],
                mention_count=c["mention_count"],
                chunk_count=c["chunk_count"],
                importance_score=c["importance_score"],
                avg_quality=c["avg_quality"],
                topo_order=c["topo_order"],
            )
        logger.info(f"Created {len(concepts)} Concept nodes")

        # 3. Create typed relationship edges
        allowed_rel_types = {
            "RELATED_TO", "REQUIRES", "IS_A", "PART_OF",
            "DERIVES_FROM", "ENABLES", "APPLIES_TO", "HAS_PART",
            "USES", "SIMILAR_TO", "CONTRASTS_WITH", "PREREQ",
            "INSTANCE_OF", "SUBCLASS_OF", "COMPONENT_OF",
        }
        edge_count = 0
        for e in edges:
            rel = (e["rel_type"] or "RELATED_TO").upper()
            if rel not in allowed_rel_types:
                rel = "RELATED_TO"
            try:
                await session.run(f"""
                    MATCH (a:Concept {{concept_id: $src, resource_id: $rid}})
                    MATCH (b:Concept {{concept_id: $tgt, resource_id: $rid}})
                    CREATE (a)-[r:{rel} {{
                        weight:      $weight,
                        confidence:  $confidence,
                        dir_forward: $dir_forward,
                        dir_backward:$dir_backward,
                        source:      $source
                    }}]->(b)
                """,
                    src=e["source_concept_id"],
                    tgt=e["target_concept_id"],
                    rid=resource_id,
                    weight=e["assoc_weight"],
                    confidence=e["confidence"],
                    dir_forward=e["dir_forward"],
                    dir_backward=e["dir_backward"],
                    source=e["source"],
                )
                edge_count += 1
            except Exception as ex:
                logger.warning(f"Edge {e['source_concept_id']}->{e['target_concept_id']}: {ex}")
        logger.info(f"Created {edge_count} typed edges")

        # 4. Prereq edges
        prereq_count = 0
        for p in prereqs:
            try:
                await session.run("""
                    MATCH (a:Concept {concept_id: $src, resource_id: $rid})
                    MATCH (b:Concept {concept_id: $tgt, resource_id: $rid})
                    MERGE (a)-[r:PREREQ]->(b)
                    SET r.support_count = $cnt
                """,
                    src=p["source_concept_id"],
                    tgt=p["target_concept_id"],
                    rid=resource_id,
                    cnt=p["support_count"],
                )
                prereq_count += 1
            except Exception as ex:
                logger.warning(f"Prereq {p['source_concept_id']}->{p['target_concept_id']}: {ex}")
        logger.info(f"Created {prereq_count} PREREQ edges")

        # 5. Topic nodes + PRECEDES ordering edges
        topic_node_count = 0
        for t in topics:
            await session.run("""
                CREATE (t:Topic {
                    topic_id:    $topic_id,
                    resource_id: $resource_id,
                    name:        $name
                })
            """,
                topic_id=t["topic_id"],
                resource_id=resource_id,
                name=t["topic_name"],
            )
            topic_node_count += 1

            # Link primary concepts to their topic
            for cid in (t["primary_concepts"] or []):
                try:
                    await session.run("""
                        MATCH (c:Concept {concept_id: $cid, resource_id: $rid})
                        MATCH (t:Topic {topic_id: $tid, resource_id: $rid})
                        CREATE (c)-[:BELONGS_TO]->(t)
                    """, cid=cid, tid=t["topic_id"], rid=resource_id)
                except Exception:
                    pass

        logger.info(f"Created {topic_node_count} Topic nodes")

        # Topic prereq ordering (PRECEDES)
        for t in topics:
            for prereq_tid in (t["prereq_topic_ids"] or []):
                try:
                    await session.run("""
                        MATCH (prereq:Topic {topic_id: $prereq_id, resource_id: $rid})
                        MATCH (curr:Topic   {topic_id: $curr_id,   resource_id: $rid})
                        CREATE (prereq)-[:PRECEDES]->(curr)
                    """, prereq_id=prereq_tid, curr_id=t["topic_id"], rid=resource_id)
                except Exception:
                    pass

    await driver.close()

    logger.info("=" * 60)
    logger.info(f"✅  Neo4j sync complete for resource {resource_id}")
    logger.info(f"    Nodes:  {len(concepts)} Concept + {topic_node_count} Topic")
    logger.info(f"    Edges:  {edge_count} semantic + {prereq_count} PREREQ")
    logger.info("=" * 60)


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(sync(rid))
