import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, BarChart3, Loader2, Wand2, CheckCircle2, AlertTriangle,
  BookOpen, Layers, MessageSquare,
} from 'lucide-react';
import { useNotebook, useNotebookProgress, useNotebookArtifacts, useGenerateNotebookArtifact, useNotebookSessions } from '../api/hooks';
import { ArtifactViewerCard } from '../components/ui/ArtifactViewer';

const ARTIFACT_TYPES = ['notes', 'flashcards', 'quiz', 'revision_plan'] as const;
const ARTIFACT_META: Record<string, { icon: typeof BookOpen; label: string; color: string }> = {
  notes:         { icon: BookOpen, label: 'Study Notes',   color: 'text-blue-400' },
  flashcards:    { icon: Layers,   label: 'Flashcards',    color: 'text-emerald-400' },
  quiz:          { icon: CheckCircle2, label: 'Quiz',      color: 'text-orange-400' },
  revision_plan: { icon: BarChart3, label: 'Revision Plan', color: 'text-purple-400' },
};

export default function NotebookProgressArtifactsPage() {
  const navigate = useNavigate();
  const { notebookId = '' } = useParams<{ notebookId: string }>();

  const { data: notebook } = useNotebook(notebookId);
  const { data: progress, isLoading: progressLoading } = useNotebookProgress(notebookId);
  const { data: artifacts, isLoading: artifactsLoading } = useNotebookArtifacts(notebookId);
  const { data: notebookSessions } = useNotebookSessions(notebookId);
  const generateArtifact = useGenerateNotebookArtifact(notebookId);

  const [artifactType, setArtifactType] = useState<(typeof ARTIFACT_TYPES)[number]>('notes');
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([]);
  const [questionCount, setQuestionCount] = useState(5);
  const [horizonDays, setHorizonDays] = useState(5);

  const mastery = progress?.mastery_snapshot ?? {};
  const masteryEntries = Object.entries(mastery).sort(([, a], [, b]) => a - b);
  const masteryValues = Object.values(mastery);
  const avgMastery = masteryValues.length ? Math.round((masteryValues.reduce((a, b) => a + b, 0) / masteryValues.length) * 100) : 0;
  const weakConcepts = progress?.weak_concepts_snapshot ?? [];
  const artifactItems = artifacts?.items ?? [];
  const sessions = notebookSessions?.items ?? [];

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
    <div className="h-full flex flex-col overflow-auto">
      {/* Header */}
      <div className="px-8 pt-8 pb-2">
        <button onClick={() => navigate(`/notebooks/${notebookId}`)} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-5 transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to notebook
        </button>
        <div className="flex items-center gap-2 mb-2">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">Progress & Artifacts</span>
        </div>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground mb-1">{notebook?.title || 'Notebook'}</h1>
        <p className="text-sm text-muted-foreground">Track mastery, review weak concepts, and generate study materials.</p>
      </div>

      {/* Content */}
      <div className="px-8 py-6 grid lg:grid-cols-5 gap-6">
        {/* Left: Progress (3/5) */}
        <div className="lg:col-span-3 space-y-5">
          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 animate-fade-up">
            <div className="rounded-lg border border-border bg-card p-3">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Avg mastery</p>
              <p className="text-2xl font-display font-semibold text-foreground">{avgMastery}<span className="text-sm text-muted-foreground">%</span></p>
            </div>
            <div className="rounded-lg border border-border bg-card p-3">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Concepts</p>
              <p className="text-2xl font-display font-semibold text-foreground">{masteryEntries.length}</p>
            </div>
            <div className="rounded-lg border border-border bg-card p-3">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Sessions</p>
              <p className="text-2xl font-display font-semibold text-foreground">{progress?.sessions_count ?? 0}</p>
            </div>
            <div className="rounded-lg border border-border bg-card p-3">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Completed</p>
              <p className="text-2xl font-display font-semibold text-foreground">{progress?.completed_sessions_count ?? 0}</p>
            </div>
          </div>

          {/* Mastery bars */}
          <section className="rounded-xl border border-border bg-card p-5 animate-fade-up" style={{ animationDelay: '0.05s' }}>
            <div className="flex items-center gap-2 mb-4 text-gold text-sm font-medium">
              <BarChart3 className="w-4 h-4" /> Concept Mastery
            </div>
            {progressLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
            ) : masteryEntries.length === 0 ? (
              <p className="text-xs text-muted-foreground">No mastery data yet. Complete study sessions to see progress.</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-auto">
                {masteryEntries.map(([concept, score]) => {
                  const pct = Math.round(score * 100);
                  const barColor = pct >= 80 ? 'from-emerald-500 to-emerald-400' : pct >= 50 ? 'from-gold to-amber-400' : 'from-red-500 to-red-400';
                  return (
                    <div key={concept} className="flex items-center gap-3">
                      <span className="text-xs text-foreground w-32 truncate shrink-0" title={concept}>{concept}</span>
                      <div className="flex-1 h-2 rounded-full bg-border overflow-hidden">
                        <div className={`h-full rounded-full bg-gradient-to-r ${barColor} transition-all`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-[10px] text-muted-foreground w-8 text-right">{pct}%</span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Weak concepts */}
          {weakConcepts.length > 0 && (
            <section className="rounded-xl border border-border bg-card p-5 animate-fade-up" style={{ animationDelay: '0.1s' }}>
              <div className="flex items-center gap-2 mb-3 text-sm font-medium">
                <AlertTriangle className="w-4 h-4 text-red-400" />
                <span className="text-red-400">Weak Concepts</span>
                <span className="text-[10px] text-muted-foreground ml-auto">{weakConcepts.length} concepts need attention</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {weakConcepts.map((c) => (
                  <span key={c} className="px-2.5 py-1 rounded-lg text-xs border border-red-500/15 bg-red-500/[0.06] text-red-400">{c}</span>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* Right: Artifacts (2/5) */}
        <div className="lg:col-span-2 space-y-4">
          {/* Generate */}
          <div className="rounded-xl border border-border bg-card p-5 animate-fade-up" style={{ animationDelay: '0.05s' }}>
            <div className="flex items-center gap-2 mb-3 text-gold text-sm font-medium">
              <Wand2 className="w-4 h-4" /> Generate Artifact
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {ARTIFACT_TYPES.map((type) => {
                const meta = ARTIFACT_META[type];
                const Icon = meta.icon;
                const active = artifactType === type;
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setArtifactType(type)}
                    className={`rounded-2xl border px-4 py-3 text-left transition-all ${active ? 'border-gold/30 bg-gold/10' : 'border-border hover:border-gold/20 hover:bg-muted/50'}`}
                  >
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Icon className={`h-4 w-4 ${meta.color}`} /> {meta.label}
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="mt-4 space-y-3 rounded-2xl border border-border/70 bg-background/60 p-4">
              <div>
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                  <MessageSquare className="h-3.5 w-3.5" /> Source sessions
                </div>
                <p className="mt-1 text-xs text-muted-foreground">Leave this empty to use the whole notebook history. Select specific sessions when you want a scoped artifact.</p>
              </div>
              <div className="space-y-2 max-h-40 overflow-auto pr-1">
                {sessions.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No notebook sessions available yet.</p>
                ) : sessions.slice(0, 8).map((session) => {
                  const active = selectedSessionIds.includes(session.session_id);
                  return (
                    <button
                      key={session.id}
                      type="button"
                      onClick={() => handleToggleSession(session.session_id)}
                      className={`w-full rounded-xl border px-3 py-2 text-left transition-all ${active ? 'border-gold/30 bg-gold/10' : 'border-border hover:border-gold/20 hover:bg-card'}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-medium capitalize text-foreground">{session.mode}</span>
                        <span className="text-[11px] text-muted-foreground">{new Date(session.started_at).toLocaleDateString()}</span>
                      </div>
                    </button>
                  );
                })}
              </div>

              {artifactType === 'quiz' && (
                <label className="block space-y-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">Question count</span>
                  <input type="range" min={3} max={10} value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))} className="w-full" />
                  <div className="text-xs text-muted-foreground">{questionCount} questions</div>
                </label>
              )}

              {artifactType === 'revision_plan' && (
                <label className="block space-y-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">Plan horizon</span>
                  <input type="range" min={3} max={10} value={horizonDays} onChange={(e) => setHorizonDays(Number(e.target.value))} className="w-full" />
                  <div className="text-xs text-muted-foreground">{horizonDays} days</div>
                </label>
              )}

              <button onClick={handleGenerate} disabled={generateArtifact.isPending}
                className="w-full px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium disabled:opacity-50 hover:bg-gold/90 transition-colors inline-flex items-center justify-center gap-2">
                {generateArtifact.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
                Generate {ARTIFACT_META[artifactType]?.label ?? artifactType}
              </button>
            </div>
          </div>

          {/* List */}
          <div className="space-y-2">
            {artifactsLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground p-4"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
            ) : artifactItems.length === 0 ? (
              <div className="rounded-xl border border-border bg-card p-6 text-center">
                <Wand2 className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
                <p className="text-xs text-muted-foreground">No artifacts yet. Generate study materials above.</p>
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
          </div>
        </div>
      </div>
    </div>
  );
}
