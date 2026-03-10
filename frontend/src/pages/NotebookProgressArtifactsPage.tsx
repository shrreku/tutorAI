import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, BarChart3, Loader2, Wand2, CheckCircle2, AlertTriangle,
  BookOpen, Layers, ChevronDown, ChevronUp, Download, MessageSquare,
} from 'lucide-react';
import { useNotebook, useNotebookProgress, useNotebookArtifacts, useGenerateNotebookArtifact, useNotebookSessions } from '../api/hooks';
import type { NotebookArtifact } from '../types/api';

const ARTIFACT_TYPES = ['notes', 'flashcards', 'quiz', 'revision_plan'] as const;
const ARTIFACT_META: Record<string, { icon: typeof BookOpen; label: string; color: string }> = {
  notes:         { icon: BookOpen, label: 'Study Notes',   color: 'text-blue-400' },
  flashcards:    { icon: Layers,   label: 'Flashcards',    color: 'text-emerald-400' },
  quiz:          { icon: CheckCircle2, label: 'Quiz',      color: 'text-orange-400' },
  revision_plan: { icon: BarChart3, label: 'Revision Plan', color: 'text-purple-400' },
};

/* Format artifact payload as pretty structured content instead of raw JSON */
function ArtifactContent({ artifact }: { artifact: NotebookArtifact }) {
  const payload = artifact.payload_json;
  if (!payload || Object.keys(payload).length === 0) return <p className="text-xs text-muted-foreground italic">Empty artifact.</p>;

  const type = artifact.artifact_type;

  if (type === 'notes' && Array.isArray(payload.sections)) {
    return (
      <div className="space-y-4">
        {typeof payload.summary === 'string' && <p className="text-sm leading-relaxed text-foreground">{payload.summary}</p>}
        {(payload.sections as Array<Record<string, unknown>>).map((section, index) => (
          <div key={`${section.heading ?? index}`} className="rounded-2xl border border-border/60 bg-background/60 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-sm font-semibold text-foreground">{String(section.heading ?? `Section ${index + 1}`)}</h4>
              {Array.isArray(section.source_session_ids) && section.source_session_ids.length > 0 && (
                <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground">
                  {section.source_session_ids.length} session sources
                </span>
              )}
            </div>
            {Array.isArray(section.bullets) && section.bullets.length > 0 && (
              <ul className="mt-3 space-y-2 text-sm text-foreground">
                {(section.bullets as string[]).map((bullet, bulletIndex) => (
                  <li key={bulletIndex} className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-gold" />
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
            )}
            {typeof section.key_takeaway === 'string' && (
              <p className="mt-3 rounded-xl border border-gold/15 bg-gold/10 px-3 py-2 text-xs text-foreground">
                Key takeaway: {section.key_takeaway}
              </p>
            )}
          </div>
        ))}
        {Array.isArray(payload.next_actions) && payload.next_actions.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Next actions</p>
            <div className="flex flex-wrap gap-2">
              {(payload.next_actions as string[]).map((action) => (
                <span key={action} className="rounded-full border border-border px-3 py-1.5 text-xs text-foreground">
                  {action}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // flashcards: expect { cards: [{ front, back }] } or similar
  if (type === 'flashcards') {
    const cards = (payload.cards ?? payload.flashcards ?? (Array.isArray(payload) ? payload : [])) as Array<Record<string, string>>;
    if (Array.isArray(cards) && cards.length > 0) {
      return (
        <div className="grid gap-2 sm:grid-cols-2">
          {cards.slice(0, 20).map((card, i) => (
            <div key={i} className="rounded-lg border border-border/50 p-3 space-y-1.5">
              <p className="text-xs font-semibold text-foreground">{card.front ?? card.question ?? `Card ${i+1}`}</p>
              {card.study_hint && <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{card.study_hint}</p>}
              <div className="h-px bg-border/30" />
              <p className="text-xs text-muted-foreground">{card.back ?? card.answer ?? '—'}</p>
            </div>
          ))}
        </div>
      );
    }
  }

  // quiz: expect { questions: [{ question, options?, answer }] }
  if (type === 'quiz') {
    const questions = (payload.questions ?? (Array.isArray(payload) ? payload : [])) as Array<Record<string, unknown>>;
    if (Array.isArray(questions) && questions.length > 0) {
      return (
        <div className="space-y-3">
          {questions.slice(0, 20).map((q, i) => (
            <div key={i} className="rounded-lg border border-border/50 p-3">
              <p className="text-xs font-medium text-foreground mb-1.5">{i+1}. {String(q.question ?? q.text ?? '')}</p>
              {Array.isArray(q.options) && (
                <ul className="space-y-1">
                  {(q.options as string[]).map((opt, j) => (
                    <li key={j} className="text-xs text-muted-foreground flex items-start gap-1.5">
                      <span className="w-4 h-4 rounded-full border border-border flex items-center justify-center text-[9px] shrink-0 mt-0.5">{String.fromCharCode(65 + j)}</span>
                      {String(opt)}
                    </li>
                  ))}
                </ul>
              )}
              {(q.correct_answer ?? q.answer) != null && <p className="text-[10px] text-emerald-400 mt-1.5">Answer: {String(q.correct_answer ?? q.answer)}</p>}
              {q.explanation != null && <p className="text-[10px] text-muted-foreground mt-1">{String(q.explanation)}</p>}
            </div>
          ))}
        </div>
      );
    }
  }

  // revision_plan: expect { steps/items/plan: [...] } or { concepts: [...], schedule: [...] }
  if (type === 'revision_plan') {
    const steps = (payload.days ?? payload.steps ?? payload.items ?? payload.plan ?? payload.schedule ?? (Array.isArray(payload) ? payload : [])) as Array<Record<string, unknown>>;
    if (Array.isArray(steps) && steps.length > 0) {
      return (
        <ol className="space-y-2">
          {steps.slice(0, 20).map((step, i) => (
            <li key={i} className="flex gap-3">
              <span className="w-6 h-6 rounded-full bg-gold/10 border border-gold/20 flex items-center justify-center text-[10px] text-gold font-semibold shrink-0">{i+1}</span>
              <div className="pt-1">
                <div className="text-xs font-medium text-foreground">{String(step.day_label ?? step.title ?? step.topic ?? `Day ${i + 1}`)}</div>
                <div className="mt-1 text-xs text-muted-foreground">{String(step.rationale ?? step.description ?? step.concept ?? '')}</div>
                {Array.isArray(step.activities) && step.activities.length > 0 && (
                  <ul className="mt-2 space-y-1 text-xs text-foreground">
                    {(step.activities as string[]).map((activity) => <li key={activity}>• {activity}</li>)}
                  </ul>
                )}
              </div>
            </li>
          ))}
        </ol>
      );
    }
  }

  // notes: expect { content/summary/text: string } or string values
  if (type === 'notes') {
    const text = typeof payload === 'string' ? payload : (payload.content ?? payload.summary ?? payload.text ?? payload.notes ?? null);
    if (typeof text === 'string') {
      return <div className="text-xs text-foreground leading-relaxed whitespace-pre-wrap">{text}</div>;
    }
  }

  // Fallback: pretty-print JSON
  return <pre className="text-[11px] text-muted-foreground whitespace-pre-wrap break-words leading-relaxed">{JSON.stringify(payload, null, 2)}</pre>;
}

function ArtifactCard({ artifact }: { artifact: NotebookArtifact }) {
  const [expanded, setExpanded] = useState(false);
  const meta = ARTIFACT_META[artifact.artifact_type] ?? ARTIFACT_META.notes;
  const Icon = meta.icon;
  const generation = (artifact.payload_json?.generation ?? {}) as Record<string, unknown>;
  const sourceCounts = (artifact.payload_json?.source_counts ?? {}) as Record<string, unknown>;

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(artifact.payload_json, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.artifact_type}-${artifact.id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/30 transition-colors">
        <Icon className={`w-4 h-4 shrink-0 ${meta.color}`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">{meta.label}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
            <span>{new Date(artifact.created_at).toLocaleString()}</span>
            {typeof generation.strategy === 'string' && <span className="rounded-full border border-border px-2 py-0.5">{String(generation.strategy)}</span>}
            {sourceCounts.sessions != null && <span className="rounded-full border border-border px-2 py-0.5">{String(sourceCounts.sessions)} sessions</span>}
          </div>
        </div>
        <button onClick={(e) => { e.stopPropagation(); handleDownload(); }} className="text-muted-foreground hover:text-gold transition-colors p-1">
          <Download className="w-3.5 h-3.5" />
        </button>
        {expanded ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
      </button>
      {expanded && (
        <div className="px-4 pb-4 pt-1 border-t border-border/30">
          <ArtifactContent artifact={artifact} />
        </div>
      )}
    </div>
  );
}

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
              artifactItems.map((a) => <ArtifactCard key={a.id} artifact={a} />)
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
