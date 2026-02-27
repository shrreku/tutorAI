import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  PaginatedResponse,
  Resource,
  ResourceTopicsResponse,
  IngestionStatus,
  Session,
  SessionDetail,
  SessionCreateRequest,
  TutorTurnRequest,
  TutorTurnResponse,
  Turn,
  TurnsResponse,
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
    list: (params?: { status?: string }) =>
      [...queryKeys.sessions.all, 'list', params] as const,
    detail: (id: string) => [...queryKeys.sessions.all, 'detail', id] as const,
    turns: (id: string) => [...queryKeys.sessions.all, 'turns', id] as const,
  },
};

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

export function useUploadResource() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: async ({ file, topic }: { file: File; topic?: string }) => {
      const formData = new FormData();
      formData.append('file', file);
      if (topic) {
        formData.append('topic', topic);
      }
      return apiClient.postForm<IngestionStatus>('/ingest/upload', formData);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.resources.all });
    },
  });
}

export function useResourceTopics(resourceId: string) {
  return useQuery({
    queryKey: [...queryKeys.resources.detail(resourceId), 'topics'] as const,
    queryFn: () => apiClient.get<ResourceTopicsResponse>(`/resources/${resourceId}/topics`),
    enabled: !!resourceId,
  });
}

// Session hooks
export function useSessions(params?: { status?: string }) {
  return useQuery({
    queryKey: queryKeys.sessions.list(params),
    queryFn: () =>
      apiClient.get<PaginatedResponse<Session>>('/sessions', {
        status: params?.status,
      } as Record<string, string>),
  });
}

export function useSession(id: string) {
  return useQuery({
    queryKey: queryKeys.sessions.detail(id),
    queryFn: () => apiClient.get<SessionDetail>(`/sessions/${id}`),
    enabled: !!id,
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (request: SessionCreateRequest) =>
      apiClient.post<Session>('/sessions/resource', request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions.all });
    },
  });
}

export function useEndSession() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (sessionId: string) =>
      apiClient.post<Session>(`/sessions/${sessionId}/end`),
    onSuccess: (_data: Session, sessionId: string) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.sessions.detail(sessionId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions.all });
    },
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

export function useSendMessage() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (request: TutorTurnRequest) =>
      apiClient.post<TutorTurnResponse>('/tutor/turn', request),
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
    },
  });
}
