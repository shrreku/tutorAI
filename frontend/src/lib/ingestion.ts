import type { IngestionCapabilityProgress, IngestionStatus, Resource } from '../types/api';

type LiveResource = Pick<Resource, 'status' | 'capabilities' | 'latest_job'>;

export function hasActiveIngestionJob(job?: IngestionStatus | null): boolean {
  if (!job) return false;
  return job.status !== 'completed' && job.status !== 'failed';
}

export function getLiveCapabilityProgress(resource?: LiveResource | null): IngestionCapabilityProgress {
  const capabilities = resource?.capabilities ?? {};
  const progress = resource?.latest_job?.capability_progress;
  const curriculumReady = Boolean(
    capabilities.study_ready
    || capabilities.curriculum_ready
    || capabilities.has_topic_bundles
    || capabilities.has_curriculum_artifacts
    || capabilities.can_start_learn_session
    || capabilities.can_start_practice_session
    || capabilities.can_start_revision_session,
  );

  return {
    search_ready: Boolean(
      progress?.search_ready
      || capabilities.can_search
      || capabilities.vector_search_ready,
    ),
    doubt_ready: Boolean(
      progress?.doubt_ready
      || capabilities.can_answer_doubts
      || capabilities.basic_tutoring_ready,
    ),
    learn_ready: Boolean(
      progress?.learn_ready
      || curriculumReady
      || capabilities.has_concepts
      || capabilities.concepts_ready,
    ),
  };
}

export function isResourceDoubtReady(resource?: LiveResource | null): boolean {
  const progress = getLiveCapabilityProgress(resource);
  return progress.doubt_ready || progress.learn_ready;
}

export function isResourceStudyReady(resource?: LiveResource | null): boolean {
  return getLiveCapabilityProgress(resource).learn_ready;
}

export function getResourceDisplayStatus(resource?: LiveResource | null): string {
  if (!resource) return 'processing';
  if (hasActiveIngestionJob(resource.latest_job)) return 'processing';
  return resource.status;
}

export function getLiveIngestionJob(resource?: LiveResource | null): IngestionStatus | null {
  return hasActiveIngestionJob(resource?.latest_job) ? resource?.latest_job ?? null : null;
}