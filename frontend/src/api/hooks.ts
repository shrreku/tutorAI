import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  PaginatedResponse,
  Resource,
  TutorTurnRequest,
  TutorTurnResponse,
  Turn,
  TurnsResponse,
  UserSettings,
  UserSettingsUpdateRequest,
  Notebook,
  NotebookCreateRequest,
  NotebookUpdateRequest,
  NotebookResource,
  NotebookResourceAttachRequest,
  NotebookSession,
  NotebookSessionCreateRequest,
  NotebookSessionDetail,
  NotebookProgress,
  NotebookArtifact,
  NotebookArtifactGenerateRequest,
} from '../types/api';

// Query keys
export const queryKeys = {
  resources: {
    all: ['resources'] as const,
    list: (params?: { status?: string; limit?: number; offset?: number }) =>
      [...queryKeys.resources.all, 'list', params] as const,
    detail: (id: string) => [...queryKeys.resources.all, 'detail', id] as const,
  },
  sessions: {
    all: ['sessions'] as const,
    detail: (id: string) => [...queryKeys.sessions.all, 'detail', id] as const,
    turns: (id: string) => [...queryKeys.sessions.all, 'turns', id] as const,
  },
  user: {
    all: ['user'] as const,
    settings: () => [...queryKeys.user.all, 'settings'] as const,
  },
  notebooks: {
    all: ['notebooks'] as const,
    list: () => [...queryKeys.notebooks.all, 'list'] as const,
    detail: (id: string) => [...queryKeys.notebooks.all, 'detail', id] as const,
    resources: (id: string) => [...queryKeys.notebooks.all, 'resources', id] as const,
    sessions: (id: string) => [...queryKeys.notebooks.all, 'sessions', id] as const,
    sessionDetail: (notebookId: string, sessionId: string) =>
      [...queryKeys.notebooks.all, 'sessions', notebookId, sessionId] as const,
    progress: (id: string) => [...queryKeys.notebooks.all, 'progress', id] as const,
    artifacts: (id: string, artifactType?: string) =>
      [...queryKeys.notebooks.all, 'artifacts', id, artifactType] as const,
  },
};

// Notebook hooks
export function useNotebooks() {
  return useQuery({
    queryKey: queryKeys.notebooks.list(),
    queryFn: () => apiClient.get<PaginatedResponse<Notebook>>('/notebooks'),
  });
}

export function useNotebook(notebookId: string) {
  return useQuery({
    queryKey: queryKeys.notebooks.detail(notebookId),
    queryFn: () => apiClient.get<Notebook>(`/notebooks/${notebookId}`),
    enabled: !!notebookId,
  });
}

export function useCreateNotebook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: NotebookCreateRequest) =>
      apiClient.post<Notebook>('/notebooks', request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.all });
    },
  });
}

export function useUpdateNotebook(notebookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: NotebookUpdateRequest) =>
      apiClient.patch<Notebook>(`/notebooks/${notebookId}`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.detail(notebookId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.list() });
    },
  });
}

export function useNotebookResources(notebookId: string) {
  return useQuery({
    queryKey: queryKeys.notebooks.resources(notebookId),
    queryFn: () => apiClient.get<PaginatedResponse<NotebookResource>>(`/notebooks/${notebookId}/resources`),
    enabled: !!notebookId,
  });
}

export function useAttachNotebookResource(notebookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: NotebookResourceAttachRequest) =>
      apiClient.post<NotebookResource>(`/notebooks/${notebookId}/resources`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.resources(notebookId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.progress(notebookId) });
    },
  });
}

export function useDetachNotebookResource(notebookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (resourceId: string) =>
      apiClient.delete<void>(`/notebooks/${notebookId}/resources/${resourceId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.resources(notebookId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.progress(notebookId) });
    },
  });
}

export function useNotebookSessions(notebookId: string) {
  return useQuery({
    queryKey: queryKeys.notebooks.sessions(notebookId),
    queryFn: () => apiClient.get<PaginatedResponse<NotebookSession>>(`/notebooks/${notebookId}/sessions`),
    enabled: !!notebookId,
  });
}

export function useNotebookSessionDetail(notebookId: string, sessionId: string) {
  return useQuery({
    queryKey: queryKeys.notebooks.sessionDetail(notebookId, sessionId),
    queryFn: () => apiClient.get<NotebookSessionDetail>(`/notebooks/${notebookId}/sessions/${sessionId}`),
    enabled: !!notebookId && !!sessionId,
  });
}

export function useCreateNotebookSession(notebookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: NotebookSessionCreateRequest) =>
      apiClient.post<NotebookSessionDetail>(`/notebooks/${notebookId}/sessions`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.sessions(notebookId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.progress(notebookId) });
    },
  });
}

export function useNotebookProgress(notebookId: string) {
  return useQuery({
    queryKey: queryKeys.notebooks.progress(notebookId),
    queryFn: () => apiClient.get<NotebookProgress>(`/notebooks/${notebookId}/progress`),
    enabled: !!notebookId,
  });
}

export function useNotebookArtifacts(notebookId: string, artifactType?: string) {
  return useQuery({
    queryKey: queryKeys.notebooks.artifacts(notebookId, artifactType),
    queryFn: () =>
      apiClient.get<PaginatedResponse<NotebookArtifact>>(`/notebooks/${notebookId}/artifacts`, {
        artifact_type: artifactType,
      } as Record<string, string>),
    enabled: !!notebookId,
  });
}

export function useGenerateNotebookArtifact(notebookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: NotebookArtifactGenerateRequest) =>
      apiClient.post<NotebookArtifact>(`/notebooks/${notebookId}/artifacts:generate`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.artifacts(notebookId) });
    },
  });
}

export function useSendNotebookMessage(notebookId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: TutorTurnRequest) =>
      apiClient.post<TutorTurnResponse>(`/tutor/notebooks/${notebookId}/turn`, request),
    onSuccess: (data: TutorTurnResponse, variables: TutorTurnRequest) => {
      queryClient.setQueryData<TurnsResponse | undefined>(
        queryKeys.sessions.turns(variables.session_id),
        (existing) => {
          const priorTurns = existing?.turns ?? [];
          const lastTurnIndex = priorTurns.length
            ? priorTurns[priorTurns.length - 1].turn_index
            : 0;
          const nextTurn: Turn = {
            turn_id: data.turn_id,
            turn_index: lastTurnIndex + 1,
            student_message: variables.message,
            tutor_response: data.response,
            tutor_question: data.tutor_question,
            pedagogical_action: data.step_transition,
            current_step: data.current_step,
            created_at: new Date().toISOString(),
          };
          return {
            session_id: existing?.session_id ?? variables.session_id,
            turns: [...priorTurns, nextTurn],
          };
        }
      );

      queryClient.invalidateQueries({
        queryKey: queryKeys.sessions.detail(variables.session_id),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks.progress(notebookId) });
    },
  });
}

// Resource hooks
export function useResources(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: queryKeys.resources.list(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<Resource>>('/resources', {
        status: params?.status,
        limit: params?.limit?.toString(),
        offset: params?.offset?.toString(),
      } as Record<string, string>),
  });
}

// Tutor hooks
export function useTurns(sessionId: string) {
  return useQuery({
    queryKey: queryKeys.sessions.turns(sessionId),
    queryFn: () => apiClient.get<TurnsResponse>(`/tutor/turns/${sessionId}`),
    enabled: !!sessionId,
  });
}

export function useUserSettings() {
  return useQuery({
    queryKey: queryKeys.user.settings(),
    queryFn: () => apiClient.get<UserSettings>('/users/me/settings'),
  });
}

export function useUpdateUserSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: UserSettingsUpdateRequest) =>
      apiClient.patch<UserSettings>('/users/me/settings', request),
    onSuccess: (data: UserSettings) => {
      queryClient.setQueryData(queryKeys.user.settings(), data);
    },
  });
}
