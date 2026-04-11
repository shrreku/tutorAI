/**
 * Right artifact panel for the study workspace (PROD-009 / PROD-011).
 *
 * Redesigned with: card-based artifact grid with type badges/icons,
 * proper content rendering, generate buttons as visual cards,
 * personal notes, and source citations.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Cpu, ExternalLink, Files, Loader2, PanelRightClose, Save, Settings2, Sparkles, StickyNote } from 'lucide-react';
import { cn } from '../../lib/utils';
import { ARTIFACT_TYPE_COLOR } from '../icons/ArtifactCatalog';
import {
  QuizIcon,
  FlashcardsIcon,
  SummaryIcon,
  RevisionPlanIcon,
} from '../icons/ArtifactIcons';
import type { ArtifactEventPayload } from '../../types/session-events';
import type {
  NotebookArtifact,
  NotebookPersonalization,
  TaskModelsResponse,
  UserModelPreferences,
  UserModelPreferencesUpdate,
} from '../../types/api';
import { ArtifactViewerCard, type QuizSubmissionSignal } from '../ui/ArtifactViewer';
import RichTutorContent from '../ui/RichTutorContent';

type ArtifactTab = 'artifacts' | 'notes' | 'settings';
type NotesMode = 'edit' | 'preview';

interface ArtifactPanelProps {
  liveArtifacts: ArtifactEventPayload[];
  savedArtifacts: NotebookArtifact[];
  notesDraft: string;
  onNotesChange: (value: string) => void;
  onAddToNotes?: (text: string) => void;
  notesSyncStatus?: 'saved' | 'saving' | 'error';
  focusNotesSignal?: number;
  quizSignals?: QuizSubmissionSignal[];
  onQuizSubmission?: (signal: QuizSubmissionSignal) => void;
  onGenerateArtifact?: (type: string) => void;
  isGeneratingArtifact?: boolean;
  onClose?: () => void;
  notebookPersonalization?: NotebookPersonalization | null;
  onSaveNotebookPersonalization?: (personalization: NotebookPersonalization) => Promise<void> | void;
  modelPreferences?: UserModelPreferences | null;
  onSaveModelPreferences?: (preferences: UserModelPreferencesUpdate) => Promise<void> | void;
  policyTaskModels?: TaskModelsResponse | null;
  responseTaskModels?: TaskModelsResponse | null;
  artifactTaskModels?: TaskModelsResponse | null;
  sessionPersonalization?: Record<string, unknown> | null;
  collapsed?: boolean;
}

function formatArtifactTitle(type: string) {
  return type
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatControlLabel(value: string) {
  return value.replace(/_/g, ' ');
}

function formatSessionValue(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return value.trim() || null;
  if (Array.isArray(value)) {
    const items: Array<string | null> = value
      .map((item) => formatSessionValue(item))
      .filter((item): item is string => Boolean(item));
    return items.length ? items.join(', ') : null;
  }
  if (typeof value === 'object') {
    const entries: Array<string | null> = Object.entries(value as Record<string, unknown>)
      .map(([key, nestedValue]) => {
        const formatted = formatSessionValue(nestedValue);
        return formatted ? `${formatControlLabel(key)}: ${formatted}` : null;
      })
      .filter((item): item is string => Boolean(item));
    return entries.length ? entries.join(' · ') : null;
  }
  return String(value);
}

function modelDisplayName(modelId: string, fallback?: string) {
  return fallback || modelId.split('/').pop() || modelId;
}

/* ── Generate button card ──────────────────────────────────────────── */
const GENERATE_TYPES = [
  { type: 'flashcards', label: 'Flashcards', desc: 'Key term cards', Icon: FlashcardsIcon },
  { type: 'quiz', label: 'Quiz', desc: 'Test knowledge', Icon: QuizIcon },
  { type: 'notes', label: 'Summary', desc: 'Condensed notes', Icon: SummaryIcon },
  { type: 'revision_plan', label: 'Plan', desc: 'Revision schedule', Icon: RevisionPlanIcon },
] as const;


/* ── Main panel ─────────────────────────────────────────────────────── */
export default function ArtifactPanel({
  liveArtifacts,
  savedArtifacts,
  notesDraft,
  onNotesChange,
  onAddToNotes,
  notesSyncStatus = 'saved',
  focusNotesSignal = 0,
  quizSignals = [],
  onQuizSubmission,
  onGenerateArtifact,
  isGeneratingArtifact = false,
  onClose,
  notebookPersonalization,
  onSaveNotebookPersonalization,
  modelPreferences,
  onSaveModelPreferences,
  policyTaskModels,
  responseTaskModels,
  artifactTaskModels,
  sessionPersonalization,
  collapsed = false,
}: ArtifactPanelProps) {
  const [activeTab, setActiveTab] = useState<ArtifactTab>('notes');
  const [notesMode, setNotesMode] = useState<NotesMode>('edit');
  const [selectedPolicyModel, setSelectedPolicyModel] = useState('');
  const [selectedResponseModel, setSelectedResponseModel] = useState('');
  const [selectedArtifactModel, setSelectedArtifactModel] = useState('');
  const [selectedPurpose, setSelectedPurpose] = useState<string | null>(null);
  const [selectedPace, setSelectedPace] = useState<string | null>(null);
  const [selectedDepth, setSelectedDepth] = useState<string | null>(null);
  const [selectedIntensity, setSelectedIntensity] = useState<string | null>(null);
  const [selectedExamContext, setSelectedExamContext] = useState('');
  const [urgent, setUrgent] = useState(false);
  const [savingModels, setSavingModels] = useState(false);
  const [savingNotebookPrefs, setSavingNotebookPrefs] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const totalCount = liveArtifacts.length + savedArtifacts.length;
  const recentIncorrectSignals = useMemo(
    () => quizSignals.filter((signal) => !signal.wasCorrect).slice(-4).reverse(),
    [quizSignals],
  );

  useEffect(() => {
    if (!focusNotesSignal) return;
    setActiveTab('notes');
    setNotesMode('edit');
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(notesDraft.length, notesDraft.length);
    });
  }, [focusNotesSignal, notesDraft.length]);

  useEffect(() => {
    setSelectedPolicyModel(
      modelPreferences?.preferences?.policy_model_id ??
        modelPreferences?.preferences?.tutoring_model_id ??
        policyTaskModels?.default_model_id ??
        '',
    );
    setSelectedResponseModel(
      modelPreferences?.preferences?.response_model_id ??
        modelPreferences?.preferences?.tutoring_model_id ??
        responseTaskModels?.default_model_id ??
        '',
    );
    setSelectedArtifactModel(
      modelPreferences?.preferences?.artifact_model_id ?? artifactTaskModels?.default_model_id ?? '',
    );
  }, [artifactTaskModels?.default_model_id, modelPreferences, policyTaskModels?.default_model_id, responseTaskModels?.default_model_id]);

  useEffect(() => {
    setSelectedPurpose(notebookPersonalization?.purpose ?? null);
    setSelectedPace(notebookPersonalization?.study_pace ?? null);
    setSelectedDepth(notebookPersonalization?.study_depth ?? null);
    setSelectedIntensity(notebookPersonalization?.practice_intensity ?? null);
    setSelectedExamContext(notebookPersonalization?.exam_context ?? '');
    setUrgent(Boolean(notebookPersonalization?.urgency));
  }, [notebookPersonalization]);

  if (collapsed) {
    return (
      <div className="flex flex-col items-center py-4 gap-4">
        <Files className="w-4 h-4 text-muted-foreground" />
        <StickyNote className="w-4 h-4 text-muted-foreground" />
        <ExternalLink className="w-4 h-4 text-muted-foreground" />
      </div>
    );
  }

  const tabs: { key: ArtifactTab; label: string; count: number }[] = [
    { key: 'notes', label: 'Notes', count: 0 },
    { key: 'artifacts', label: 'Artifacts', count: totalCount },
    { key: 'settings', label: 'Settings', count: 0 },
  ];

  const selectedPolicyModelLabel = useMemo(() => {
    if (!selectedPolicyModel) return 'System default';
    return (
      policyTaskModels?.allowed_models.find((model) => model.model_id === selectedPolicyModel)?.display_name ||
      modelDisplayName(selectedPolicyModel)
    );
  }, [selectedPolicyModel, policyTaskModels]);

  const sessionPersonalizationEntries = useMemo(() => {
    if (!sessionPersonalization) return [];
    return Object.entries(sessionPersonalization)
      .map(([key, value]) => {
        const formattedValue = formatSessionValue(value);
        if (!formattedValue) return null;
        return {
          key,
          label: formatControlLabel(key),
          value: formattedValue,
        };
      })
      .filter((item): item is { key: string; label: string; value: string } => Boolean(item));
  }, [sessionPersonalization]);

  const handleSaveModelPreferences = async () => {
    if (!onSaveModelPreferences) return;
    setSavingModels(true);
    try {
      await onSaveModelPreferences({
        policy_model_id: selectedPolicyModel || policyTaskModels?.default_model_id || undefined,
        response_model_id: selectedResponseModel || responseTaskModels?.default_model_id || undefined,
        artifact_model_id: selectedArtifactModel || artifactTaskModels?.default_model_id || undefined,
      });
    } finally {
      setSavingModels(false);
    }
  };

  const handleSaveNotebookPersonalization = async () => {
    if (!onSaveNotebookPersonalization) return;
    setSavingNotebookPrefs(true);
    try {
      await onSaveNotebookPersonalization({
        purpose: selectedPurpose as NotebookPersonalization['purpose'],
        urgency: urgent,
        study_pace: selectedPace as NotebookPersonalization['study_pace'],
        study_depth: selectedDepth as NotebookPersonalization['study_depth'],
        practice_intensity: selectedIntensity as NotebookPersonalization['practice_intensity'],
        exam_context: selectedExamContext.trim() || undefined,
      });
    } finally {
      setSavingNotebookPrefs(false);
    }
  };

  return (
    <div className="h-full flex flex-col overflow-hidden surface-scholarly">
      {/* Tab bar */}
      <div className="flex items-center border-b border-border/40 px-2 shrink-0">
        {onClose && (
          <button
            onClick={onClose}
            className="rounded-lg border border-border/60 p-1 mr-1 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground shrink-0"
            title="Close artifacts"
          >
            <PanelRightClose className="w-3.5 h-3.5" />
          </button>
        )}
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-2.5 text-[11px] font-medium transition-colors border-b-2 -mb-px font-ui uppercase tracking-[0.08em]',
              activeTab === tab.key
                ? 'text-gold border-gold'
                : 'text-muted-foreground border-transparent hover:text-foreground',
            )}
          >
            {tab.label}
            {tab.count > 0 && (
              <span className={cn(
                'text-[9px] px-1.5 py-0.5 rounded-full font-ui',
                activeTab === tab.key
                  ? 'bg-gold/10 text-gold'
                  : 'bg-muted text-muted-foreground',
              )}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-3">
        {/* ── Artifacts tab ─────────────────────────────────────── */}
        {activeTab === 'artifacts' && (
          <div className="space-y-4">
            {/* Generate buttons as a 2×2 mini grid */}
            {onGenerateArtifact && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground mb-2 font-ui">
                  Generate
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  {GENERATE_TYPES.map(({ type, label, desc, Icon }) => (
                    <button
                      key={type}
                      onClick={() => onGenerateArtifact(type)}
                      className={cn(
                        'flex items-center gap-2 rounded-xl border p-2.5 text-left transition-colors hover:border-gold/30',
                        ARTIFACT_TYPE_COLOR[type] || 'border-border bg-card',
                      )}
                    >
                      <Icon size={16} />
                      <div className="min-w-0">
                        <p className="text-[11px] font-semibold leading-tight font-ui uppercase tracking-[0.06em]">{label}</p>
                        <p className="text-[9px] opacity-70 leading-tight reading-copy">{desc}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Generating artifact placeholder */}
            {isGeneratingArtifact && (
              <div className="rounded-xl border border-gold/25 bg-gold/[0.04] p-3 animate-pulse">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl border border-gold/20 bg-gold/10 p-2.5 shrink-0">
                    <Sparkles className="h-4 w-4 text-gold animate-pulse" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-gold">Generating artifact…</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">This may take a moment</p>
                  </div>
                  <Loader2 className="h-4 w-4 text-gold animate-spin shrink-0" />
                </div>
              </div>
            )}

            {/* Artifact cards */}
            {liveArtifacts.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground mb-2 font-ui">
                  This Session
                </p>
                <div className="space-y-2">
                  {liveArtifacts.map((a) => (
                    <ArtifactViewerCard
                      key={a.artifact_id}
                      artifactKey={a.artifact_id}
                      type={a.artifact_type}
                      title={formatArtifactTitle(a.artifact_type)}
                      isGenerating={a.status === 'generating'}
                      payload={a.payload_json}
                      onAddToNotes={onAddToNotes}
                      onQuizSubmission={onQuizSubmission}
                      downloadFileName={`${a.artifact_type}-${a.artifact_id.slice(0, 8)}.json`}
                    />
                  ))}
                </div>
              </div>
            )}

            {savedArtifacts.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground mb-2 font-ui">
                  Saved
                </p>
                <div className="space-y-2">
                  {savedArtifacts.map((a) => (
                    <ArtifactViewerCard
                      key={a.id}
                      artifactKey={a.id}
                      type={a.artifact_type}
                      title={formatArtifactTitle(a.artifact_type)}
                      subtitle={new Date(a.created_at).toLocaleDateString()}
                      createdAt={a.created_at}
                      payload={a.payload_json}
                      onAddToNotes={onAddToNotes}
                      onQuizSubmission={onQuizSubmission}
                      downloadFileName={`${a.artifact_type}-${a.id.slice(0, 8)}.json`}
                    />
                  ))}
                </div>
              </div>
            )}

            {totalCount === 0 && !onGenerateArtifact && (
              <div className="flex flex-col items-center justify-center border border-dashed border-border py-8 rounded-lg text-center">
                <Files className="mb-2 w-8 h-8 text-muted-foreground/20" />
                <p className="text-xs text-muted-foreground/60">
                  Artifacts will appear here as you study
                </p>
              </div>
            )}
          </div>
        )}

        {/* ── Notes tab ─────────────────────────────────────────── */}
        {activeTab === 'notes' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground font-ui">
                Personal Notes
              </p>
              <div className="inline-flex rounded-full border border-border bg-background/80 p-0.5">
                <button
                  type="button"
                  onClick={() => setNotesMode('edit')}
                  className={cn(
                    'rounded-full px-3 py-1 text-[10px] uppercase tracking-[0.12em] transition-colors',
                    notesMode === 'edit' ? 'bg-gold/10 text-gold' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => setNotesMode('preview')}
                  className={cn(
                    'rounded-full px-3 py-1 text-[10px] uppercase tracking-[0.12em] transition-colors',
                    notesMode === 'preview' ? 'bg-gold/10 text-gold' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  Preview
                </button>
              </div>
            </div>

            {recentIncorrectSignals.length > 0 && (
              <div className="rounded-xl border border-amber-500/20 bg-amber-50/60 p-3 dark:bg-amber-500/10">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-amber-700 dark:text-amber-400 font-ui">
                  Quiz profiling signals
                </p>
                <div className="mt-2 space-y-2">
                  {recentIncorrectSignals.map((signal) => (
                    <div key={`${signal.artifactKey}:${signal.questionId}`} className="rounded-lg border border-amber-500/10 bg-background/70 px-3 py-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-foreground">{signal.concept || 'Concept to revisit'}</p>
                          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{signal.question}</p>
                        </div>
                        {onAddToNotes ? (
                          <button
                            type="button"
                            onClick={() => onAddToNotes([
                              `## Misconception note: ${signal.concept || signal.artifactTitle}`,
                              `Question: ${signal.question}`,
                              `My answer: ${signal.userAnswer || 'No answer recorded'}`,
                              `Correct answer: ${signal.correctAnswer}`,
                              signal.explanation ? `Explanation: ${signal.explanation}` : '',
                            ].filter(Boolean).join('\n'))}
                            className="shrink-0 rounded-full border border-amber-500/20 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-amber-700 transition-colors hover:bg-amber-100/70 dark:text-amber-300 dark:hover:bg-amber-500/10"
                          >
                            Add
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {notesMode === 'edit' ? (
              <textarea
                ref={textareaRef}
                value={notesDraft}
                onChange={(event) => onNotesChange(event.target.value)}
                className="w-full min-h-[320px] resize-none rounded-xl border border-border bg-background/90 p-3 text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/40 focus:border-gold/40 transition-colors reading-copy"
                placeholder="Capture explanations in your own words, jot down formulas, or draft a revision checklist..."
              />
            ) : (
              <div className="min-h-[320px] rounded-xl border border-border bg-background/90 p-4">
                {notesDraft.trim() ? (
                  <RichTutorContent content={notesDraft} />
                ) : (
                  <p className="text-sm text-muted-foreground reading-copy">Your notes preview will appear here, including LaTeX and formatting.</p>
                )}
              </div>
            )}

            <p className="text-[10px] text-muted-foreground/50 text-center font-ui uppercase tracking-[0.08em]">
              {notesSyncStatus === 'saving'
                ? 'Saving notes to notebook…'
                : notesSyncStatus === 'error'
                  ? 'Save failed • your draft is still in this browser'
                  : 'Saved to notebook • selections from tutor replies and artifacts can be added here'}
            </p>
          </div>
        )}

        {/* ── Settings tab ─────────────────────────────────────── */}
        {activeTab === 'settings' && (
          <div className="space-y-4">
            {/* Quick summary chips */}
            <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
              <span className="rounded-full border border-border/60 bg-background/60 px-2 py-0.5">
                {selectedPolicyModelLabel}
              </span>
              <span className="rounded-full border border-border/60 bg-background/60 px-2 py-0.5">
                {selectedPurpose ? formatControlLabel(selectedPurpose) : 'No purpose'}
              </span>
            </div>

            {/* ── Model settings ── */}
            <div className="space-y-3 rounded-2xl border border-border/60 bg-background/55 p-3.5">
              <div className="flex items-center gap-2">
                <Cpu className="h-3.5 w-3.5 text-gold" />
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground font-ui">
                  Model settings
                </p>
              </div>

              <div className="space-y-3 border-t border-border/40 pt-3">
                <div className="space-y-1.5">
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-ui">
                    Policy model
                  </label>
                  <select
                    value={selectedPolicyModel}
                    onChange={(e) => setSelectedPolicyModel(e.target.value)}
                    className="w-full rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none focus:border-gold/30 transition-colors"
                  >
                    <option value="">Default ({policyTaskModels?.default_model_id?.split('/').pop() ?? 'system'})</option>
                    {(policyTaskModels?.allowed_models ?? []).map((model) => (
                      <option key={model.model_id} value={model.model_id}>
                        {model.display_name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-ui">
                    Response model
                  </label>
                  <select
                    value={selectedResponseModel}
                    onChange={(e) => setSelectedResponseModel(e.target.value)}
                    className="w-full rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none focus:border-gold/30 transition-colors"
                  >
                    <option value="">Default ({responseTaskModels?.default_model_id?.split('/').pop() ?? 'system'})</option>
                    {(responseTaskModels?.allowed_models ?? []).map((model) => (
                      <option key={model.model_id} value={model.model_id}>
                        {model.display_name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-ui">
                    Artifact model
                  </label>
                  <select
                    value={selectedArtifactModel}
                    onChange={(e) => setSelectedArtifactModel(e.target.value)}
                    className="w-full rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none focus:border-gold/30 transition-colors"
                  >
                    <option value="">Default ({artifactTaskModels?.default_model_id?.split('/').pop() ?? 'system'})</option>
                    {(artifactTaskModels?.allowed_models ?? []).map((model) => (
                      <option key={model.model_id} value={model.model_id}>
                        {model.display_name}
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  type="button"
                  onClick={() => void handleSaveModelPreferences()}
                  disabled={!onSaveModelPreferences || savingModels}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-gold/30 bg-gold/[0.08] px-3 py-2 text-xs font-semibold text-gold transition-colors hover:bg-gold/[0.14] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {savingModels ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                  Save model preferences
                </button>
              </div>
            </div>

            {/* ── Notebook personalization ── */}
            <div className="space-y-3 rounded-2xl border border-border/60 bg-background/55 p-3.5">
              <div className="flex items-center gap-2">
                <Sparkles className="h-3.5 w-3.5 text-gold" />
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground font-ui">
                  Notebook personalization
                </p>
              </div>

              <div className="space-y-3 border-t border-border/40 pt-3">
                <div className="space-y-1.5">
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-ui">
                    Purpose
                  </label>
                  <select
                    value={selectedPurpose ?? ''}
                    onChange={(e) => setSelectedPurpose(e.target.value || null)}
                    className="w-full rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none focus:border-gold/30 transition-colors"
                  >
                    <option value="">No purpose set</option>
                    <option value="exam_prep">Exam prep</option>
                    <option value="assignment">Assignment</option>
                    <option value="concept_mastery">Concept mastery</option>
                    <option value="doubt_clearing">Doubt clearing</option>
                    <option value="general">General</option>
                  </select>
                </div>

                <div className="grid gap-2 grid-cols-2">
                  <div className="space-y-1.5">
                    <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-ui">
                      Pace
                    </label>
                    <select
                      value={selectedPace ?? ''}
                      onChange={(e) => setSelectedPace(e.target.value || null)}
                      className="w-full rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none focus:border-gold/30 transition-colors"
                    >
                      <option value="">Not set</option>
                      <option value="relaxed">Relaxed</option>
                      <option value="moderate">Moderate</option>
                      <option value="intensive">Intensive</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-ui">
                      Depth
                    </label>
                    <select
                      value={selectedDepth ?? ''}
                      onChange={(e) => setSelectedDepth(e.target.value || null)}
                      className="w-full rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none focus:border-gold/30 transition-colors"
                    >
                      <option value="">Not set</option>
                      <option value="surface">Surface</option>
                      <option value="balanced">Balanced</option>
                      <option value="deep">Deep</option>
                    </select>
                  </div>
                </div>

                <div className="grid gap-2 grid-cols-2">
                  <div className="space-y-1.5">
                    <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-ui">
                      Practice intensity
                    </label>
                    <select
                      value={selectedIntensity ?? ''}
                      onChange={(e) => setSelectedIntensity(e.target.value || null)}
                      className="w-full rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none focus:border-gold/30 transition-colors"
                    >
                      <option value="">Not set</option>
                      <option value="light">Light</option>
                      <option value="moderate">Moderate</option>
                      <option value="heavy">Heavy</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-ui">
                      Urgent deadline
                    </label>
                    <select
                      value={urgent ? 'yes' : 'no'}
                      onChange={(e) => setUrgent(e.target.value === 'yes')}
                      className="w-full rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none focus:border-gold/30 transition-colors"
                    >
                      <option value="no">No urgency</option>
                      <option value="yes">Urgent</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-ui">
                    Exam context
                  </label>
                  <input
                    value={selectedExamContext}
                    onChange={(e) => setSelectedExamContext(e.target.value)}
                    placeholder="Midterm in 2 weeks, chapter 4 revision…"
                    className="w-full rounded-xl border border-border/60 bg-background/70 px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-gold/30 transition-colors"
                  />
                </div>

                <button
                  type="button"
                  onClick={() => void handleSaveNotebookPersonalization()}
                  disabled={!onSaveNotebookPersonalization || savingNotebookPrefs}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-gold/30 bg-gold/[0.08] px-3 py-2 text-xs font-semibold text-gold transition-colors hover:bg-gold/[0.14] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {savingNotebookPrefs ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                  Save personalization
                </button>
              </div>
            </div>

            {/* ── Session snapshot ── */}
            {sessionPersonalizationEntries.length > 0 && (
              <div className="space-y-2 rounded-2xl border border-dashed border-border/50 bg-background/35 px-3.5 py-3">
                <div className="flex items-center gap-1.5">
                  <Settings2 className="h-3 w-3 text-muted-foreground/60" />
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground font-ui">
                    Session snapshot
                  </p>
                </div>
                <div className="space-y-1">
                  {sessionPersonalizationEntries.map((entry) => (
                    <div key={entry.key} className="flex items-baseline justify-between gap-2 px-1 py-0.5">
                      <span className="text-[10px] uppercase tracking-[0.10em] text-muted-foreground/70 font-ui shrink-0">{entry.label}</span>
                      <span className="text-[11px] text-foreground text-right truncate">{entry.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
