from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.repositories.notebook_repo import (
    NotebookPlanningStateRepository,
    NotebookProgressRepository,
    NotebookSessionRepository,
)
from app.db.repositories.session_repo import SessionRepository
from app.models.knowledge_base import (
    ResourceConceptGraph,
    ResourceConceptStats,
    ResourceLearningObjective,
    ResourcePrereqHint,
    ResourceTopicBundle,
)
from app.models.notebook import NotebookPlanningState, NotebookProgress, NotebookResource

MASTERED_THRESHOLD = 0.7
WEAK_THRESHOLD = 0.4


def _pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100.0, 2)


def _stringify_list(values: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values or []:
        if value is None:
            continue
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_compatible(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _objective_concepts(objective: dict[str, Any]) -> list[str]:
    scope = objective.get("concept_scope") or {}
    return _stringify_list(
        list(scope.get("primary") or [])
        + list(scope.get("support") or [])
        + list(scope.get("prereq") or [])
    )


def _objective_primary_concepts(objective: dict[str, Any]) -> list[str]:
    scope = objective.get("concept_scope") or {}
    return _stringify_list(scope.get("primary") or [])


def _objective_status(progress: dict[str, Any], mastery_snapshot: dict[str, float]) -> str:
    attempts = _safe_int(progress.get("attempts"))
    steps_completed = _safe_int(progress.get("steps_completed"))
    steps_skipped = _safe_int(progress.get("steps_skipped"))
    concept_scores = [
        _safe_float(mastery_snapshot.get(concept))
        for concept in _stringify_list(progress.get("primary_concepts") or [])
        if concept in mastery_snapshot
    ]
    mastered = bool(concept_scores) and min(concept_scores) >= MASTERED_THRESHOLD
    if mastered:
        return "mastered"
    if attempts > 0 or steps_completed > 0:
        return "taught"
    if steps_skipped > 0:
        return "deferred"
    return "planned"


class NotebookPlanningStateService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.notebook_session_repo = NotebookSessionRepository(db)
        self.session_repo = SessionRepository(db)
        self.progress_repo = NotebookProgressRepository(db)
        self.planning_state_repo = NotebookPlanningStateRepository(db)

    async def sync_for_session(
        self,
        session_id: uuid.UUID | str,
    ) -> Optional[dict[str, Any]]:
        notebook_link = await self.notebook_session_repo.get_by_session_id(
            uuid.UUID(str(session_id))
        )
        if not notebook_link:
            return None
        return await self.sync_notebook(notebook_link.notebook_id)

    async def sync_notebook(
        self,
        notebook_id: uuid.UUID | str,
    ) -> dict[str, Any]:
        notebook_uuid = uuid.UUID(str(notebook_id))
        links = await self.notebook_session_repo.get_by_notebook(
            notebook_uuid, limit=1000, offset=0
        )
        sessions = []
        for link in links:
            session = await self.session_repo.get_by_id(link.session_id)
            if session:
                sessions.append(session)

        aggregate = self._aggregate_progress(sessions)
        active_resource_ids = await self._active_resource_ids(notebook_uuid)
        knowledge_state = _json_compatible(
            await self._build_knowledge_state(notebook_uuid, active_resource_ids)
        )
        learner_state = _json_compatible(
            await self._build_learner_state(notebook_uuid, aggregate, sessions)
        )
        planner_state = _json_compatible(self._build_planner_state(
            notebook_uuid,
            sessions,
            aggregate,
            knowledge_state,
            learner_state,
        ))
        coverage_snapshot = _json_compatible(self._build_coverage_snapshot(
            knowledge_state,
            learner_state,
            planner_state,
        ))
        planning_metadata = _json_compatible(
            {
                "last_sync_source": "notebook_planning_service",
                "session_count": len(sessions),
            }
        )

        progress = await self.progress_repo.get_by_notebook(notebook_uuid)
        if not progress:
            progress = NotebookProgress(
                notebook_id=notebook_uuid,
                mastery_snapshot=aggregate["mastery_snapshot"],
                objective_progress_snapshot=aggregate["objective_progress_snapshot"],
                weak_concepts_snapshot=aggregate["weak_concepts_snapshot"],
            )
            progress = await self.progress_repo.create(progress)
        else:
            progress.mastery_snapshot = aggregate["mastery_snapshot"]
            progress.objective_progress_snapshot = aggregate[
                "objective_progress_snapshot"
            ]
            progress.weak_concepts_snapshot = aggregate["weak_concepts_snapshot"]
            self.db.add(progress)

        planning_state = await self.planning_state_repo.get_by_notebook(notebook_uuid)
        if not planning_state:
            planning_state = NotebookPlanningState(
                notebook_id=notebook_uuid,
                revision=1,
                knowledge_state=knowledge_state,
                learner_state=learner_state,
                planner_state=planner_state,
                coverage_snapshot=coverage_snapshot,
                planning_metadata=planning_metadata,
            )
            planning_state = await self.planning_state_repo.create(planning_state)
        else:
            changed = any(
                getattr(planning_state, field) != value
                for field, value in (
                    ("knowledge_state", knowledge_state),
                    ("learner_state", learner_state),
                    ("planner_state", planner_state),
                    ("coverage_snapshot", coverage_snapshot),
                )
            )
            planning_state.knowledge_state = knowledge_state
            planning_state.learner_state = learner_state
            planning_state.planner_state = planner_state
            planning_state.coverage_snapshot = coverage_snapshot
            planning_state.planning_metadata = planning_metadata
            if changed:
                planning_state.revision = _safe_int(planning_state.revision, 0) + 1
            self.db.add(planning_state)
            flag_modified(planning_state, "knowledge_state")
            flag_modified(planning_state, "learner_state")
            flag_modified(planning_state, "planner_state")
            flag_modified(planning_state, "coverage_snapshot")
            flag_modified(planning_state, "planning_metadata")

        await self.db.flush()
        await self.db.refresh(planning_state)

        state_payload = self.serialize_state(planning_state)
        return {
            "notebook_id": str(notebook_uuid),
            "aggregate": aggregate,
            "coverage_snapshot": coverage_snapshot,
            "notebook_planning_state": state_payload,
        }

    def build_planning_context(
        self,
        notebook_state_payload: dict[str, Any] | None,
        *,
        mode: str,
        topic: str | None,
        selected_topics: list[str] | None,
        personalization_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        state = deepcopy(notebook_state_payload or {})
        knowledge_state = deepcopy(state.get("knowledge_state") or {})
        resource_ids = list(knowledge_state.get("resource_ids") or [])
        return {
            "mode": mode,
            "topic": topic,
            "requested_topic": topic,
            "selected_topics": list(selected_topics or []),
            "resource_ids": resource_ids,
            "scope_type": "notebook",
            "notebook_id": state.get("notebook_id"),
            "personalization": deepcopy(personalization_snapshot or {}),
            "knowledge_state": knowledge_state,
            "learner_state": deepcopy(state.get("learner_state") or {}),
            "planner_state": deepcopy(state.get("planner_state") or {}),
            "coverage_snapshot": deepcopy(state.get("coverage_snapshot") or {}),
        }

    def serialize_state(self, planning_state: NotebookPlanningState | None) -> dict[str, Any] | None:
        if not planning_state:
            return None
        return _json_compatible({
            "notebook_id": str(planning_state.notebook_id),
            "revision": _safe_int(planning_state.revision, 1),
            "knowledge_state": deepcopy(planning_state.knowledge_state or {}),
            "learner_state": deepcopy(planning_state.learner_state or {}),
            "planner_state": deepcopy(planning_state.planner_state or {}),
            "coverage_snapshot": deepcopy(planning_state.coverage_snapshot or {}),
            "updated_at": planning_state.updated_at,
        })

    async def _active_resource_ids(self, notebook_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.db.execute(
            select(NotebookResource.resource_id)
            .where(NotebookResource.notebook_id == notebook_id)
            .where(NotebookResource.is_active.is_(True))
        )
        return [row[0] for row in rows.all()]

    def _aggregate_progress(self, sessions: list[Any]) -> dict[str, Any]:
        mastery_accumulator: dict[str, float] = {}
        mastery_counts: dict[str, int] = {}
        objective_progress: dict[str, dict[str, Any]] = {}
        completed_sessions_count = 0

        for session in sessions:
            if getattr(session, "status", None) == "completed":
                completed_sessions_count += 1

            for concept, score in (getattr(session, "mastery", None) or {}).items():
                numeric_score = _safe_float(score, None)
                if numeric_score is None:
                    continue
                mastery_accumulator[concept] = mastery_accumulator.get(concept, 0.0) + numeric_score
                mastery_counts[concept] = mastery_counts.get(concept, 0) + 1

            plan_state = getattr(session, "plan_state", None) or {}
            objective_queue = list(plan_state.get("objective_queue") or [])
            queue_by_id = {
                str(objective.get("objective_id") or f"obj_{index}"): objective
                for index, objective in enumerate(objective_queue)
            }
            for objective_id, progress in (plan_state.get("objective_progress") or {}).items():
                current = objective_progress.setdefault(
                    objective_id,
                    {
                        "attempts": 0,
                        "correct": 0,
                        "steps_completed": 0,
                        "steps_skipped": 0,
                        "session_ids": [],
                        "title": (queue_by_id.get(objective_id) or {}).get("title"),
                        "primary_concepts": _objective_primary_concepts(
                            queue_by_id.get(objective_id) or {}
                        ),
                    },
                )
                current["attempts"] += _safe_int(progress.get("attempts"))
                current["correct"] += _safe_int(progress.get("correct"))
                current["steps_completed"] += _safe_int(progress.get("steps_completed"))
                current["steps_skipped"] += _safe_int(progress.get("steps_skipped"))
                session_id = str(getattr(session, "id", ""))
                if session_id and session_id not in current["session_ids"]:
                    current["session_ids"].append(session_id)

        mastery_snapshot = {
            concept: round(mastery_accumulator[concept] / mastery_counts[concept], 4)
            for concept in mastery_accumulator
            if mastery_counts.get(concept, 0) > 0
        }
        weak_concepts_snapshot = [
            concept
            for concept, score in mastery_snapshot.items()
            if _safe_float(score) < WEAK_THRESHOLD
        ]

        return {
            "mastery_snapshot": mastery_snapshot,
            "objective_progress_snapshot": objective_progress,
            "weak_concepts_snapshot": weak_concepts_snapshot,
            "sessions_count": len(sessions),
            "completed_sessions_count": completed_sessions_count,
        }

    async def _build_knowledge_state(
        self,
        notebook_id: uuid.UUID,
        resource_ids: list[uuid.UUID],
    ) -> dict[str, Any]:
        concept_rows = (
            await self.db.execute(
                select(ResourceConceptStats).where(ResourceConceptStats.resource_id.in_(resource_ids))
            )
        ).scalars().all() if resource_ids else []
        topic_rows = (
            await self.db.execute(
                select(ResourceTopicBundle).where(ResourceTopicBundle.resource_id.in_(resource_ids))
            )
        ).scalars().all() if resource_ids else []
        objective_rows = (
            await self.db.execute(
                select(ResourceLearningObjective).where(
                    ResourceLearningObjective.resource_id.in_(resource_ids)
                )
            )
        ).scalars().all() if resource_ids else []
        prereq_rows = (
            await self.db.execute(
                select(ResourcePrereqHint).where(ResourcePrereqHint.resource_id.in_(resource_ids))
            )
        ).scalars().all() if resource_ids else []
        graph_rows = (
            await self.db.execute(
                select(ResourceConceptGraph).where(
                    ResourceConceptGraph.resource_id.in_(resource_ids)
                )
            )
        ).scalars().all() if resource_ids else []

        concepts: dict[str, dict[str, Any]] = {}
        for row in concept_rows:
            current = concepts.setdefault(
                row.concept_id,
                {
                    "concept_id": row.concept_id,
                    "teach_count": 0,
                    "mention_count": 0,
                    "importance_score": 0.0,
                    "concept_type": row.concept_type,
                    "bloom_level": row.bloom_level,
                    "topo_order": row.topo_order,
                    "resource_ids": [],
                },
            )
            current["teach_count"] += _safe_int(row.teach_count)
            current["mention_count"] += _safe_int(row.mention_count)
            current["importance_score"] = max(
                _safe_float(current.get("importance_score")),
                _safe_float(row.importance_score),
            )
            if current.get("topo_order") is None and row.topo_order is not None:
                current["topo_order"] = row.topo_order
            resource_id = str(row.resource_id)
            if resource_id not in current["resource_ids"]:
                current["resource_ids"].append(resource_id)

        topic_map: dict[str, dict[str, Any]] = {}
        for row in topic_rows:
            key = row.topic_id or row.topic_name
            current = topic_map.setdefault(
                key,
                {
                    "topic_id": row.topic_id,
                    "topic_name": row.topic_name,
                    "primary_concepts": [],
                    "support_concepts": [],
                    "prereq_topic_ids": _stringify_list(row.prereq_topic_ids or []),
                },
            )
            for concept in _stringify_list(row.primary_concepts or []):
                if concept not in current["primary_concepts"]:
                    current["primary_concepts"].append(concept)
            for concept in _stringify_list(row.support_concepts or []):
                if concept not in current["support_concepts"]:
                    current["support_concepts"].append(concept)

        objective_texts = []
        seen_objectives: set[str] = set()
        for row in objective_rows:
            text = str(row.objective_text or "").strip()
            if not text or text in seen_objectives:
                continue
            seen_objectives.add(text)
            objective_texts.append(
                {
                    "objective_text": text,
                    "specificity": row.specificity,
                    "resource_id": str(row.resource_id),
                }
            )

        prereq_hints = []
        for row in prereq_rows:
            prereq_hints.append(
                {
                    "source": row.source_concept_id,
                    "target": row.target_concept_id,
                    "support_count": _safe_int(row.support_count),
                }
            )

        graph_edges = []
        for row in graph_rows:
            graph_edges.append(
                {
                    "source": row.source_concept_id,
                    "target": row.target_concept_id,
                    "relation_type": row.relation_type,
                    "confidence": _safe_float(row.confidence),
                    "assoc_weight": _safe_float(row.assoc_weight),
                }
            )

        ordered_concepts = sorted(
            concepts.values(),
            key=lambda item: (
                item.get("topo_order") is None,
                item.get("topo_order") if item.get("topo_order") is not None else 10**9,
                -_safe_int(item.get("teach_count")),
                -_safe_float(item.get("importance_score")),
                item.get("concept_id") or "",
            ),
        )

        return {
            "version": 1,
            "notebook_id": str(notebook_id),
            "resource_ids": [str(resource_id) for resource_id in resource_ids],
            "concepts": ordered_concepts,
            "topics": list(topic_map.values()),
            "learning_objectives": objective_texts,
            "prereq_hints": prereq_hints[:120],
            "concept_graph": graph_edges[:160],
            "total_concepts": len(ordered_concepts),
            "total_topics": len(topic_map),
        }

    async def _build_learner_state(
        self,
        notebook_id: uuid.UUID,
        aggregate: dict[str, Any],
        sessions: list[Any],
    ) -> dict[str, Any]:
        recent_sessions = []
        for session in sessions[:5]:
            plan = getattr(session, "plan_state", None) or {}
            recent_sessions.append(
                {
                    "session_id": str(session.id),
                    "status": session.status,
                    "mode": plan.get("mode"),
                    "topic": plan.get("active_topic"),
                    "updated_at": session.updated_at,
                }
            )
        return {
            "version": 1,
            "notebook_id": str(notebook_id),
            "mastery_snapshot": deepcopy(aggregate["mastery_snapshot"]),
            "weak_concepts": list(aggregate["weak_concepts_snapshot"]),
            "mastered_concepts": [
                concept
                for concept, score in (aggregate["mastery_snapshot"] or {}).items()
                if _safe_float(score) >= MASTERED_THRESHOLD
            ],
            "recent_sessions": recent_sessions,
        }

    def _build_planner_state(
        self,
        notebook_id: uuid.UUID,
        sessions: list[Any],
        aggregate: dict[str, Any],
        knowledge_state: dict[str, Any],
        learner_state: dict[str, Any],
    ) -> dict[str, Any]:
        planned_concepts: set[str] = set()
        taught_concepts: set[str] = set()
        mastered_concepts: set[str] = set(learner_state.get("mastered_concepts") or [])
        deferred_concepts: set[str] = set()
        planned_objectives: dict[str, dict[str, Any]] = {}
        active_session_id: str | None = None

        mastery_snapshot = aggregate.get("mastery_snapshot") or {}
        progress_snapshot = aggregate.get("objective_progress_snapshot") or {}

        for session in sessions:
            plan = getattr(session, "plan_state", None) or {}
            if getattr(session, "status", None) == "active" and active_session_id is None:
                active_session_id = str(session.id)
            for index, objective in enumerate(plan.get("objective_queue") or []):
                objective_id = str(objective.get("objective_id") or f"obj_{index}")
                objective_progress = progress_snapshot.get(objective_id) or {}
                all_concepts = _objective_concepts(objective)
                primary_concepts = _objective_primary_concepts(objective)
                planned_concepts.update(all_concepts)
                status = _objective_status(
                    {
                        **objective_progress,
                        "primary_concepts": primary_concepts,
                    },
                    mastery_snapshot,
                )
                if status in {"taught", "mastered"}:
                    taught_concepts.update(all_concepts)
                if status == "mastered":
                    mastered_concepts.update(primary_concepts or all_concepts)
                if status == "deferred":
                    deferred_concepts.update(all_concepts)
                planned_objectives[objective_id] = {
                    "objective_id": objective_id,
                    "title": objective.get("title"),
                    "status": status,
                    "primary_concepts": primary_concepts,
                    "all_concepts": all_concepts,
                    "session_id": str(session.id),
                    "mode": plan.get("mode"),
                }

        total_objective_candidates = max(
            len(planned_objectives),
            len(knowledge_state.get("learning_objectives") or []),
        )
        return {
            "version": 1,
            "notebook_id": str(notebook_id),
            "active_session_id": active_session_id,
            "planned_concepts": sorted(planned_concepts),
            "taught_concepts": sorted(taught_concepts),
            "mastered_concepts": sorted(mastered_concepts),
            "deferred_concepts": sorted(deferred_concepts),
            "planned_objectives": list(planned_objectives.values()),
            "planned_objective_ids": sorted(planned_objectives.keys()),
            "planned_objective_count": len(planned_objectives),
            "candidate_objective_count": total_objective_candidates,
        }

    def _build_coverage_snapshot(
        self,
        knowledge_state: dict[str, Any],
        learner_state: dict[str, Any],
        planner_state: dict[str, Any],
    ) -> dict[str, Any]:
        total_concepts = _safe_int(knowledge_state.get("total_concepts"))
        total_objectives = max(
            _safe_int(planner_state.get("candidate_objective_count")),
            len(knowledge_state.get("learning_objectives") or []),
            len(planner_state.get("planned_objectives") or []),
        )
        planned_concepts = set(planner_state.get("planned_concepts") or [])
        taught_concepts = set(planner_state.get("taught_concepts") or [])
        mastered_concepts = set(planner_state.get("mastered_concepts") or [])
        planned_objectives = planner_state.get("planned_objectives") or []
        taught_objectives = [
            objective for objective in planned_objectives if objective.get("status") in {"taught", "mastered"}
        ]
        mastered_objectives = [
            objective for objective in planned_objectives if objective.get("status") == "mastered"
        ]

        topic_coverage = []
        for topic in knowledge_state.get("topics") or []:
            topic_concepts = set(
                _stringify_list(topic.get("primary_concepts") or [])
                + _stringify_list(topic.get("support_concepts") or [])
            )
            if not topic_concepts:
                continue
            topic_coverage.append(
                {
                    "topic_id": topic.get("topic_id"),
                    "topic_name": topic.get("topic_name"),
                    "concept_count": len(topic_concepts),
                    "planned_count": len(topic_concepts & planned_concepts),
                    "taught_count": len(topic_concepts & taught_concepts),
                    "mastered_count": len(topic_concepts & mastered_concepts),
                    "planned_percent": _pct(len(topic_concepts & planned_concepts), len(topic_concepts)),
                    "taught_percent": _pct(len(topic_concepts & taught_concepts), len(topic_concepts)),
                    "mastered_percent": _pct(len(topic_concepts & mastered_concepts), len(topic_concepts)),
                }
            )

        return {
            "total_concepts": total_concepts,
            "planned_concepts": len(planned_concepts),
            "taught_concepts": len(taught_concepts),
            "mastered_concepts": len(mastered_concepts),
            "planned_percent": _pct(len(planned_concepts), total_concepts),
            "taught_percent": _pct(len(taught_concepts), total_concepts),
            "mastered_percent": _pct(len(mastered_concepts), total_concepts),
            "total_objectives": total_objectives,
            "planned_objectives": len(planned_objectives),
            "taught_objectives": len(taught_objectives),
            "mastered_objectives": len(mastered_objectives),
            "objective_planned_percent": _pct(len(planned_objectives), total_objectives),
            "objective_taught_percent": _pct(len(taught_objectives), total_objectives),
            "objective_mastered_percent": _pct(len(mastered_objectives), total_objectives),
            "topic_coverage": topic_coverage,
        }
