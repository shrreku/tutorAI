/**
 * Right artifact panel for the study workspace (PROD-009 / PROD-011).
 *
 * Redesigned with: card-based artifact grid with type badges/icons,
 * proper content rendering, generate buttons as visual cards,
 * personal notes, and source citations.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  StickyNote, ExternalLink,
  Files,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import {
  ARTIFACT_TYPE_COLOR,
  QuizIcon, FlashcardsIcon, SummaryIcon, RevisionPlanIcon,
} from '../icons/ArtifactIcons';
import type { ArtifactEventPayload, SourceCitationPayload } from '../../types/session-events';
import type { NotebookArtifact } from '../../types/api';
import { ArtifactViewerCard, type QuizSubmissionSignal } from '../ui/ArtifactViewer';
import RichTutorContent from '../ui/RichTutorContent';

type ArtifactTab = 'artifacts' | 'notes' | 'sources';
type NotesMode = 'edit' | 'preview';

interface ArtifactPanelProps {
  liveArtifacts: ArtifactEventPayload[];
  savedArtifacts: NotebookArtifact[];
  citations: SourceCitationPayload[];
  notesDraft: string;
  onNotesChange: (value: string) => void;
  onAddToNotes?: (text: string) => void;
  notesSyncStatus?: 'saved' | 'saving' | 'error';
  focusNotesSignal?: number;
  quizSignals?: QuizSubmissionSignal[];
  onQuizSubmission?: (signal: QuizSubmissionSignal) => void;
  onGenerateArtifact?: (type: string) => void;
  collapsed?: boolean;
}

function formatArtifactTitle(type: string) {
  return type
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

/* ── Generate button card ──────────────────────────────────────────── */
const GENERATE_TYPES = [
  { type: 'flashcards', label: 'Flashcards', desc: 'Key term cards', Icon: FlashcardsIcon },
  { type: 'quiz', label: 'Quiz', desc: 'Test knowledge', Icon: QuizIcon },
  { type: 'notes', label: 'Summary', desc: 'Condensed notes', Icon: SummaryIcon },
  { type: 'revision_plan', label: 'Plan', desc: 'Revision schedule', Icon: RevisionPlanIcon },
] as const;


/* ── Citation card ──────────────────────────────────────────────────── */
function CitationCard({ citation }: { citation: SourceCitationPayload }) {
  return (
    <div className="flex items-start gap-2 py-2 px-1">
      <ExternalLink className="w-3.5 h-3.5 text-gold shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <span className="text-sm text-foreground font-reading">
          {citation.resource_name || citation.resource_id}
        </span>
        {citation.page_numbers.length > 0 && (
          <span className="text-[10px] text-muted-foreground ml-2 font-ui uppercase tracking-[0.06em]">
            p.{citation.page_numbers.join(', ')}
          </span>
        )}
        {citation.snippet && (
          <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed line-clamp-3 italic reading-copy">
            &ldquo;{citation.snippet}&rdquo;
          </p>
        )}
      </div>
    </div>
  );
}

/* ── Main panel ─────────────────────────────────────────────────────── */
export default function ArtifactPanel({
  liveArtifacts,
  savedArtifacts,
  citations,
  notesDraft,
  onNotesChange,
  onAddToNotes,
  notesSyncStatus = 'saved',
  focusNotesSignal = 0,
  quizSignals = [],
  onQuizSubmission,
  onGenerateArtifact,
  collapsed = false,
}: ArtifactPanelProps) {
  const [activeTab, setActiveTab] = useState<ArtifactTab>('notes');
  const [notesMode, setNotesMode] = useState<NotesMode>('edit');
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
    { key: 'sources', label: 'Sources', count: citations.length },
  ];

  return (
    <div className="h-full flex flex-col overflow-hidden surface-scholarly">
      {/* Tab bar */}
      <div className="flex border-b border-border/40 px-2 shrink-0">
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
                      badge={a.status === 'ready' ? 'ready' : undefined}
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

        {/* ── Sources tab ───────────────────────────────────────── */}
        {activeTab === 'sources' && (
          <div>
            {citations.length === 0 ? (
              <div className="flex flex-col items-center justify-center border border-dashed border-border py-8 rounded-lg text-center">
                <ExternalLink className="mb-2 w-8 h-8 text-muted-foreground/20" />
                <p className="text-xs text-muted-foreground/60">
                  Source citations will appear here
                </p>
              </div>
            ) : (
              <div className="divide-y divide-border/40">
                {citations.map((c) => <CitationCard key={c.citation_id} citation={c} />)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
