/**
 * Typed live session event contracts (PROD-012).
 *
 * Matches backend app/schemas/session_events.py exactly.
 * The workspace UI renders structured state changes from these events
 * instead of parsing raw tutor text.
 */

// ---------------------------------------------------------------------------
// Event type enum
// ---------------------------------------------------------------------------

export type SessionEventType =
  | 'session.started'
  | 'session.resumed'
  | 'session.completed'
  | 'session.brief'
  | 'tutor.message.delta'
  | 'tutor.message.completed'
  | 'session.objective.updated'
  | 'session.objective.completed'
  | 'session.mastery.updated'
  | 'artifact.started'
  | 'artifact.updated'
  | 'artifact.completed'
  | 'checkpoint.requested'
  | 'checkpoint.response.received'
  | 'source.citation.available'
  | 'warning.model_rerouted'
  | 'warning.rate_limited';

// ---------------------------------------------------------------------------
// Payload shapes
// ---------------------------------------------------------------------------

export interface ObjectiveSnapshot {
  objective_id: string;
  title: string;
  description?: string | null;
  primary_concepts: string[];
  support_concepts: string[];
  prereq_concepts: string[];
  step_count: number;
  status: 'pending' | 'active' | 'completed' | 'skipped';
  progress_pct: number;
}

export interface SessionBriefPayload {
  notebook_id: string;
  session_id: string;
  mode: string;
  scope_type: string;
  resource_count: number;
  objectives_count: number;
  objectives: ObjectiveSnapshot[];
  mastery_snapshot: Record<string, number>;
  weak_concepts: string[];
  session_overview?: string | null;
}

export interface StructuredContentBlock {
  block_type: 'text' | 'concept_card' | 'quiz_card' | 'checkpoint' | 'latex' | 'diagram' | 'code';
  content: string;
  metadata: Record<string, unknown>;
}

export interface TutorMessageDeltaPayload {
  turn_id: string;
  delta: string;
  content_type: 'text' | 'markdown' | 'latex' | 'concept_card' | 'quiz_card';
}

export interface TutorMessageCompletedPayload {
  turn_id: string;
  response: string;
  tutor_question?: string | null;
  content_type: string;
  current_step?: string | null;
  current_step_index: number;
  objective_id?: string | null;
  objective_title?: string | null;
  step_transition?: string | null;
  focus_concepts: string[];
  pedagogical_action?: string | null;
  structured_content?: StructuredContentBlock[] | null;
}

export interface ObjectiveUpdatedPayload {
  objective_id: string;
  title: string;
  status: 'pending' | 'active' | 'completed' | 'skipped';
  progress_pct: number;
  attempts: number;
  correct: number;
}

export interface MasteryUpdatedPayload {
  concept_id: string;
  previous_score: number;
  new_score: number;
  delta: number;
}

export interface ArtifactEventPayload {
  artifact_id: string;
  artifact_type: 'notes' | 'flashcards' | 'quiz' | 'revision_plan' | 'concept_card';
  status: 'generating' | 'ready' | 'error';
  payload_json?: Record<string, unknown> | null;
  source_session_ids: string[];
  source_resource_ids: string[];
  error_message?: string | null;
}

export interface CheckpointRequestedPayload {
  checkpoint_id: string;
  checkpoint_type: 'understanding' | 'recall' | 'application';
  question: string;
  concept_id?: string | null;
  options: string[];
  allow_freeform: boolean;
}

export interface CheckpointResponsePayload {
  checkpoint_id: string;
  response: string;
  is_correct?: boolean | null;
  score?: number | null;
  feedback?: string | null;
}

export interface SourceCitationPayload {
  citation_id: string;
  resource_id: string;
  resource_name?: string | null;
  chunk_ids: string[];
  page_numbers: number[];
  snippet?: string | null;
}

export interface WarningPayload {
  warning_type: string;
  message: string;
  selected_model_id?: string | null;
  routed_model_id?: string | null;
  reroute_reason?: string | null;
}

export interface SessionCompletedPayload {
  session_id: string;
  summary_text?: string | null;
  concepts_strong: string[];
  concepts_developing: string[];
  concepts_to_revisit: string[];
  objectives: ObjectiveSnapshot[];
  mastery_snapshot: Record<string, number>;
  turn_count: number;
  recommended_next?: string | null;
}

// ---------------------------------------------------------------------------
// Study map snapshot (returned in turn responses)
// ---------------------------------------------------------------------------

export interface StudyMapStepSnapshot {
  type: string;
  goal: string;
  status: 'completed' | 'active' | 'upcoming' | 'skipped';
}

export interface StudyMapObjectiveSnapshot {
  objective_id: string;
  title: string;
  status: 'completed' | 'active' | 'pending';
  primary_concepts: string[];
  support_concepts: string[];
  prereq_concepts: string[];
  steps: StudyMapStepSnapshot[];
  progress: Record<string, number>;
}

export interface StudyMapSnapshot {
  current_objective_index: number;
  current_step_index: number;
  total_objectives: number;
  ad_hoc_count: number;
  max_ad_hoc: number;
  last_decision?: string | null;
  last_transition?: string | null;
  last_ad_hoc_type?: string | null;
  session_complete: boolean;
  objectives: StudyMapObjectiveSnapshot[];
}

// ---------------------------------------------------------------------------
// Event envelope
// ---------------------------------------------------------------------------

export interface SessionEvent {
  event_type: SessionEventType;
  timestamp: string;
  session_id: string;
  notebook_id?: string | null;
  payload: Record<string, unknown>;
  is_persistent: boolean;
}

// ---------------------------------------------------------------------------
// Type-safe event helpers
// ---------------------------------------------------------------------------

export type SessionEventPayloadMap = {
  'session.started': SessionBriefPayload;
  'session.resumed': SessionBriefPayload;
  'session.completed': SessionCompletedPayload;
  'session.brief': SessionBriefPayload;
  'tutor.message.delta': TutorMessageDeltaPayload;
  'tutor.message.completed': TutorMessageCompletedPayload;
  'session.objective.updated': ObjectiveUpdatedPayload;
  'session.objective.completed': ObjectiveUpdatedPayload;
  'session.mastery.updated': MasteryUpdatedPayload;
  'artifact.started': ArtifactEventPayload;
  'artifact.updated': ArtifactEventPayload;
  'artifact.completed': ArtifactEventPayload;
  'checkpoint.requested': CheckpointRequestedPayload;
  'checkpoint.response.received': CheckpointResponsePayload;
  'source.citation.available': SourceCitationPayload;
  'warning.model_rerouted': WarningPayload;
  'warning.rate_limited': WarningPayload;
};

export function parseSessionEvent<T extends SessionEventType>(
  event: SessionEvent,
  expectedType: T,
): SessionEventPayloadMap[T] | null {
  if (event.event_type !== expectedType) return null;
  return event.payload as unknown as SessionEventPayloadMap[T];
}
