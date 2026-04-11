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
  lifecycle_status?: string | null;
  processing_profile?: string | null;
  capabilities?: Record<string, boolean | number>;
  uploaded_at: string;
  processed_at: string | null;
  latest_job?: IngestionStatus | null;
}

export interface ResourceDetail extends Resource {
  chunk_count: number;
  concept_count: number;
  topic_bundles: TopicBundle[];
  artifacts?: ResourceArtifact[];
}

export interface ResourceArtifact {
  id: string;
  resource_id?: string | null;
  notebook_id?: string | null;
  scope_type: string;
  scope_key: string;
  artifact_kind: string;
  status: string;
  version: string;
  payload_json?: Record<string, unknown> | null;
  source_chunk_ids?: string[] | null;
  content_hash?: string | null;
  generated_at: string;
  error_message?: string | null;
}

export interface TopicBundle {
  topic_id: string;
  topic_name: string;
  primary_concepts: string[];
}

export interface TopicBundleEditable extends TopicBundle {
  support_concepts: string[];
  prereq_topic_ids: string[];
}

// Ingestion types
export interface IngestionStatus {
  job_id: string;
  resource_id: string;
  status: string;
  job_kind?: string;
  requested_capability?: string | null;
  scope_type?: string | null;
  scope_key?: string | null;
  current_stage: string | null;
  progress_percent: number;
  error_message: string | null;
  error_stage?: string | null;
  resumable?: boolean;
  resume_hint?: string | null;
  last_completed_stage?: string | null;
  started_at: string | null;
  completed_at: string | null;
  document_metrics?: IngestionDocumentMetrics | null;
  capability_progress?: IngestionCapabilityProgress | null;
  billing?: IngestionBillingStatus | null;
  curriculum_billing?: IngestionCurriculumBillingStatus | null;
  async_byok?: IngestionAsyncByokStatus | null;
}

export interface IngestionDocumentMetrics {
  page_count_actual: number;
  section_count: number;
  chunk_count_actual: number;
  token_count_actual: number;
}

export interface IngestionCapabilityProgress {
  search_ready: boolean;
  doubt_ready: boolean;
  learn_ready: boolean;
  ready_batch_count?: number;
  total_batch_count?: number;
  progressive_study_ready?: boolean;
}

export interface IngestionBillingStatus {
  uses_platform_credits: boolean;
  estimated_credits: number;
  reserved_credits: number;
  actual_credits?: number | null;
  status: string;
  release_reason?: string | null;
  file_size_bytes: number;
}

export interface IngestionCurriculumBillingStatus {
  estimated_credits_low: number;
  estimated_credits_high: number;
  reserved_credits: number;
  actual_credits?: number | null;
  status: string;
  operation_id?: string | null;
  release_reason?: string | null;
}

export interface IngestionAsyncByokStatus {
  enabled: boolean;
  escrow_id?: string | null;
  provider_name?: string | null;
  status: string;
  expires_at?: string | null;
  revoked_at?: string | null;
}

export interface KnowledgeBaseConcept {
  concept_id: string;
  teach_count: number;
  mention_count: number;
  importance_score: number | null;
  concept_type: string | null;
  bloom_level: string | null;
  topo_order: number | null;
}

export interface KnowledgeBaseEdge {
  source_concept_id: string;
  target_concept_id: string;
  relation_type: string;
  assoc_weight: number | null;
  confidence: number | null;
}

export interface ResourceKnowledgeBase {
  resource_id: string;
  resource_name: string;
  topic: string | null;
  status: string;
  chunk_count: number;
  concept_count: number;
  graph_edge_count: number;
  concepts: KnowledgeBaseConcept[];
  edges: KnowledgeBaseEdge[];
  topic_bundles: TopicBundleEditable[];
  latest_job: IngestionStatus | null;
}

export interface KnowledgeBaseConceptOverride {
  concept_id: string;
  importance_score?: number | null;
  concept_type?: string | null;
  bloom_level?: string | null;
  topo_order?: number | null;
}

export interface KnowledgeBaseTopicBundleUpdate {
  topic_id: string;
  topic_name: string;
  primary_concepts: string[];
  support_concepts: string[];
  prereq_topic_ids: string[];
}

export interface KnowledgeBaseEdgeUpdate {
  source_concept_id: string;
  target_concept_id: string;
  relation_type: string;
  assoc_weight?: number | null;
  confidence?: number | null;
}

export interface KnowledgeBaseConceptRename {
  from_concept_id: string;
  to_concept_id: string;
}

export interface KnowledgeBaseGraphOps {
  add_concepts: string[];
  remove_concepts: string[];
  rename_concepts: KnowledgeBaseConceptRename[];
  add_edges: KnowledgeBaseEdgeUpdate[];
  remove_edges: KnowledgeBaseEdgeUpdate[];
}

export interface KnowledgeBaseUpdateRequest {
  topic?: string | null;
  concept_overrides: KnowledgeBaseConceptOverride[];
  graph_ops?: KnowledgeBaseGraphOps;
  topic_bundles?: KnowledgeBaseTopicBundleUpdate[];
}

export interface CoverageTopicSnapshot {
  topic_id?: string | null;
  topic_name?: string | null;
  concept_count: number;
  planned_count: number;
  taught_count: number;
  mastered_count: number;
  planned_percent: number;
  taught_percent: number;
  mastered_percent: number;
}

export interface CoverageSnapshot {
  total_concepts: number;
  planned_concepts: number;
  taught_concepts: number;
  mastered_concepts: number;
  planned_percent: number;
  taught_percent: number;
  mastered_percent: number;
  total_objectives: number;
  planned_objectives: number;
  taught_objectives: number;
  mastered_objectives: number;
  objective_planned_percent: number;
  objective_taught_percent: number;
  objective_mastered_percent: number;
  topic_coverage: CoverageTopicSnapshot[];
}

export interface NotebookPlanningState {
  notebook_id: string;
  revision: number;
  knowledge_state: Record<string, unknown>;
  learner_state: Record<string, unknown>;
  planner_state: Record<string, unknown>;
  coverage_snapshot: CoverageSnapshot | Record<string, unknown>;
  updated_at: string | null;
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
  curriculum_overview?: {
    active_topic?: string | null;
    total_objectives: number;
    objectives: Array<{
      objective_id: string;
      title: string;
      description?: string | null;
      primary_concepts: string[];
      support_concepts: string[];
      prereq_concepts: string[];
      step_count: number;
      estimated_turns: number;
    }>;
    session_overview?: string | null;
  } | null;
  created_at: string;
  consent_training: boolean;
  plan_state: Record<string, unknown> | null;
  notebook_planning_state: NotebookPlanningState | null;
}

export interface SessionDetail extends Session {
  turn_count: number;
}

export interface SessionCreateRequest {
  resource_id: string;
  topic?: string;
  selected_topics?: string[];
  consent_training?: boolean | null;
}

// ---- Learner Personalization (PROD-021) ----

export interface LearnerPreferences {
  pace?: 'relaxed' | 'moderate' | 'intensive' | null;
  depth?: 'surface' | 'balanced' | 'deep' | null;
  tutoring_style?: 'explanation-heavy' | 'practice-heavy' | 'balanced' | 'socratic' | null;
  hint_level?: 'none' | 'gentle' | 'full' | null;
  language?: string | null;
  accessibility?: Record<string, unknown> | null;
}

export interface NotebookPersonalization {
  purpose?: 'exam_prep' | 'assignment' | 'concept_mastery' | 'doubt_clearing' | 'general' | null;
  urgency?: boolean | null;
  study_pace?: 'relaxed' | 'moderate' | 'intensive' | null;
  study_depth?: 'surface' | 'balanced' | 'deep' | null;
  practice_intensity?: 'light' | 'moderate' | 'heavy' | null;
  exam_context?: string | null;
}

export interface SessionPersonalization {
  time_budget_minutes?: number | null;
  today_goal?: string | null;
  interaction_style?: 'explanation-heavy' | 'practice-heavy' | 'balanced' | 'revision' | null;
  confidence?: 'unsure' | 'somewhat' | 'confident' | null;
  want_hints?: boolean | null;
  want_examples?: boolean | null;
}

// Notebook types
export interface Notebook {
  id: string;
  student_id: string;
  title: string;
  goal: string | null;
  target_date: string | null;
  status: string;
  settings_json: Record<string, unknown> | null;
  personalization: NotebookPersonalization | null;
  created_at: string;
  updated_at: string;
}

export interface NotebookCreateRequest {
  title: string;
  goal?: string;
  target_date?: string;
  settings_json?: Record<string, unknown>;
  personalization?: NotebookPersonalization;
}

export interface NotebookUpdateRequest {
  title?: string;
  goal?: string;
  target_date?: string;
  status?: string;
  settings_json?: Record<string, unknown>;
  personalization?: NotebookPersonalization;
}

export interface NotebookResource {
  id: string;
  notebook_id: string;
  resource_id: string;
  role: string;
  is_active: boolean;
  added_at: string;
  created_at: string;
  updated_at: string;
  resource?: Resource | null;
}

export interface NotebookResourceAttachRequest {
  resource_id: string;
  role?: string;
  is_active?: boolean;
}

export interface NotebookSession {
  id: string;
  notebook_id: string;
  session_id: string;
  mode: string;
  started_at: string;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
  mastery_avg: number | null;
  concepts_count: number;
  topic: string | null;
}

export interface NotebookSessionCreateRequest {
  resource_id: string;
  selected_resource_ids?: string[];
  notebook_wide?: boolean;
  mode?: 'learn' | 'doubt' | 'practice' | 'revision';
  topic?: string;
  selected_topics?: string[];
  consent_training?: boolean | null;
  resume_existing?: boolean;
  curriculum_model_id?: string;
  personalization?: SessionPersonalization;
}

export interface NotebookSessionDetail {
  notebook_session: NotebookSession;
  session: Session;
  reused_existing: boolean;
  preparation_summary?: Record<string, unknown>;
  notebook_planning_state?: NotebookPlanningState | null;
}

export interface NotebookProgress {
  notebook_id: string;
  mastery_snapshot: Record<string, number>;
  objective_progress_snapshot: Record<string, unknown>;
  weak_concepts_snapshot: string[];
  sessions_count: number;
  completed_sessions_count: number;
  coverage_snapshot: CoverageSnapshot | Record<string, unknown>;
  notebook_planning_state: NotebookPlanningState | null;
  updated_at: string | null;
}

export interface NotebookArtifact {
  id: string;
  notebook_id: string;
  artifact_type: string;
  payload_json: Record<string, unknown>;
  source_session_ids: string[];
  source_resource_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface NotebookArtifactGenerateRequest {
  artifact_type: 'notes' | 'flashcards' | 'quiz' | 'revision_plan';
  source_session_ids?: string[];
  source_resource_ids?: string[];
  options?: Record<string, unknown>;
}

export interface UserSettings {
  consent_training_global: boolean;
  consent_preference_set: boolean;
  consent_personalization: boolean;
  is_admin: boolean;
  async_byok_escrow_enabled: boolean;
  async_byok_escrow_backend?: string | null;
  async_byok_escrow_ttl_minutes: number;
  parse_page_limit: number;
  parse_page_used: number;
  parse_page_reserved: number;
  parse_page_remaining: number;
  byok_api_key_set?: boolean;
  byok_api_base_url?: string;
  learning_preferences?: LearnerPreferences | null;
}

export interface UserSettingsUpdateRequest {
  consent_training_global?: boolean;
  consent_personalization?: boolean;
  learning_preferences?: LearnerPreferences;
}

export interface AdminUserSummary {
  id: string;
  email: string | null;
  display_name: string | null;
  external_id: string | null;
  created_at: string;
  balance: number;
  lifetime_granted: number;
  lifetime_used: number;
  is_admin: boolean;
  parse_page_limit: number;
  parse_page_used: number;
  parse_page_reserved: number;
  parse_page_remaining: number;
}

export interface AsyncByokEscrow {
  id: string;
  purpose_type: string;
  purpose_id: string;
  scope_type: string;
  scope_key: string;
  provider_name?: string | null;
  status: string;
  expires_at: string;
  hard_delete_after: string;
  access_count: number;
  last_accessed_at?: string | null;
  revoked_at?: string | null;
  deleted_at?: string | null;
  deletion_reason?: string | null;
}

export interface AdminBillingOverview {
  configured_admin_external_id: string | null;
  credits_enabled: boolean;
  default_monthly_grant: number;
  default_page_allowance: number;
  current_grant_period: string;
  users: AdminUserSummary[];
}

export interface AdminGrantRequest {
  user_id: string;
  amount: number;
  source: string;
  memo: string;
}

export interface AdminGrantResponse {
  grant_id: string;
  user_id: string;
  amount: number;
  new_balance: number;
}

export interface AdminPageAllowanceGrantRequest {
  user_id: string;
  amount: number;
  memo: string;
}

export interface AdminPageAllowanceGrantResponse {
  user_id: string;
  amount: number;
  new_limit: number;
  remaining_pages: number;
}

export interface CreditBalance {
  credits_enabled: boolean;
  balance: number;
  lifetime_granted: number;
  lifetime_used: number;
  plan_tier: string;
  daily_limit: number;
  monthly_limit: number;
  soft_limit_pct: number;
  default_monthly_grant: number;
}

export interface CreditLedgerEntry {
  id: string;
  entry_type: string;
  delta: number;
  balance_after: number;
  reference_type: string | null;
  reference_id: string | null;
  created_at: string;
}

export interface CreditUsageHistory {
  credits_enabled: boolean;
  entries: CreditLedgerEntry[];
}

export interface AdminMonthlyGrantRequest {
  amount?: number;
  period_key?: string;
  memo_prefix?: string;
}

export interface AdminMonthlyGrantResponse {
  period_key: string;
  amount: number;
  granted_user_count: number;
  skipped_user_count: number;
  granted_user_ids: string[];
}

// Tutor types
export interface TutorTurnRequest {
  session_id: string;
  message: string;
}

export interface CitationData {
  citation_id: string;
  resource_id?: string;
  chunk_id: string;
  sub_chunk_id?: string;
  page_start?: number;
  page_end?: number;
  section_heading?: string;
  snippet: string;
  relevance_score: number;
  char_start?: number;
  char_end?: number;
}

export interface StructuredContentBlockData {
  block_type: string;
  content: string;
  metadata: Record<string, unknown>;
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
  session_summary: SessionSummary | null;
  progression_contract?: Record<string, unknown>;
  retrieval_contract?: Record<string, unknown>;
  response_contract?: Record<string, unknown>;
  structured_content?: StructuredContentBlockData[] | null;
  study_map_delta?: Record<string, unknown> | null;
  study_map_snapshot?: Record<string, unknown> | null;
  citations: CitationData[];
  // CM-015: Model routing transparency
  selected_model_id: string | null;
  routed_model_id: string | null;
  reroute_reason: string | null;
}

export interface SessionSummary {
  summary_text: string;
  concepts_strong: string[];
  concepts_developing: string[];
  concepts_to_revisit: string[];
  objectives: SessionObjectiveSummary[];
  mastery_snapshot: Record<string, number>;
  turn_count: number;
  topic: string | null;
}

export interface SessionObjectiveSummary {
  objective_id: string;
  title: string;
  primary_concepts: string[];
  progress: {
    attempts?: number;
    correct?: number;
    steps_completed?: number;
    steps_skipped?: number;
  };
}

export interface SessionSummaryResponse {
  session_id: string;
  status: string;
  topic: string | null;
  turn_count: number;
  summary_text: string | null;
  concepts_strong: string[];
  concepts_developing: string[];
  concepts_to_revisit: string[];
  objectives: SessionObjectiveSummary[];
  mastery_snapshot: Record<string, number>;
  notebook_planning_state: NotebookPlanningState | null;
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
  current_step_index?: number;
  objective_id?: string | null;
  objective_title?: string | null;
  step_transition?: string | null;
  focus_concepts?: string[];
  mastery_update?: Record<string, number> | null;
  progression_decision?: string | null;
  retrieved_chunks?: unknown[] | null;
  policy_output?: unknown | null;
  evaluator_output?: unknown | null;
  latency_ms?: number | null;
  session_summary?: SessionSummary | null;
  progression_contract?: Record<string, unknown>;
  retrieval_contract?: Record<string, unknown>;
  response_contract?: Record<string, unknown>;
  structured_content?: StructuredContentBlockData[] | null;
  study_map_delta?: Record<string, unknown> | null;
  study_map_snapshot?: Record<string, unknown> | null;
  citations?: CitationData[];
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

// Quiz types
export interface QuizQuestion {
  question_id: string;
  question_text: string;
  question_type: string;
  options: string[];
  concept: string;
  difficulty: string;
}

export interface QuizGenerateRequest {
  session_id: string;
  num_questions?: number;
}

export interface QuizGenerateResponse {
  quiz_id: string;
  session_id: string;
  topic: string | null;
  quiz_focus: string;
  questions: QuizQuestion[];
  total_questions: number;
}

export interface QuizAnswerRequest {
  quiz_id: string;
  question_id: string;
  answer: string;
}

export interface QuizAnswerResponse {
  question_id: string;
  is_correct: boolean;
  score: number;
  feedback: string;
  correct_answer: string;
  explanation: string;
}

export interface QuizResultsResponse {
  quiz_id: string;
  session_id: string;
  total_questions: number;
  answered: number;
  correct: number;
  score_percent: number;
  per_question: QuizPerQuestion[];
  concept_scores: Record<string, number>;
  summary: string;
}

export interface QuizPerQuestion {
  question_id: string;
  question_text: string;
  concept: string;
  answered: boolean;
  student_answer: string | null;
  is_correct: boolean | null;
  score: number;
  correct_answer: string;
  explanation: string;
}

// ---- Credits, Model Selection, Metering (CM tickets) ----

export interface ModelPricing {
  model_id: string;
  provider_name: string;
  display_name: string;
  model_class: string;
  input_usd_per_million: number;
  output_usd_per_million: number;
  cache_write_usd_per_million: number | null;
  cache_read_usd_per_million: number | null;
  is_active: boolean;
  is_user_selectable: boolean;
  supports_structured_output: boolean;
  supports_long_context: boolean;
  notes: string | null;
}

export interface ModelPricingCreateRequest {
  model_id: string;
  provider_name: string;
  display_name: string;
  model_class: string;
  input_usd_per_million: number;
  output_usd_per_million: number;
  cache_write_usd_per_million?: number | null;
  cache_read_usd_per_million?: number | null;
  is_active?: boolean;
  is_user_selectable?: boolean;
  supports_structured_output?: boolean;
  supports_long_context?: boolean;
  supports_byok?: boolean;
  notes?: string | null;
}

export interface ModelPricingUpdateRequest {
  input_usd_per_million?: number;
  output_usd_per_million?: number;
  is_active?: boolean;
  is_user_selectable?: boolean;
  notes?: string | null;
}

export interface TaskAssignment {
  task_type: string;
  default_model_id: string;
  fallback_model_ids: string[];
  allowed_model_ids: string[];
  user_override_allowed: boolean;
  rollout_state: string;
  beta_only: boolean;
}

export interface TaskAssignmentCreateRequest {
  task_type: string;
  default_model_id: string;
  fallback_model_ids?: string[];
  allowed_model_ids?: string[];
  user_override_allowed?: boolean;
  rollout_state?: string;
  beta_only?: boolean;
}

export interface TaskAssignmentUpdateRequest {
  default_model_id?: string;
  fallback_model_ids?: string[];
  allowed_model_ids?: string[];
  user_override_allowed?: boolean;
  rollout_state?: string;
}

export interface ModelTaskHealth {
  model_id: string;
  task_type: string;
  status: string;
  consecutive_errors: number;
  rolling_error_rate: number;
  cooldown_until: string | null;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_code: string | null;
  last_error_summary: string | null;
  manual_override_reason: string | null;
}

export interface TaskModelsResponse {
  task_type: string;
  allowed_models: ModelPricing[];
  default_model_id: string;
  user_override_allowed: boolean;
}

export interface UserModelPreferences {
  model_selection_enabled: boolean;
  preferences: Record<string, string>;
}

export interface UserModelPreferencesUpdate {
  policy_model_id?: string;
  response_model_id?: string;
  artifact_model_id?: string;
  upload_model_id?: string;
  tutoring_model_id?: string;
}

export interface BillingOperation {
  id: string;
  operation_type: string;
  status: string;
  selected_model_id: string | null;
  routed_model_id: string | null;
  reroute_reason: string | null;
  estimate_credits_low: number | null;
  estimate_credits_high: number | null;
  reserved_credits: number;
  final_credits: number | null;
  final_usd: number | null;
  created_at: string;
}

export interface OperationHistoryResponse {
  operations: BillingOperation[];
}

export interface IngestionEstimateRequest {
  filename: string;
  file_size_bytes: number;
  page_count_estimate?: number;
  token_count_estimate?: number;
  chunk_count_estimate?: number;
  ontology_model_id?: string;
  enrichment_model_id?: string;
}

export interface IngestionEstimateResponse {
  estimated_credits_low: number;
  estimated_credits_high: number;
  estimated_usd_low: number;
  estimated_usd_high: number;
  core_upload_credits: number;
  core_upload_usd: number;
  curriculum_credits_low: number;
  curriculum_credits_high: number;
  curriculum_usd_low: number;
  curriculum_usd_high: number;
  page_count_estimate: number;
  token_count_estimate: number;
  chunk_count_estimate: number;
  estimate_confidence: string;
  warnings: string[];
}

export interface HealthActionRequest {
  model_id: string;
  task_type: string;
  reason?: string;
}
