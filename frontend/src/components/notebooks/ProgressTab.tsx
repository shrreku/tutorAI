import { useState } from 'react';
import {
  BarChart3, Loader2, Wand2, CheckCircle2, AlertTriangle,
  BookOpen, Layers, ChevronDown, ChevronUp, Download, MessageSquare,
  ChevronRight,
} from 'lucide-react';
import { useNotebookProgress, useNotebookArtifacts, useGenerateNotebookArtifact, useNotebookSessions } from '../../api/hooks';
import type { NotebookArtifact } from '../../types/api';

const ARTIFACT_TYPES = ['notes', 'flashcards', 'quiz', 'revision_plan'] as const;
const ARTIFACT_META: Record<string, { icon: typeof BookOpen; label: string; color: string }> = {
  notes:         { icon: BookOpen, label: 'Study Notes',   color: 'text-blue-400' },
  flashcards:    { icon: Layers,   label: 'Flashcards',    color: 'text-emerald-400' },
  quiz:          { icon: CheckCircle2, label: 'Quiz',      color: 'text-orange-400' },
  revision_plan: { icon: BarChart3, label: 'Revision Plan', color: 'text-purple-400' },
};

function ArtifactContent({ artifact }: { artifact: NotebookArtifact }) {
  const payload = artifact.payload_json;
  if (!payload || Object.keys(payload).length === 0) return <p className="text-xs text-muted-foreground italic">Empty artifact.</p>;

  const type = artifact.artifact_type;

  if (type === 'notes' && Array.isArray(payload.sections)) {
    return (
      <div className="space-y-4">
        {typeof payload.summary === 'string' && <p className="text-sm leading-relaxed text-foreground">{payload.summary}</p>}
        {(payload.sections as Array<Record<string, unknown>>).map((section, index) => (
          <div key={`${section.heading ?? index}`} className="rounded-xl border border-border/60 bg-background/60 p-4">
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
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-gold shrink-0" />
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
                <span key={action} className="rounded-full border border-border px-3 py-1.5 text-xs text-foreground">{action}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (type === 'flashcards') {
    const cards = (payload.cards ?? payload.flashcards ?? (Array.isArray(payload) ? payload : [])) as Array<Record<string, string>>;
    if (Array.isArray(cards) && cards.length > 0) {
      return (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {cards.slice(0, 20).map((card, i) => (
            <div key={i} className="rounded-xl border border-border/50 bg-background/40 p-4 space-y-2 hover:border-gold/15 transition-colors">
              <p className="text-sm font-semibold text-foreground">{card.front ?? card.question ?? `Card ${i + 1}`}</p>
              {card.study_hint && <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{card.study_hint}</p>}
              <div className="h-px bg-border/30" />
              <p className="text-sm text-muted-foreground">{card.back ?? card.answer ?? '—'}</p>
            </div>
          ))}
        </div>
      );
    }
  }

  if (type === 'quiz') {
    const questions = (payload.questions ?? (Array.isArray(payload) ? payload : [])) as Array<Record<string, unknown>>;
    if (Array.isArray(questions) && questions.length > 0) {
      return (
        <div className="grid gap-3 lg:grid-cols-2">
          {questions.slice(0, 20).map((q, i) => (
            <div key={i} className="rounded-xl border border-border/50 bg-background/40 p-4">
              <p className="text-sm font-medium text-foreground mb-2">{i + 1}. {String(q.question ?? q.text ?? '')}</p>
              {Array.isArray(q.options) && (
                <ul className="space-y-1.5 mb-2">
                  {(q.options as string[]).map((opt, j) => (
                    <li key={j} className="text-sm text-muted-foreground flex items-start gap-2">
                      <span className="w-5 h-5 rounded-full border border-border flex items-center justify-center text-[10px] shrink-0 mt-0.5">{String.fromCharCode(65 + j)}</span>
                      {String(opt)}
                    </li>
                  ))}
                </ul>
              )}
              {(q.correct_answer ?? q.answer) != null && <p className="text-xs text-emerald-400 mt-1.5">Answer: {String(q.correct_answer ?? q.answer)}</p>}
              {q.explanation != null && <p className="text-xs text-muted-foreground mt-1">{String(q.explanation)}</p>}
            </div>
          ))}
        </div>
      );
    }
  }

  if (type === 'revision_plan') {
    const steps = (payload.days ?? payload.steps ?? payload.items ?? payload.plan ?? payload.schedule ?? (Array.isArray(payload) ? payload : [])) as Array<Record<string, unknown>>;
    if (Array.isArray(steps) && steps.length > 0) {
      return (
        <div className="grid gap-3 lg:grid-cols-2">
          {steps.slice(0, 20).map((step, i) => (
            <div key={i} className="flex gap-3 rounded-xl border border-border/50 bg-background/40 p-4">
              <span className="w-7 h-7 rounded-full bg-gold/10 border border-gold/20 flex items-center justify-center text-xs text-gold font-semibold shrink-0">{i + 1}</span>
              <div>
                <div className="text-sm font-medium text-foreground">{String(step.day_label ?? step.title ?? step.topic ?? `Day ${i + 1}`)}</div>
                <div className="mt-1 text-xs text-muted-foreground">{String(step.rationale ?? step.description ?? step.concept ?? '')}</div>
                {Array.isArray(step.activities) && step.activities.length > 0 && (
                  <ul className="mt-2 space-y-1 text-xs text-foreground">
                    {(step.activities as string[]).map((activity) => <li key={activity}>• {activity}</li>)}
                  </ul>
                )}
              </div>
            </div>
          ))}
        </div>
      );
    }
  }

  if (type === 'notes') {
    const text = typeof payload === 'string' ? payload : (payload.content ?? payload.summary ?? payload.text ?? payload.notes ?? null);
    if (typeof text === 'string') {
      return <div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{text}</div>;
    }
  }

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
    <div className="rounded-xl border border-border bg-card overflow-hidden transition-all hover:border-gold/10">
      <button onClick={() => setExpanded(!expanded)} className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-muted/30 transition-colors">
        <div className={`w-9 h-9 rounded-lg border border-border/50 flex items-center justify-center shrink-0 ${expanded ? 'bg-gold/10 border-gold/20' : ''}`}>
          <Icon className={`w-4 h-4 ${expanded ? 'text-gold' : meta.color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">{meta.label}</p>
          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span>{new Date(artifact.created_at).toLocaleString()}</span>
            {typeof generation.strategy === 'string' && <span className="rounded-full border border-border px-2 py-0.5">{String(generation.strategy)}</span>}
            {sourceCounts.sessions != null && <span className="rounded-full border border-border px-2 py-0.5">{String(sourceCounts.sessions)} sessions</span>}
          </div>
        </div>
        <button onClick={(e) => { e.stopPropagation(); handleDownload(); }} className="text-muted-foreground hover:text-gold transition-colors p-1.5 rounded-md hover:bg-gold/10">
          <Download className="w-3.5 h-3.5" />
        </button>
        {expanded ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
      </button>
      {expanded && (
        <div className="px-5 pb-5 pt-2 border-t border-border/30">
          <ArtifactContent artifact={artifact} />
        </div>
      )}
    </div>
  );
}

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
            <Wand2 className="w-8 h-8 text-muted-foreground/20 mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">No artifacts yet. Generate study materials above.</p>
          </div>
        ) : (
          artifactItems.map((a) => <ArtifactCard key={a.id} artifact={a} />)
        )}
      </section>
    </div>
  );
}
