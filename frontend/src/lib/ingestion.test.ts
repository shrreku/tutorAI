import { describe, expect, it } from 'vitest';

import {
  getLiveCapabilityProgress,
  getResourceDisplayStatus,
  hasActiveIngestionJob,
  isResourceDoubtReady,
  isResourceStudyReady,
} from './ingestion';

describe('ingestion helpers', () => {
  it('detects active ingestion jobs', () => {
    expect(hasActiveIngestionJob({ status: 'pending' } as never)).toBe(true);
    expect(hasActiveIngestionJob({ status: 'running' } as never)).toBe(true);
    expect(hasActiveIngestionJob({ status: 'completed' } as never)).toBe(false);
  });

  it('promotes live readiness from latest job progress', () => {
    const resource = {
      status: 'processing',
      capabilities: { study_ready: false, can_answer_doubts: false },
      latest_job: {
        status: 'running',
        capability_progress: {
          search_ready: true,
          doubt_ready: true,
          learn_ready: false,
        },
      },
    };

    expect(getLiveCapabilityProgress(resource as never)).toEqual({
      search_ready: true,
      doubt_ready: true,
      learn_ready: false,
    });
    expect(isResourceDoubtReady(resource as never)).toBe(true);
    expect(isResourceStudyReady(resource as never)).toBe(false);
  });

  it('keeps display status processing while background work is active', () => {
    const resource = {
      status: 'ready',
      capabilities: {},
      latest_job: { status: 'running' },
    };

    expect(getResourceDisplayStatus(resource as never)).toBe('processing');
  });

  it('treats normalized curriculum flags as study-ready', () => {
    const resource = {
      status: 'ready',
      capabilities: {
        curriculum_ready: true,
        has_topic_bundles: true,
        can_start_revision_session: true,
      },
      latest_job: { status: 'completed' },
    };

    expect(getLiveCapabilityProgress(resource as never)).toEqual({
      search_ready: false,
      doubt_ready: false,
      learn_ready: true,
    });
    expect(isResourceStudyReady(resource as never)).toBe(true);
  });
});