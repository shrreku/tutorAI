/**
 * Three-panel study workspace shell (PROD-009).
 *
 * Layout: [Context Panel | Tutor Panel | Artifact Panel]
 * Uses react-resizable-panels for drag-to-resize.
 * Responsive: collapses side panels on small screens.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen,
  ArrowLeft,
} from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { cn } from '../../lib/utils';
import ContextPanel from './ContextPanel';
import TutorPanel from './TutorPanel';
import ArtifactPanel from './ArtifactPanel';
import {
  useNotebook,
  useNotebookResources,
  useNotebookSessions,
  useNotebookSessionDetail,
  useResourceTopicsBatch,
  useTurns,
  useSendNotebookMessage,
  useNotebookArtifacts,
  useNotebookProgress,
  useGenerateNotebookArtifact,
  useUpdateNotebook,
} from '../../api/hooks';
import type { Turn, NotebookArtifact } from '../../types/api';
import type { QuizSubmissionSignal } from '../ui/ArtifactViewer';
import type {
  ObjectiveSnapshot,
  CheckpointRequestedPayload,
  ArtifactEventPayload,
  SourceCitationPayload,
  StudyMapSnapshot,
} from '../../types/session-events';
import { Sparkles, Brain, TimerReset, Target } from 'lucide-react';
import {
  buildNotebookSettingsWithPersonalNotes,
  readNotebookPersonalNotes,
  type NotebookPersonalNotesSource,
} from '../../lib/notebookPersonalNotes';

const MOBILE_BREAKPOINT = 768;

function ResizeHandle({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'group relative hidden w-1.5 shrink-0 items-center justify-center xl:flex',
        className,
      )}
    >
      <div className="w-px h-8 rounded-full bg-border/40 group-hover:bg-gold/40 group-active:bg-gold transition-colors" />
    </div>
  );
}

export default function StudyWorkspace() {
  const { notebookId } = useParams<{ notebookId: string }>();
  const navigate = useNavigate();
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  // Responsive detection
  useEffect(() => {
    const check = () => {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT;
      if (mobile) {
        setLeftOpen(false);
        setRightOpen(false);
      }
    };
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  // Data hooks
  const { data: notebook } = useNotebook(notebookId || '');
  const { data: resourcesData } = useNotebookResources(notebookId || '');
  const { data: sessionsData } = useNotebookSessions(notebookId || '');
  const { data: artifactsData } = useNotebookArtifacts(notebookId || '');
  const { data: progressData } = useNotebookProgress(notebookId || '');
  const generateArtifact = useGenerateNotebookArtifact(notebookId || '');
  const updateNotebook = useUpdateNotebook(notebookId || '');

  // Find active/latest notebook session (flat NotebookSession type)
  const activeNbSession = useMemo(() => {
    if (!sessionsData?.items?.length) return null;
    const sorted = [...sessionsData.items].sort(
      (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
    );
    return sorted.find((s) => !s.ended_at) ?? sorted[0];
  }, [sessionsData]);

  const sessionId = activeNbSession?.session_id || '';

  // Get full session detail (includes Session with status, mastery, plan_state)
  const { data: sessionDetail } = useNotebookSessionDetail(notebookId || '', sessionId);

  const { data: turnsData, isLoading: turnsLoading } = useTurns(sessionId);
  const sendMessage = useSendNotebookMessage(notebookId || '');
  const notesStorageKey = useMemo(() => `study-workspace-notes:${notebookId || 'default'}`, [notebookId]);
  const persistedNotebookNotes = useMemo(
    () => readNotebookPersonalNotes(notebook?.settings_json),
    [notebook?.settings_json],
  );

  // Build turns list
  const turns: Turn[] = useMemo(() => {
    if (!turnsData?.turns) return [];
    return turnsData.turns;
  }, [turnsData]);

  // Build resource list for context panel
  const resources = useMemo(() => {
    if (!resourcesData?.items) return [];
    return resourcesData.items.map((r: any) => ({
      id: String(r.resource_id),
      label: r.resource?.filename || 'Resource',
      subtitle: r.resource?.topic || undefined,
      status: r.resource?.status || 'unknown',
      studyReady: r.resource?.capabilities?.learn_ready || r.resource?.capabilities?.search_ready || false,
    }));
  }, [resourcesData]);

  const resourceIds = useMemo(() => resources.map((resource) => resource.id), [resources]);
  const resourceTopicQueries = useResourceTopicsBatch(resourceIds);
  const resourceTopics = useMemo(() => {
    return resourceTopicQueries
      .map((query, index) => {
        const data = query.data;
        const resource = resources[index];
        if (!data || !resource || data.topics.length === 0) return null;
        return {
          resourceId: data.resource_id,
          resourceLabel: resource.label,
          courseTopic: data.topic,
          topics: data.topics,
        };
      })
      .filter((item): item is NonNullable<typeof item> => Boolean(item));
  }, [resourceTopicQueries, resources]);

  // Build objectives from session curriculum_overview (top-level field on SessionResponse)
  const objectives: ObjectiveSnapshot[] = useMemo(() => {
    const session = sessionDetail?.session;
    const overview = session?.curriculum_overview;
    const objs = overview?.objectives;
    if (!Array.isArray(objs)) return [];
    return objs.map((obj: any) => ({
      objective_id: obj.objective_id || obj.id || '',
      title: obj.title || '',
      description: obj.description,
      primary_concepts: obj.primary_concepts || [],
      support_concepts: obj.support_concepts || [],
      prereq_concepts: obj.prereq_concepts || [],
      step_count: obj.step_count || 0,
      status: 'pending' as const,
      progress_pct: 0,
    }));
  }, [sessionDetail]);

  // Mastery from progress data or session
  const mastery: Record<string, number> = useMemo(() => {
    return progressData?.mastery_snapshot || sessionDetail?.session?.mastery || {};
  }, [progressData, sessionDetail]);

  const weakConcepts: string[] = useMemo(() => {
    return progressData?.weak_concepts_snapshot || [];
  }, [progressData]);

  // Artifacts
  const savedArtifacts: NotebookArtifact[] = useMemo(() => {
    return artifactsData?.items || [];
  }, [artifactsData]);

  // Live state (will be populated from session events in future)
  const [liveArtifacts] = useState<ArtifactEventPayload[]>([]);
  const [citations] = useState<SourceCitationPayload[]>([]);
  const [activeCheckpoint] = useState<CheckpointRequestedPayload | null>(null);
  const [notesDraft, setNotesDraft] = useState('');
  const [notesSyncStatus, setNotesSyncStatus] = useState<'saved' | 'saving' | 'error'>('saved');
  const [lastSavedNotes, setLastSavedNotes] = useState('');
  const [hydratedNotebookKey, setHydratedNotebookKey] = useState<string | null>(null);
  const [focusNotesSignal, setFocusNotesSignal] = useState(0);
  const [quizSignals, setQuizSignals] = useState<Record<string, QuizSubmissionSignal>>({});
  const pendingNotesSourceRef = useRef<NotebookPersonalNotesSource>('manual');

  // Live study map snapshot — updated from turn responses
  const [studyMapSnapshot, setStudyMapSnapshot] = useState<StudyMapSnapshot | null>(null);

  // Update study map from the latest turn response
  useEffect(() => {
    if (!turns.length) return;
    const last = turns[turns.length - 1] as any;
    if (last?.study_map_snapshot) {
      setStudyMapSnapshot(last.study_map_snapshot);
    }
  }, [turns]);

  useEffect(() => {
    if (!notebookId || !notebook) return;

    if (hydratedNotebookKey === notebook.id) {
      if (persistedNotebookNotes.markdown === lastSavedNotes) {
        setNotesSyncStatus('saved');
      }
      return;
    }

    let nextNotes = persistedNotebookNotes.markdown;
    let shouldMigrateLocalNotes = false;

    if (typeof window !== 'undefined') {
      const localDraft = window.localStorage.getItem(notesStorageKey) || '';
      if (!nextNotes.trim() && localDraft.trim()) {
        nextNotes = localDraft;
        shouldMigrateLocalNotes = true;
      }
      window.localStorage.setItem(notesStorageKey, nextNotes);
    }

    setNotesDraft(nextNotes);
    setLastSavedNotes(shouldMigrateLocalNotes ? '' : persistedNotebookNotes.markdown);
    setNotesSyncStatus(shouldMigrateLocalNotes ? 'saving' : 'saved');
    pendingNotesSourceRef.current = shouldMigrateLocalNotes ? 'migration' : 'manual';
    setHydratedNotebookKey(notebook.id);
  }, [hydratedNotebookKey, lastSavedNotes, notebook, notebookId, notesStorageKey, persistedNotebookNotes]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(notesStorageKey, notesDraft);
  }, [notesDraft, notesStorageKey]);

  useEffect(() => {
    if (!notebookId || !notebook || hydratedNotebookKey !== notebook.id) return;
    if (notesDraft === lastSavedNotes) return;

    setNotesSyncStatus('saving');
    const saveTimer = window.setTimeout(() => {
      const source = pendingNotesSourceRef.current;
      updateNotebook.mutate(
        {
          settings_json: buildNotebookSettingsWithPersonalNotes(notebook.settings_json, notesDraft, source),
        },
        {
          onSuccess: (updatedNotebook) => {
            const updatedNotes = readNotebookPersonalNotes(updatedNotebook.settings_json);
            setLastSavedNotes(updatedNotes.markdown);
            setNotesSyncStatus('saved');
            pendingNotesSourceRef.current = 'manual';
            if (typeof window !== 'undefined') {
              window.localStorage.setItem(notesStorageKey, updatedNotes.markdown);
            }
          },
          onError: () => {
            setNotesSyncStatus('error');
          },
        },
      );
    }, 800);

    return () => window.clearTimeout(saveTimer);
  }, [hydratedNotebookKey, lastSavedNotes, notebook, notebookId, notesDraft, notesStorageKey, updateNotebook]);

  const handleNotesChange = useCallback((value: string) => {
    pendingNotesSourceRef.current = 'manual';
    setNotesDraft(value);
  }, []);

  const sessionComplete = useMemo(() => {
    return sessionDetail?.session?.status === 'completed';
  }, [sessionDetail]);

  // Session mode
  const mode = activeNbSession?.mode || null;

  // Session overview
  // Handlers
  const handleSendMessage = useCallback(
    (text: string) => {
      if (!sessionId) return;
      sendMessage.mutate({ session_id: sessionId, message: text });
    },
    [sessionId, sendMessage],
  );

  const handleGenerateArtifact = useCallback(
    (type: string) => {
      if (!['notes', 'flashcards', 'quiz', 'revision_plan'].includes(type)) return;
      generateArtifact.mutate({
        artifact_type: type as 'notes' | 'flashcards' | 'quiz' | 'revision_plan',
        source_session_ids: sessionId ? [sessionId] : undefined,
      });
    },
    [generateArtifact, sessionId],
  );

  const appendToNotes = useCallback((text: string) => {
    const normalized = text.trim();
    if (!normalized) return;
    pendingNotesSourceRef.current = 'capture';
    setRightOpen(true);
    setFocusNotesSignal((value) => value + 1);
    setNotesDraft((current) => current.trim()
      ? `${current.trimEnd()}\n\n${normalized}`
      : normalized);
  }, []);

  const handleQuizSubmission = useCallback((signal: QuizSubmissionSignal) => {
    setQuizSignals((current) => ({
      ...current,
      [`${signal.artifactKey}:${signal.questionId}`]: signal,
    }));
  }, []);

  // Quick actions for empty state
  const quickActions = useMemo(() => [
    { label: 'Start learning', message: 'Let\'s begin studying this topic.' },
    { label: 'Explain concepts', message: 'Can you explain the key concepts?' },
    { label: 'Quiz me', message: 'Give me a quick quiz on what we\'ve covered.' },
    { label: 'Summarize', message: 'Can you summarize the main points?' },
  ], []);

  const completionPct = objectives.length > 0
    ? Math.round((objectives.filter((objective) => objective.status === 'completed').length / objectives.length) * 100)
    : turns.length > 0 ? Math.min(85, turns.length * 12) : 0;
  const quizSignalItems = useMemo(() => Object.values(quizSignals), [quizSignals]);
  const profiledWeakConcepts = useMemo(() => {
    const combined = new Set(weakConcepts);
    quizSignalItems.forEach((signal) => {
      if (!signal.wasCorrect && signal.concept) combined.add(signal.concept);
    });
    return Array.from(combined);
  }, [quizSignalItems, weakConcepts]);
  const masteryAverage = Object.keys(mastery).length > 0
    ? Math.round((Object.values(mastery).reduce((sum, value) => sum + value, 0) / Object.keys(mastery).length) * 100)
    : 0;

  const activeObjectiveSnapshot = useMemo(() => {
    if (studyMapSnapshot?.objectives?.length) {
      return studyMapSnapshot.objectives[studyMapSnapshot.current_objective_index] ?? studyMapSnapshot.objectives[0] ?? null;
    }
    if (!objectives.length) return null;
    const liveObjectiveId = turns[turns.length - 1]?.objective_id;
    return objectives.find((objective) => objective.objective_id === liveObjectiveId)
      ?? objectives.find((objective) => objective.status === 'active')
      ?? objectives[0]
      ?? null;
  }, [objectives, studyMapSnapshot, turns]);

  const collapsedObjectiveProgress = useMemo(() => {
    if (!activeObjectiveSnapshot) return null;

    const liveObjective = studyMapSnapshot?.objectives.find(
      (objective) => objective.objective_id === activeObjectiveSnapshot.objective_id,
    );

    if (liveObjective?.steps?.length) {
      const completedSteps = liveObjective.steps.filter((step) => step.status === 'completed').length;
      const activeStepOffset = liveObjective.steps.some((step) => step.status === 'active') ? 1 : 0;
      return `${Math.min(completedSteps + activeStepOffset, liveObjective.steps.length)}/${liveObjective.steps.length} steps`;
    }

    if (liveObjective?.status === 'completed') return 'Completed';
    if (liveObjective?.status === 'active') return 'In progress';
    return null;
  }, [activeObjectiveSnapshot, studyMapSnapshot]);

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Compact workspace toolbar */}
      <div className="shrink-0 border-b border-border/40 bg-card/80 backdrop-blur-sm">
        <div className="flex flex-wrap items-center gap-2 px-3 py-3">
          <button
            onClick={() => navigate(`/notebooks/${notebookId}`)}
            className="rounded-xl border border-border bg-card/80 p-1.5 text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
            title="Back to notebook"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
          </button>

          <div className="flex-1 min-w-0 flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="section-kicker text-[10px] text-gold">Study workspace</p>
              <h1 className="font-reading text-2xl text-foreground truncate">
                {notebook?.title || 'Study Workspace'}
              </h1>
            </div>
            {mode && (
              <span className="data-chip hidden sm:inline-flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-[10px] uppercase text-muted-foreground">
                <TimerReset className="h-2.5 w-2.5 text-gold" />
                {mode}
              </span>
            )}
            {!leftOpen && activeObjectiveSnapshot && (
              <div className="hidden lg:flex items-center gap-2 rounded-full border border-border/70 bg-background/80 px-3 py-1.5">
                <Target className="h-3 w-3 text-gold" />
                <span className="font-reading text-sm text-foreground truncate max-w-[220px]">
                  {activeObjectiveSnapshot.title}
                </span>
                {collapsedObjectiveProgress && (
                  <span className="data-chip rounded-full border border-gold/15 bg-gold/[0.06] px-2 py-0.5 text-[10px] text-gold">
                    {collapsedObjectiveProgress}
                  </span>
                )}
              </div>
            )}
            <div className="hidden xl:flex items-center gap-3 ml-auto text-[11px] text-muted-foreground font-ui uppercase tracking-[0.12em]">
              <span className="flex items-center gap-1.5">
                <Sparkles className="h-3 w-3 text-gold" />
                {completionPct}% progress
              </span>
              <span className="w-px h-3 bg-border" />
              <span className="flex items-center gap-1.5">
                <Brain className="h-3 w-3 text-gold" />
                {masteryAverage}% mastery
              </span>
              {profiledWeakConcepts.length > 0 && (
                <>
                  <span className="w-px h-3 bg-border" />
                  <span className="text-amber-600">{profiledWeakConcepts.length} needs review</span>
                </>
              )}
              {generateArtifact.isPending && (
                <>
                  <span className="w-px h-3 bg-border" />
                  <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-gold animate-pulse" />Generating…</span>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 md:ml-2">
            <button
              onClick={() => setLeftOpen(!leftOpen)}
              className={cn(
                'font-ui flex items-center gap-2 rounded-full border px-4 py-2 text-[12px] font-medium uppercase tracking-[0.12em] transition-colors',
                leftOpen
                  ? 'border-gold/25 bg-gold/[0.06] text-gold'
                  : 'border-border bg-background text-muted-foreground hover:text-foreground hover:bg-muted/50',
              )}
              title={leftOpen ? 'Hide study map' : 'Show study map'}
            >
              {leftOpen ? <PanelLeftClose className="w-3.5 h-3.5" /> : <PanelLeftOpen className="w-3.5 h-3.5" />}
              <span>Study Map</span>
            </button>
            <button
              onClick={() => setRightOpen(!rightOpen)}
              className={cn(
                'font-ui flex items-center gap-2 rounded-full border px-4 py-2 text-[12px] font-medium uppercase tracking-[0.12em] transition-colors',
                rightOpen
                  ? 'border-gold/25 bg-gold/[0.06] text-gold'
                  : 'border-border bg-background text-muted-foreground hover:text-foreground hover:bg-muted/50',
              )}
              title={rightOpen ? 'Hide artifacts' : 'Show artifacts'}
            >
              {rightOpen ? <PanelRightClose className="w-3.5 h-3.5" /> : <PanelRightOpen className="w-3.5 h-3.5" />}
              <span>Artifacts</span>
            </button>
          </div>
        </div>
      </div>

      {/* Three-panel workspace */}
      <div className="flex-1 overflow-hidden">
        <div
          id="study-workspace"
          className="flex h-full min-w-0"
        >
          {/* Left context panel */}
          {leftOpen && (
            <>
              <div
                id="context"
                className="hidden h-full w-[20rem] min-w-[17rem] max-w-[24rem] border-r border-border/40 bg-card/40 lg:block"
              >
                <ContextPanel
                  resources={resources}
                  resourceTopics={resourceTopics}
                  objectives={objectives}
                  mastery={mastery}
                  weakConcepts={profiledWeakConcepts}
                  mode={mode}
                  studyMapSnapshot={studyMapSnapshot}
                />
              </div>
              <ResizeHandle />
            </>
          )}

          {/* Center tutor panel */}
          <div id="tutor" className="min-w-0 flex-1">
            <TutorPanel
              turns={turns}
              isLoading={turnsLoading}
              isSending={sendMessage.isPending}
              onSendMessage={handleSendMessage}
              onAddToNotes={appendToNotes}
              activeCheckpoint={activeCheckpoint}
              sessionComplete={sessionComplete}
              onEndSession={() => navigate(`/notebooks/${notebookId}`)}
              quickActions={quickActions}
            />
          </div>

          {/* Right artifact panel */}
          {rightOpen && (
            <>
              <ResizeHandle />
              <div
                id="artifacts"
                className="hidden h-full w-[22rem] min-w-[18rem] max-w-[26rem] border-l border-border/40 bg-card/40 xl:block"
              >
                <ArtifactPanel
                  liveArtifacts={liveArtifacts}
                  savedArtifacts={savedArtifacts}
                  citations={citations}
                  notesDraft={notesDraft}
                  onNotesChange={handleNotesChange}
                  onAddToNotes={appendToNotes}
                  notesSyncStatus={notesSyncStatus}
                  focusNotesSignal={focusNotesSignal}
                  quizSignals={quizSignalItems}
                  onQuizSubmission={handleQuizSubmission}
                  onGenerateArtifact={handleGenerateArtifact}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
