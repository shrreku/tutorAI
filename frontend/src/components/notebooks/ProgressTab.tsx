import { useMemo, useState } from 'react';
import {
  BarChart3, Loader2, Wand2, CheckCircle2, AlertTriangle,
  BookOpen, Layers, MessageSquare,
  ChevronDown, ChevronRight, ChevronUp,
} from 'lucide-react';
import { useNotebookProgress, useNotebookArtifacts, useGenerateNotebookArtifact, useNotebookSessions } from '../../api/hooks';
import { ArtifactViewerCard } from '../ui/ArtifactViewer';

const ARTIFACT_TYPES = ['notes', 'flashcards', 'quiz', 'revision_plan'] as const;
const ARTIFACT_META: Record<string, { icon: typeof BookOpen; label: string; color: string }> = {
  notes:         { icon: BookOpen, label: 'Study Notes',   color: 'text-blue-400' },
  flashcards:    { icon: Layers,   label: 'Flashcards',    color: 'text-emerald-400' },
  quiz:          { icon: CheckCircle2, label: 'Quiz',      color: 'text-orange-400' },
  revision_plan: { icon: BarChart3, label: 'Revision Plan', color: 'text-purple-400' },
};

export default function ProgressTab({ notebookId }: { notebookId: string }) {
  const { data: progress, isLoading: progressLoading } = useNotebookProgress(notebookId);
  const { data: artifacts, isLoading: artifactsLoading } = useNotebookArtifacts(notebookId);
  const { data: notebookSessions } = useNotebookSessions(notebookId);
  const generateArtifact = useGenerateNotebookArtifact(notebookId);

  const [artifactType, setArtifactType] = useState<(typeof ARTIFACT_TYPES)[number]>('notes');
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([]);
  const [questionCount, setQuestionCount] = useState(5);
  const [horizonDays, setHorizonDays] = useState(5);
  const [showMastery, setShowMastery] = useState(false);
  const [showGenerator, setShowGenerator] = useState(false);

  const mastery = progress?.mastery_snapshot ?? {};
  const masteryEntries = Object.entries(mastery).sort(([, a], [, b]) => a - b);
  const masteryValues = Object.values(mastery);
  const avgMastery = masteryValues.length ? Math.round((masteryValues.reduce((a, b) => a + b, 0) / masteryValues.length) * 100) : 0;
  const weakConcepts = progress?.weak_concepts_snapshot ?? [];
  const artifactItems = artifacts?.items ?? [];
  const sessions = notebookSessions?.items ?? [];

  const coverage = useMemo(() => {
    const snapshot = progress?.coverage_snapshot;
    return snapshot && typeof snapshot === 'object'
      ? snapshot as Record<string, unknown>
      : {};
  }, [progress?.coverage_snapshot]);
  const topicCoverage = Array.isArray(coverage.topic_coverage)
    ? coverage.topic_coverage as Array<Record<string, unknown>>
    : [];
  const plannerState = progress?.notebook_planning_state?.planner_state;
  const plannedPercent = Math.round(Number(coverage.planned_percent ?? 0));
  const taughtPercent = Math.round(Number(coverage.taught_percent ?? 0));
  const masteredPercent = Math.round(Number(coverage.mastered_percent ?? 0));
  const plannedObjectives = Number(coverage.planned_objectives ?? 0);
  const totalObjectives = Number(coverage.total_objectives ?? 0);
  const activeSessionId = typeof plannerState?.active_session_id === 'string'
    ? plannerState.active_session_id
    : null;

  const handleToggleSession = (sessionId: string) => {
    setSelectedSessionIds((current) => current.includes(sessionId)
      ? current.filter((id) => id !== sessionId)
      : [...current, sessionId]);
  };

  const handleGenerate = () => {
    const options: Record<string, unknown> = {};
    if (artifactType === 'quiz') options.question_count = questionCount;
    if (artifactType === 'revision_plan') options.horizon_days = horizonDays;
    generateArtifact.mutate({
      artifact_type: artifactType,
      source_session_ids: selectedSessionIds,
      options,
    });
  };

  return (
    <div className="px-6 lg:px-8 py-6 animate-tab-enter">
      {/* Compact mastery summary bar */}
      <div className="flex flex-wrap items-center gap-4 mb-5 animate-fade-up">
        <div className="flex items-center gap-2.5">
          <div className="relative w-9 h-9">
            <svg viewBox="0 0 36 36" className="w-9 h-9 -rotate-90">
              <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none" stroke="hsl(var(--border))" strokeWidth="3.5" />
              <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none" stroke="hsl(var(--gold))" strokeWidth="3.5" strokeLinecap="round"
                strokeDasharray={`${avgMastery}, 100`} className="transition-all duration-700" />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-foreground">{avgMastery}%</span>
          </div>
          <div className="text-xs text-muted-foreground">
            <span className="text-foreground font-medium">{masteryEntries.length}</span> concepts
            <span className="mx-1.5 text-border">·</span>
            <span className="text-foreground font-medium">{progress?.sessions_count ?? 0}</span> sessions
            <span className="mx-1.5 text-border">·</span>
            <span className="text-foreground font-medium">{progress?.completed_sessions_count ?? 0}</span> completed
          </div>
        </div>

        {weakConcepts.length > 0 && (
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="w-3 h-3 text-red-400" />
            <span className="text-xs text-red-400">{weakConcepts.length} weak</span>
            <div className="hidden sm:flex gap-1 ml-1">
              {weakConcepts.slice(0, 3).map((c) => (
                <span key={c} className="px-1.5 py-0.5 rounded text-[9px] border border-red-500/15 bg-red-500/[0.06] text-red-400">{c}</span>
              ))}
              {weakConcepts.length > 3 && <span className="text-[9px] text-red-400/60">+{weakConcepts.length - 3}</span>}
            </div>
          </div>
        )}

        {/* Expand mastery details */}
        {masteryEntries.length > 0 && (
          <button onClick={() => setShowMastery(!showMastery)}
            className="ml-auto text-[11px] text-gold hover:text-gold/80 transition-colors inline-flex items-center gap-1">
            {showMastery ? 'Hide details' : 'View all concepts'}
            <ChevronRight className={`w-3 h-3 transition-transform duration-200 ${showMastery ? 'rotate-90' : ''}`} />
          </button>
        )}
      </div>

      {(Number(coverage.total_concepts ?? 0) > 0 || plannedObjectives > 0) && (
        <section className="grid gap-3 mb-5 md:grid-cols-[repeat(3,minmax(0,1fr))] animate-fade-up">
          <div className="rounded-xl border border-border bg-card px-4 py-3">
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-ui">Coverage</div>
            <div className="mt-2 flex items-end gap-2">
              <span className="text-2xl font-reading text-foreground">{masteredPercent}%</span>
              <span className="text-xs text-muted-foreground mb-1">mastered</span>
            </div>
            <div className="mt-2 text-[11px] text-muted-foreground space-y-1">
              <div className="flex items-center justify-between"><span>Planned</span><span className="text-foreground">{plannedPercent}%</span></div>
              <div className="flex items-center justify-between"><span>Taught</span><span className="text-foreground">{taughtPercent}%</span></div>
              <div className="flex items-center justify-between"><span>Concepts</span><span className="text-foreground">{Number(coverage.mastered_concepts ?? 0)}/{Number(coverage.total_concepts ?? 0)}</span></div>
            </div>
          </div>
          <div className="rounded-xl border border-border bg-card px-4 py-3">
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-ui">Planner</div>
            <div className="mt-2 flex items-end gap-2">
              <span className="text-2xl font-reading text-foreground">{plannedObjectives}</span>
              <span className="text-xs text-muted-foreground mb-1">planned objectives</span>
            </div>
            <div className="mt-2 text-[11px] text-muted-foreground space-y-1">
              <div className="flex items-center justify-between"><span>Objective coverage</span><span className="text-foreground">{totalObjectives > 0 ? Math.round(Number(coverage.objective_planned_percent ?? 0)) : 0}%</span></div>
              <div className="flex items-center justify-between"><span>Revision</span><span className="text-foreground">r{progress?.notebook_planning_state?.revision ?? 1}</span></div>
              <div className="flex items-center justify-between"><span>Active session</span><span className="text-foreground">{activeSessionId ? activeSessionId.slice(0, 8) : 'none'}</span></div>
            </div>
          </div>
          <div className="rounded-xl border border-border bg-card px-4 py-3">
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-ui">Top topics</div>
            <div className="mt-2 space-y-2">
              {topicCoverage.slice(0, 3).map((topic, index) => (
                <div key={`${String(topic.topic_id ?? topic.topic_name ?? index)}`}>
                  <div className="flex items-center justify-between gap-3 text-[11px]">
                    <span className="text-foreground truncate">{String(topic.topic_name ?? topic.topic_id ?? 'Untitled topic')}</span>
                    <span className="text-muted-foreground">{Math.round(Number(topic.mastered_percent ?? 0))}%</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-border overflow-hidden">
                    <div className="h-full rounded-full bg-gold transition-all" style={{ width: `${Math.max(0, Math.min(100, Number(topic.mastered_percent ?? 0)))}%` }} />
                  </div>
                </div>
              ))}
              {topicCoverage.length === 0 && (
                <p className="text-[11px] text-muted-foreground">Topic coverage will appear after planning and session activity.</p>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Collapsible mastery breakdown */}
      {showMastery && masteryEntries.length > 0 && (
        <section className="rounded-xl border border-border bg-card p-4 mb-5 animate-fade-up">
          {progressLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
          ) : (
            <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
              {masteryEntries.map(([concept, score]) => {
                const pct = Math.round(score * 100);
                const barColor = pct >= 80 ? 'from-emerald-500 to-emerald-400' : pct >= 50 ? 'from-gold to-amber-400' : 'from-red-500 to-red-400';
                return (
                  <div key={concept} className="flex items-center gap-2 py-0.5">
                    <span className="text-[11px] text-foreground w-28 truncate shrink-0" title={concept}>{concept}</span>
                    <div className="flex-1 h-1 rounded-full bg-border overflow-hidden">
                      <div className={`h-full rounded-full bg-gradient-to-r ${barColor} transition-all`} style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-[10px] text-muted-foreground w-7 text-right">{pct}%</span>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* Generate artifact */}
      <section className="rounded-xl border border-border bg-card overflow-hidden mb-6 animate-fade-up" style={{ animationDelay: '0.05s' }}>
        <button
          onClick={() => setShowGenerator(!showGenerator)}
          className="w-full flex items-center gap-3 px-5 py-3.5 text-left hover:bg-muted/30 transition-colors"
        >
          <Wand2 className="w-4 h-4 text-gold" />
          <span className="text-sm font-medium text-foreground flex-1">Generate Artifact</span>
          <div className="flex items-center gap-1.5">
            {ARTIFACT_TYPES.map((type) => {
              const meta = ARTIFACT_META[type];
              const Icon = meta.icon;
              return (
                <div key={type} className={`w-6 h-6 rounded-md flex items-center justify-center ${artifactType === type ? 'bg-gold/15' : 'bg-muted/50'}`}>
                  <Icon className={`w-3 h-3 ${artifactType === type ? 'text-gold' : 'text-muted-foreground'}`} />
                </div>
              );
            })}
          </div>
          {showGenerator ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
        </button>

        {showGenerator && (
          <div className="px-5 pb-5 pt-2 border-t border-border/30 space-y-4">
            <div className="grid gap-2 sm:grid-cols-4">
              {ARTIFACT_TYPES.map((type) => {
                const meta = ARTIFACT_META[type];
                const Icon = meta.icon;
                const active = artifactType === type;
                return (
                  <button key={type} type="button" onClick={() => setArtifactType(type)}
                    className={`rounded-xl border px-3 py-2.5 text-left transition-all ${active ? 'border-gold/30 bg-gold/10' : 'border-border hover:border-gold/20 hover:bg-muted/50'}`}>
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Icon className={`h-4 w-4 ${active ? 'text-gold' : meta.color}`} /> {meta.label}
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                  <MessageSquare className="h-3.5 w-3.5" /> Source sessions
                  <span className="font-normal normal-case tracking-normal text-muted-foreground/70">(leave empty for all)</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {sessions.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No sessions available yet.</p>
                  ) : sessions.slice(0, 8).map((session) => {
                    const active = selectedSessionIds.includes(session.session_id);
                    return (
                      <button key={session.id} type="button" onClick={() => handleToggleSession(session.session_id)}
                        className={`rounded-lg border px-3 py-1.5 text-xs transition-all ${active ? 'border-gold/30 bg-gold/10 text-gold' : 'border-border hover:border-gold/20 text-muted-foreground hover:text-foreground'}`}>
                        <span className="capitalize">{session.mode}</span>
                        <span className="ml-1.5 text-muted-foreground">{new Date(session.started_at).toLocaleDateString()}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex items-end gap-3">
                {artifactType === 'quiz' && (
                  <label className="space-y-1">
                    <span className="text-[11px] text-muted-foreground">Questions</span>
                    <div className="flex items-center gap-2">
                      <input type="range" min={3} max={10} value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))} className="w-20" />
                      <span className="text-xs text-foreground w-4">{questionCount}</span>
                    </div>
                  </label>
                )}
                {artifactType === 'revision_plan' && (
                  <label className="space-y-1">
                    <span className="text-[11px] text-muted-foreground">Days</span>
                    <div className="flex items-center gap-2">
                      <input type="range" min={3} max={10} value={horizonDays} onChange={(e) => setHorizonDays(Number(e.target.value))} className="w-20" />
                      <span className="text-xs text-foreground w-4">{horizonDays}</span>
                    </div>
                  </label>
                )}
                <button onClick={handleGenerate} disabled={generateArtifact.isPending}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gold text-primary-foreground text-sm font-medium disabled:opacity-50 hover:bg-gold/90 transition-colors whitespace-nowrap">
                  {generateArtifact.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
                  Generate {ARTIFACT_META[artifactType]?.label ?? artifactType}
                </button>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Artifacts list — full-width centre display */}
      <section className="space-y-3 animate-fade-up max-w-6xl" style={{ animationDelay: '0.1s' }}>
        {artifactsLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground p-4"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
        ) : artifactItems.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/60 bg-card/30 py-10 text-center">
            <Wand2 className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">No artifacts yet. Generate study materials above.</p>
          </div>
        ) : (
          artifactItems.map((a) => {
            const meta = ARTIFACT_META[a.artifact_type] ?? ARTIFACT_META.notes;
            return (
              <ArtifactViewerCard
                key={a.id}
                type={a.artifact_type}
                title={meta.label}
                subtitle={new Date(a.created_at).toLocaleDateString()}
                createdAt={a.created_at}
                payload={a.payload_json}
                downloadFileName={`${a.artifact_type}-${a.id.slice(0, 8)}.json`}
              />
            );
          })
        )}
      </section>
    </div>
  );
 }
