/**
 * Feature flags hook (PROD-014).
 *
 * Fetches server-side feature flags and provides a typed accessor.
 */

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';

export interface FeatureFlags {
  workspace_v2_enabled: boolean;
  active_learning_enabled: boolean;
  artifact_generation_enabled: boolean;
  notebooks_enabled: boolean;
}

const DEFAULT_FLAGS: FeatureFlags = {
  workspace_v2_enabled: true,
  active_learning_enabled: true,
  artifact_generation_enabled: true,
  notebooks_enabled: true,
};

export function useFeatureFlags(): FeatureFlags {
  const { data } = useQuery({
    queryKey: ['feature-flags'],
    queryFn: () => apiClient.get<FeatureFlags>('/flags'),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  return data ?? DEFAULT_FLAGS;
}
