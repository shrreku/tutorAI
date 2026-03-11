import { describe, expect, it } from 'vitest';

import type {
  ModelPricing,
  BillingOperation,
  IngestionEstimateRequest,
  IngestionEstimateResponse,
  UserModelPreferencesUpdate,
  HealthActionRequest,
  TutorTurnResponse,
} from '../types/api';

describe('CM types', () => {
  it('ModelPricing has required fields', () => {
    const model: ModelPricing = {
      model_id: 'google/gemini-3.1-flash-lite',
      provider_name: 'google',
      display_name: 'Gemini 3.1 Flash Lite',
      model_class: 'economy',
      input_usd_per_million: 0.075,
      output_usd_per_million: 0.30,
      cache_write_usd_per_million: 0,
      cache_read_usd_per_million: 0,
      is_active: true,
      is_user_selectable: true,
      supports_structured_output: true,
      supports_long_context: true,
      notes: null,
    };
    expect(model.model_id).toBe('google/gemini-3.1-flash-lite');
    expect(model.model_class).toBe('economy');
  });

  it('BillingOperation has required fields', () => {
    const op: BillingOperation = {
      id: '123',
      operation_type: 'tutor_turn',
      status: 'finalized',
      created_at: '2026-01-01T00:00:00Z',
      selected_model_id: 'gpt-5-mini',
      routed_model_id: null,
      reroute_reason: null,
      estimate_credits_low: 100,
      estimate_credits_high: 150,
      reserved_credits: 100,
      final_credits: 80,
      final_usd: 0.64,
    };
    expect(op.operation_type).toBe('tutor_turn');
    expect(op.final_credits).toBe(80);
  });

  it('IngestionEstimateRequest has required fields', () => {
    const req: IngestionEstimateRequest = {
      filename: 'test.pdf',
      file_size_bytes: 50000,
    };
    expect(req.filename).toBe('test.pdf');
  });

  it('IngestionEstimateResponse has required fields', () => {
    const res: IngestionEstimateResponse = {
      estimated_credits_low: 50,
      estimated_credits_high: 200,
      estimated_usd_low: 0.4,
      estimated_usd_high: 1.6,
      page_count_estimate: 5,
      token_count_estimate: 5000,
      chunk_count_estimate: 10,
      estimate_confidence: 'medium',
      warnings: [],
    };
    expect(res.estimated_credits_low).toBeLessThanOrEqual(res.estimated_credits_high);
  });

  it('UserModelPreferencesUpdate is valid', () => {
    const update: UserModelPreferencesUpdate = {
      tutoring_model_id: 'google/gemini-3-flash-preview',
    };
    expect(update.tutoring_model_id).toBeTruthy();
  });

  it('HealthActionRequest has required fields', () => {
    const req: HealthActionRequest = {
      model_id: 'test-model',
      task_type: 'tutoring',
      reason: 'manual test',
    };
    expect(req.reason).toBe('manual test');
  });

  it('TutorTurnResponse includes model routing fields', () => {
    const resp: TutorTurnResponse = {
      turn_id: '123',
      response: 'Hello student',
      tutor_question: null,
      current_step: null,
      current_step_index: 0,
      objective_id: null,
      objective_title: null,
      step_transition: null,
      focus_concepts: [],
      mastery_update: null,
      evaluation: null,
      session_complete: false,
      awaiting_evaluation: false,
      session_summary: null,
      selected_model_id: 'gpt-5',
      routed_model_id: 'gemini-3.1-flash-lite',
      reroute_reason: 'cooldown',
    };
    expect(resp.selected_model_id).toBe('gpt-5');
    expect(resp.routed_model_id).toBe('gemini-3.1-flash-lite');
    expect(resp.reroute_reason).toBe('cooldown');
  });

  it('TutorTurnResponse model routing fields are nullable', () => {
    const resp: TutorTurnResponse = {
      turn_id: '123',
      response: 'Hello',
      tutor_question: null,
      current_step: null,
      current_step_index: 0,
      objective_id: null,
      objective_title: null,
      step_transition: null,
      focus_concepts: [],
      mastery_update: null,
      evaluation: null,
      session_complete: false,
      awaiting_evaluation: false,
      session_summary: null,
      selected_model_id: null,
      routed_model_id: null,
      reroute_reason: null,
    };
    expect(resp.selected_model_id).toBeNull();
  });
});
