import { CheckCircle, TrendingUp, BookOpen, Target, ArrowRight, BarChart3, Sparkles, Clock, Zap, AlertCircle } from 'lucide-react';
import type { SessionSummaryResponse } from '../types/api';

function masteryLabel(value: number): { label: string; color: string } {
  if (value >= 0.7) return { label: 'Mastered', color: 'text-emerald-400' };
  if (value >= 0.5) return { label: 'Proficient', color: 'text-emerald-400' };
  if (value >= 0.25) return { label: 'Developing', color: 'text-gold' };
  if (value > 0) return { label: 'Introduced', color: 'text-muted-foreground' };
  return { label: 'Not started', color: 'text-muted-foreground/50' };
}

function masteryBarColor(value: number): string {
  if (value >= 0.7) return 'hsl(142 71% 45%)';
  if (value >= 0.5) return 'hsl(142 50% 50%)';
  if (value >= 0.25) return 'hsl(var(--gold))';
  return 'hsl(var(--muted-foreground))';
}

interface SessionReportCardProps {
  summary: SessionSummaryResponse;
  onStartQuiz?: () => void;
  onContinueLearning?: () => void;
  onBackToSessions?: () => void;
}

export default function SessionReportCard({
  summary,
  onStartQuiz,
  onContinueLearning,
  onBackToSessions,
}: SessionReportCardProps) {
  const masteryEntries = Object.entries(summary.mastery_snapshot)
    .filter(([, v]) => v > 0)
    .sort(([, a], [, b]) => b - a);

  const strongCount = summary.concepts_strong.length;
  const developingCount = summary.concepts_developing.length;
  const revisitCount = summary.concepts_to_revisit.length;

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Summary Header */}
      <div className="rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-5">
        <div className="flex items-start gap-3 mb-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-400/10 border border-emerald-400/20 flex items-center justify-center flex-shrink-0">
            <CheckCircle className="w-4.5 h-4.5 text-emerald-400" />
          </div>
          <div>
            <h3 className="font-display text-base font-semibold text-foreground">
              Session Complete
            </h3>
            {summary.topic && (
              <p className="text-xs text-muted-foreground mt-0.5">
                {summary.topic}
              </p>
            )}
          </div>
        </div>
        {summary.summary_text && (
          <div className="text-sm text-card-foreground/90 leading-relaxed whitespace-pre-wrap pl-12">
            {summary.summary_text}
          </div>
        )}
      </div>

      {/* Quick Stats Row */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-border bg-card p-3.5 text-center">
          <div className="flex items-center justify-center gap-1.5 mb-1.5">
            <Clock className="w-3.5 h-3.5 text-muted-foreground" />
          </div>
          <div className="text-lg font-display font-bold text-foreground">{summary.turn_count}</div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Turns</div>
        </div>
        <div className="rounded-xl border border-border bg-card p-3.5 text-center">
          <div className="flex items-center justify-center gap-1.5 mb-1.5">
            <Target className="w-3.5 h-3.5 text-muted-foreground" />
          </div>
          <div className="text-lg font-display font-bold text-foreground">{summary.objectives.length}</div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Objectives</div>
        </div>
        <div className="rounded-xl border border-border bg-card p-3.5 text-center">
          <div className="flex items-center justify-center gap-1.5 mb-1.5">
            <Zap className="w-3.5 h-3.5 text-muted-foreground" />
          </div>
          <div className="text-lg font-display font-bold text-foreground">{masteryEntries.length}</div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Concepts</div>
        </div>
      </div>

      {/* Objectives */}
      {summary.objectives.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <BookOpen className="w-3.5 h-3.5 text-gold" />
            <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
              Objectives Covered
            </span>
          </div>
          <div className="space-y-2.5">
            {summary.objectives.map((obj, i) => {
              const correct = obj.progress?.correct ?? 0;
              const attempts = obj.progress?.attempts ?? 0;
              const stepsCompleted = obj.progress?.steps_completed ?? 0;
              return (
                <div key={obj.objective_id || i} className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-md bg-emerald-400/10 border border-emerald-400/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <CheckCircle className="w-3 h-3 text-emerald-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-card-foreground truncate">
                      {obj.title || `Objective ${i + 1}`}
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {stepsCompleted} steps · {correct}/{attempts} correct
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Mastery Breakdown with Labels */}
      {masteryEntries.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 className="w-3.5 h-3.5 text-gold" />
            <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
              Concept Progress
            </span>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-3 mb-3 px-1">
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-[10px] text-muted-foreground">Proficient</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-gold" />
              <span className="text-[10px] text-muted-foreground">Developing</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: 'hsl(var(--muted-foreground))' }} />
              <span className="text-[10px] text-muted-foreground">Introduced</span>
            </div>
          </div>

          <div className="space-y-3">
            {masteryEntries.map(([concept, value]) => {
              const { label, color } = masteryLabel(value);
              const delta = value; // initial is always 0 for now
              return (
                <div key={concept} className="space-y-1">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-card-foreground truncate capitalize max-w-[170px]">
                      {concept.replace(/_/g, ' ')}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-medium ${color}`}>{label}</span>
                      <span className="text-[11px] text-muted-foreground font-mono">
                        {Math.round(value * 100)}%
                      </span>
                    </div>
                  </div>
                  <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-700 ease-out"
                      style={{
                        width: `${value * 100}%`,
                        backgroundColor: masteryBarColor(value),
                      }}
                    />
                  </div>
                  {delta > 0 && (
                    <div className="flex items-center gap-1 text-[10px] text-emerald-400/70">
                      <TrendingUp className="w-2.5 h-2.5" />
                      +{Math.round(delta * 100)}% this session
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Concept Summary Cards */}
      <div className="grid grid-cols-1 gap-2.5">
        {strongCount > 0 && (
          <div className="rounded-xl border border-emerald-400/15 bg-emerald-400/5 px-4 py-3 flex items-start gap-3">
            <Sparkles className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-medium text-emerald-400">Strong foundations</p>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
                {summary.concepts_strong.map(c => c.replace(/_/g, ' ')).join(', ')}
              </p>
            </div>
          </div>
        )}
        {developingCount > 0 && (
          <div className="rounded-xl border border-gold/15 bg-gold/5 px-4 py-3 flex items-start gap-3">
            <TrendingUp className="w-4 h-4 text-gold flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-medium text-gold">Building momentum</p>
              <p className="text-[11px] text-muted-foreground mt-0.5 leading-relaxed">
                {summary.concepts_developing.map(c => c.replace(/_/g, ' ')).join(', ')}
              </p>
            </div>
          </div>
        )}
        {revisitCount > 0 && (
          <div className="rounded-xl border border-border bg-card/50 px-4 py-3 flex items-start gap-3">
            <AlertCircle className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-medium text-muted-foreground">Next session targets</p>
              <p className="text-[11px] text-muted-foreground/70 mt-0.5 leading-relaxed">
                {summary.concepts_to_revisit.map(c => c.replace(/_/g, ' ')).join(', ')}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col gap-2.5 pt-1">
        {onStartQuiz && (
          <button
            onClick={onStartQuiz}
            className="flex items-center justify-center gap-2 w-full px-4 py-3 rounded-xl bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-all"
          >
            <Target className="w-4 h-4" />
            Take a Quiz to Reinforce
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
        {onContinueLearning && (
          <button
            onClick={onContinueLearning}
            className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl border border-border text-card-foreground text-sm font-medium hover:bg-card hover:border-gold/20 transition-all"
          >
            <BookOpen className="w-4 h-4" />
            Continue Learning
          </button>
        )}
        {onBackToSessions && (
          <button
            onClick={onBackToSessions}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors py-1"
          >
            Back to all sessions
          </button>
        )}
      </div>
    </div>
  );
}
