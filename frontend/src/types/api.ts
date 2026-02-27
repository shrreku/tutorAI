// API Types matching backend schemas

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ErrorResponse {
  code: string;
  message: string;
  details?: ErrorDetail[];
  request_id?: string;
}

export interface ErrorDetail {
  field?: string;
  message: string;
}

// Resource types
export interface Resource {
  id: string;
  filename: string;
  topic: string | null;
  status: string;
  uploaded_at: string;
  processed_at: string | null;
}

export interface ResourceDetail extends Resource {
  chunk_count: number;
  concept_count: number;
  topic_bundles: TopicBundle[];
}

export interface TopicBundle {
  topic_id: string;
  topic_name: string;
  primary_concepts: string[];
}

// Ingestion types
export interface IngestionStatus {
  job_id: string;
  resource_id: string;
  status: string;
  current_stage: string | null;
  progress_percent: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

// Session types
export interface Session {
  id: string;
  user_id: string;
  resource_id: string | null;
  topic: string | null;
  status: string;
  current_step: string | null;
  current_concept_id: string | null;
  mastery: Record<string, number> | null;
  created_at: string;
}

export interface SessionDetail extends Session {
  plan_state: Record<string, unknown> | null;
  turn_count: number;
}

export interface SessionCreateRequest {
  resource_id: string;
  topic?: string;
  selected_topics?: string[];
}

// Tutor types
export interface TutorTurnRequest {
  session_id: string;
  message: string;
}

export interface TutorTurnResponse {
  turn_id: string;
  response: string;
  tutor_question: string | null;
  current_step: string | null;
  current_step_index: number;
  objective_id: string | null;
  objective_title: string | null;
  step_transition: string | null;
  focus_concepts: string[];
  mastery_update: Record<string, number> | null;
  evaluation: EvaluationResult | null;
  session_complete: boolean;
  awaiting_evaluation: boolean;
}

export interface EvaluationResult {
  overall_score: number;
  correctness_label: 'correct' | 'partial' | 'incorrect' | 'unclear';
  multi_concept: boolean;
  overall_feedback: string | null;
  misconceptions: string[];
}

export interface Turn {
  turn_id: string;
  turn_index: number;
  student_message: string;
  tutor_response: string;
  tutor_question: string | null;
  pedagogical_action: string | null;
  current_step: string | null;
  created_at: string;
}

export interface TurnsResponse {
  session_id: string;
  turns: Turn[];
}

// Topic selection types
export interface TopicConceptDetail {
  concept_id: string;
  teach_count: number;
  importance: number | null;
  role: 'primary' | 'support';
}

export interface TopicInfo {
  topic_id: string;
  topic_name: string;
  primary_concepts: string[];
  support_concepts: string[];
  concept_count: number;
  concept_details: TopicConceptDetail[];
  prereq_topic_ids: string[];
}

export interface ResourceTopicsResponse {
  resource_id: string;
  resource_name: string;
  topic: string | null;
  total_concepts: number;
  topics: TopicInfo[];
}

// Health types
export interface HealthResponse {
  status: string;
  service: string;
  timestamp?: string;
}
