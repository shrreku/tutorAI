from __future__ import annotations

from typing import Any

from app.models.resource import (
    default_resource_capabilities,
    core_ready_capabilities,
    study_ready_capabilities,
    progressive_ready_capabilities,
)


def _job_capability_progress(latest_job: Any | None) -> dict[str, bool]:
    metrics = getattr(latest_job, "metrics", None) or {}
    if not isinstance(metrics, dict):
        return {}
    capability_progress = metrics.get("capability_progress")
    return capability_progress if isinstance(capability_progress, dict) else {}


def normalized_resource_capabilities(
    resource: Any, *, latest_job: Any | None = None
) -> dict[str, bool]:
    capabilities = default_resource_capabilities()
    existing = getattr(resource, "capabilities_json", None) or {}
    if isinstance(existing, dict):
        capabilities.update(existing)

    progress = _job_capability_progress(latest_job)

    is_core_ready = any(
        (
            progress.get("search_ready"),
            progress.get("doubt_ready"),
            capabilities.get("vector_search_ready"),
            capabilities.get("basic_tutoring_ready"),
            capabilities.get("can_search"),
            capabilities.get("can_answer_doubts"),
            capabilities.get("can_tutor_basic"),
            getattr(resource, "tutoring_ready_at", None) is not None,
            getattr(resource, "processed_at", None) is not None,
            getattr(resource, "status", None) == "ready",
        )
    )
    if is_core_ready:
        capabilities = core_ready_capabilities(capabilities)

    has_curriculum_ready = any(
        (
            progress.get("learn_ready"),
            capabilities.get("curriculum_ready"),
            capabilities.get("has_topic_bundles"),
            capabilities.get("has_curriculum_artifacts"),
            capabilities.get("can_start_learn_session"),
            capabilities.get("can_start_practice_session"),
            capabilities.get("can_start_revision_session"),
            getattr(resource, "curriculum_ready_at", None) is not None,
        )
    )

    has_study_ready = any(
        (
            has_curriculum_ready,
            capabilities.get("study_ready"),
            capabilities.get("has_concepts"),
            capabilities.get("concepts_ready"),
            getattr(resource, "study_ready_at", None) is not None,
            getattr(resource, "tutoring_ready_at", None) is not None,
        )
    )
    if has_study_ready:
        capabilities = study_ready_capabilities(
            capabilities,
            has_concepts=bool(
                capabilities.get("has_concepts")
                or capabilities.get("concepts_ready")
                or capabilities.get("study_ready")
                or getattr(resource, "study_ready_at", None) is not None
                or getattr(resource, "tutoring_ready_at", None) is not None
                or has_curriculum_ready
            ),
        )

    if has_curriculum_ready:
        capabilities.update(
            {
                "curriculum_ready": True,
                "has_topic_bundles": True,
                "has_curriculum_artifacts": True,
                "can_start_learn_session": True,
                "can_start_practice_session": True,
                "can_start_revision_session": True,
            }
        )

    return capabilities


def is_resource_doubt_ready(resource: Any, *, latest_job: Any | None = None) -> bool:
    capabilities = normalized_resource_capabilities(resource, latest_job=latest_job)
    return bool(
        capabilities.get("can_answer_doubts")
        or capabilities.get("basic_tutoring_ready")
        or capabilities.get("vector_search_ready")
    )


def is_resource_study_ready(resource: Any, *, latest_job: Any | None = None) -> bool:
    capabilities = normalized_resource_capabilities(resource, latest_job=latest_job)
    return bool(
        capabilities.get("study_ready")
        or capabilities.get("has_concepts")
        or capabilities.get("curriculum_ready")
        or capabilities.get("has_topic_bundles")
        or capabilities.get("can_start_learn_session")
        or capabilities.get("can_start_practice_session")
        or capabilities.get("can_start_revision_session")
        or capabilities.get("progressive_study_ready")
        or capabilities.get("has_partial_curriculum")
    )


def is_resource_progressively_ready(
    resource: Any, *, latest_job: Any | None = None
) -> bool:
    """True when at least one batch is study-ready (partial curriculum available)."""
    capabilities = normalized_resource_capabilities(resource, latest_job=latest_job)
    return bool(
        capabilities.get("progressive_study_ready")
        or capabilities.get("has_partial_curriculum")
        or int(capabilities.get("ready_batch_count", 0)) > 0
    )


def get_batch_progress(resource: Any) -> dict:
    """Return batch-level progress summary from capabilities."""
    capabilities = getattr(resource, "capabilities_json", None) or {}
    return {
        "ready_batch_count": int(capabilities.get("ready_batch_count", 0)),
        "total_batch_count": int(capabilities.get("total_batch_count", 0)),
        "progressive_study_ready": bool(capabilities.get("progressive_study_ready")),
        "has_partial_curriculum": bool(capabilities.get("has_partial_curriculum")),
        "supports_incremental_curriculum": bool(
            capabilities.get("supports_incremental_curriculum")
        ),
    }
