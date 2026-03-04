import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  PaginatedResponse,
  Resource,
  ResourceDetail,
  ResourceTopicsResponse,
  IngestionStatus,
  ResourceKnowledgeBase,
  KnowledgeBaseUpdateRequest,
  Session,
  SessionDetail,
  SessionCreateRequest,
  TutorTurnRequest,
  TutorTurnResponse,
  Turn,
  TurnsResponse,
  UserSettings,
  UserSettingsUpdateRequest,
  SessionSummaryResponse,
  QuizGenerateRequest,
  QuizGenerateResponse,
  QuizAnswerRequest,
  QuizAnswerResponse,
  QuizResultsResponse,
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
  quiz: {
    all: ['quiz'] as const,
    results: (quizId: string) => [...queryKeys.quiz.all, 'results', quizId] as const,
  },
  user: {
    all: ['user'] as const,
    settings: () => [...queryKeys.user.all, 'settings'] as const,
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

export function useResource(resourceId: string) {
  return useQuery({
    queryKey: queryKeys.resources.detail(resourceId),
    queryFn: () => apiClient.get<ResourceDetail>(`/resources/${resourceId}`),
    enabled: !!resourceId,
  });
}

export function useRetryIngestion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (resourceId: string) =>
      apiClient.post<IngestionStatus>(`/ingest/retry/${resourceId}`),
    onSuccess: (_data: IngestionStatus, resourceId: string) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.resources.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.resources.detail(resourceId) });
      queryClient.invalidateQueries({ queryKey: [...queryKeys.resources.detail(resourceId), 'kb'] as const });
    },
  });
}

export function useDeleteResource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (resourceId: string) =>
      apiClient.delete<void>(`/resources/${resourceId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.resources.all });
    },
  });
}

export function useResourceKnowledgeBase(resourceId: string) {
  return useQuery({
    queryKey: [...queryKeys.resources.detail(resourceId), 'kb'] as const,
    queryFn: () => apiClient.get<ResourceKnowledgeBase>(`/resources/${resourceId}/knowledge-base`),
    enabled: !!resourceId,
  });
}

export function useUpdateResourceKnowledgeBase(resourceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: KnowledgeBaseUpdateRequest) =>
      apiClient.patch<ResourceKnowledgeBase>(`/resources/${resourceId}/knowledge-base`, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.resources.detail(resourceId) });
      queryClient.invalidateQueries({ queryKey: [...queryKeys.resources.detail(resourceId), 'kb'] as const });
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
      apiClient.post<SessionSummaryResponse>(`/sessions/${sessionId}/end`),
    onSuccess: (data: SessionSummaryResponse) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.sessions.detail(data.session_id),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions.all });
    },
  });
}

export function useSessionSummary(sessionId: string) {
  return useQuery({
    queryKey: [...queryKeys.sessions.detail(sessionId), 'summary'] as const,
    queryFn: () => apiClient.get<SessionSummaryResponse>(`/sessions/${sessionId}/summary`),
    enabled: !!sessionId,
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

// Quiz hooks
export function useGenerateQuiz() {
  return useMutation({
    mutationFn: (request: QuizGenerateRequest) =>
      apiClient.post<QuizGenerateResponse>('/quiz/generate', request),
  });
}

export function useSubmitQuizAnswer() {
  return useMutation({
    mutationFn: (request: QuizAnswerRequest) =>
      apiClient.post<QuizAnswerResponse>('/quiz/answer', request),
  });
}

export function useQuizResults(quizId: string) {
  return useQuery({
    queryKey: queryKeys.quiz.results(quizId),
    queryFn: () => apiClient.get<QuizResultsResponse>(`/quiz/${quizId}/results`),
    enabled: !!quizId,
  });
}
