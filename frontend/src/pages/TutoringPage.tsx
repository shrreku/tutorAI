import { useState, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Send, ArrowLeft, CheckCircle, Sparkles, Loader2, Square, Info, Target, BarChart3 } from 'lucide-react';
import { useSession, useTurns, useEndSession, useSendMessage, useSessionSummary } from '../api/hooks';
import SessionReportCard from '../components/SessionReportCard';
import type { SessionSummaryResponse } from '../types/api';

export default function TutoringPage() {
  const { id: sessionId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [showEndConfirm, setShowEndConfirm] = useState(false);
  const [endSessionSummary, setEndSessionSummary] = useState<SessionSummaryResponse | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { data: session, isLoading: sessionLoading } = useSession(sessionId || '');
  const { data: turnsData } = useTurns(sessionId || '');
  const { data: fetchedSummary } = useSessionSummary(
    session?.status === 'completed' ? (sessionId || '') : ''
  );
  const sendMessage = useSendMessage();
  const endSession = useEndSession();

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turnsData?.turns]);

  useEffect(() => {
    if (session?.status === 'active') {
      inputRef.current?.focus();
    }
  }, [session?.status]);

  // Check if the last turn response contains session_complete (inline completion)
  const lastTurnComplete = sendMessage.data?.session_complete ?? false;
  const inlineSummary = sendMessage.data?.session_summary ?? null;

  // Build a SessionSummaryResponse from inline data if available
  const effectiveSummary: SessionSummaryResponse | null =
    endSessionSummary ||
    (inlineSummary
      ? {
          session_id: sessionId || '',
          status: 'completed',
          topic: inlineSummary.topic,
          turn_count: inlineSummary.turn_count,
          summary_text: inlineSummary.summary_text,
          concepts_strong: inlineSummary.concepts_strong,
          concepts_developing: inlineSummary.concepts_developing,
          concepts_to_revisit: inlineSummary.concepts_to_revisit,
          objectives: inlineSummary.objectives,
          mastery_snapshot: inlineSummary.mastery_snapshot,
        }
      : null) ||
    fetchedSummary ||
    null;

  const isCompleted = session?.status === 'completed' || lastTurnComplete;

  const handleSend = async () => {
    if (!input.trim() || sendMessage.isPending || !sessionId) return;

    const message = input.trim();
    setInput('');

    try {
      await sendMessage.mutateAsync({
        session_id: sessionId,
        message,
      });
    } catch (error) {
      console.error('Send failed:', error);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleEndSession = async () => {
    if (sessionId) {
      try {
        const summary = await endSession.mutateAsync(sessionId);
        setEndSessionSummary(summary);
        setShowEndConfirm(false);
      } catch (error) {
        console.error('End session failed:', error);
      }
    }
  };

  if (sessionLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 text-gold animate-spin" />
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-muted-foreground text-sm">Session not found</p>
        <button
          onClick={() => navigate('/sessions')}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-colors"
        >
          Back to Sessions
        </button>
      </div>
    );
  }

  const planState = session.plan_state as Record<string, unknown> | null;
  const objectiveQueue = (planState?.objective_queue as Array<Record<string, unknown>>) || [];
  const currentObjIndex = (planState?.current_objective_index as number) || 0;
  const currentObjective = objectiveQueue[currentObjIndex];
  const stepRoadmap =
    (currentObjective?.step_roadmap as Array<Record<string, unknown>>) ||
    (currentObjective?.phase_skeleton as Array<Record<string, unknown>>) ||
    [];
  const stepIndex =
    ((planState?.current_step_index as number) ?? (planState?.curriculum_phase_index as number) ?? 0);
  const conceptState = (planState?.student_concept_state as Record<string, unknown>) || {};
  const legacyMastery = (planState?.mastery_state as Record<string, number>) || {};
  const mastery: Record<string, number> = Object.keys(conceptState).length
    ? Object.fromEntries(
        Object.entries(conceptState).map(([concept, value]) => {
          if (typeof value === 'number') {
            return [concept, value];
          }
          if (value && typeof value === 'object') {
            const maybeMean = (value as Record<string, unknown>).mastery_mean;
            return [concept, typeof maybeMean === 'number' ? maybeMean : 0];
          }
          return [concept, 0];
        })
      )
    : legacyMastery;
  const masteryEntries = Object.entries(mastery).filter(([, v]) => v > 0);
  const stepProgress = stepRoadmap.length > 0 ? ((stepIndex + 1) / stepRoadmap.length) * 100 : 0;

  // Mastery label helper
  const getMasteryLabel = (value: number): { label: string; color: string } => {
    if (value >= 0.7) return { label: 'Mastered', color: 'text-emerald-400' };
    if (value >= 0.5) return { label: 'Proficient', color: 'text-emerald-400' };
    if (value >= 0.25) return { label: 'Developing', color: 'text-gold' };
    if (value > 0) return { label: 'Introduced', color: 'text-muted-foreground' };
    return { label: '', color: 'text-muted-foreground/50' };
  };

  return (
    <div className="flex h-full">
      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/sessions')}
              className="w-8 h-8 rounded-lg border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:border-gold/20 transition-all"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-lg font-semibold text-foreground">
                  Tutoring Session
                </h2>
                {session.status === 'active' && !lastTurnComplete && (
                  <div className="w-2 h-2 rounded-full bg-gold animate-pulse-gold" />
                )}
              </div>
              {currentObjective && !isCompleted && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {(currentObjective.title as string) || 'Learning in progress'}
                </p>
              )}
              {isCompleted && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  Session finished
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {session.status === 'active' && !lastTurnComplete && (
              <div className="relative">
                <button
                  onClick={() => setShowEndConfirm(!showEndConfirm)}
                  disabled={endSession.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:border-destructive/30 transition-all disabled:opacity-50"
                >
                  {endSession.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Square className="w-3 h-3" />}
                  End
                </button>
                {showEndConfirm && (
                  <div className="absolute right-0 top-full mt-2 w-64 rounded-xl border border-border bg-card p-4 shadow-lg z-50 animate-fade-up">
                    <p className="text-sm text-card-foreground mb-3">
                      End this session? You'll get a summary of your progress.
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={handleEndSession}
                        disabled={endSession.isPending}
                        className="flex-1 px-3 py-1.5 rounded-lg bg-gold/10 border border-gold/20 text-xs font-medium text-gold hover:bg-gold/20 transition-all disabled:opacity-50"
                      >
                        {endSession.isPending ? 'Ending...' : 'End & Summarize'}
                      </button>
                      <button
                        onClick={() => setShowEndConfirm(false)}
                        className="px-3 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
            {isCompleted && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-400/10 border border-emerald-400/20 text-xs font-medium text-emerald-400">
                <CheckCircle className="w-3 h-3" />
                Completed
              </div>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-auto px-6 py-4">
          <div className="max-w-3xl mx-auto space-y-5">
            {(!turnsData?.turns || turnsData.turns.length === 0) && !sendMessage.isPending && (
              <div className="flex flex-col items-center justify-center py-16 text-center animate-fade-up">
                <div className="w-14 h-14 rounded-xl bg-gold/10 border border-gold/20 flex items-center justify-center mb-5">
                  <Sparkles className="w-6 h-6 text-gold" />
                </div>
                <h3 className="font-display text-xl font-semibold text-foreground mb-2">
                  Ready to learn
                </h3>
                <p className="text-sm text-muted-foreground max-w-sm">
                  Say hello or ask a question to begin your tutoring session. Your AI tutor will guide you through the material.
                </p>
              </div>
            )}

            {turnsData?.turns.map((turn, i) => (
              <div key={turn.turn_id} className="space-y-4 animate-fade-up" style={{ animationDelay: `${i * 0.02}s` }}>
                {/* Student message */}
                <div className="flex justify-end">
                  <div className="max-w-[75%]">
                    <div className="bg-gold/10 border border-gold/15 rounded-2xl rounded-tr-md px-4 py-3">
                      <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">{turn.student_message}</p>
                    </div>
                  </div>
                </div>

                {/* Tutor response */}
                <div className="flex justify-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-card border border-border flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Sparkles className="w-3.5 h-3.5 text-gold" />
                  </div>
                  <div className="max-w-[75%]">
                    <div className="bg-card border border-border rounded-2xl rounded-tl-md px-4 py-3">
                      <p className="text-sm text-card-foreground whitespace-pre-wrap leading-relaxed">{turn.tutor_response}</p>
                    </div>
                    {turn.pedagogical_action && (
                      <div className="mt-1.5 flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        <div className="w-1 h-1 rounded-full bg-gold/50" />
                        {turn.pedagogical_action}
                        {turn.current_step && (
                          <span className="ml-1 opacity-60">· {turn.current_step}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {sendMessage.isPending && (
              <div className="flex justify-start gap-3 animate-fade-in">
                <div className="w-8 h-8 rounded-lg bg-card border border-border flex items-center justify-center flex-shrink-0">
                  <Sparkles className="w-3.5 h-3.5 text-gold animate-pulse-gold" />
                </div>
                <div className="bg-card border border-border rounded-2xl rounded-tl-md px-4 py-3">
                  <div className="flex gap-1.5 items-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-gold/60 animate-bounce" />
                    <div className="w-1.5 h-1.5 rounded-full bg-gold/60 animate-bounce" style={{ animationDelay: '0.15s' }} />
                    <div className="w-1.5 h-1.5 rounded-full bg-gold/60 animate-bounce" style={{ animationDelay: '0.3s' }} />
                  </div>
                </div>
              </div>
            )}

            {sendMessage.isError && (
              <div className="flex justify-center animate-fade-in">
                <div className="px-4 py-2 rounded-lg border border-destructive/30 bg-destructive/10 text-xs text-destructive">
                  Failed to send message. Please try again.
                </div>
              </div>
            )}

            {/* Session Report Card — shown inline at the bottom of chat when completed */}
            {isCompleted && effectiveSummary && (
              <div className="pt-4 pb-2 animate-fade-up">
                <SessionReportCard
                  summary={effectiveSummary}
                  onStartQuiz={() => navigate(`/sessions/${sessionId}/quiz`)}
                  onBackToSessions={() => navigate('/sessions')}
                  onContinueLearning={() => navigate('/sessions/new')}
                />
              </div>
            )}

            {/* Fallback if completed but no summary yet */}
            {isCompleted && !effectiveSummary && (
              <div className="pt-4 pb-2 animate-fade-up">
                <div className="rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-5 text-center">
                  <CheckCircle className="w-8 h-8 text-emerald-400 mx-auto mb-3" />
                  <h3 className="font-display text-base font-semibold text-foreground mb-2">
                    Session Complete
                  </h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    You've worked through all the learning objectives. Great effort!
                  </p>
                  <button
                    onClick={() => navigate('/sessions')}
                    className="px-4 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-colors"
                  >
                    Back to Sessions
                  </button>
                </div>
              </div>
            )}

            <div ref={scrollRef} />
          </div>
        </div>

        {/* Input */}
        {session.status === 'active' && !lastTurnComplete && (
          <div className="border-t border-border bg-card/50 backdrop-blur-sm px-6 py-4">
            <div className="max-w-3xl mx-auto flex gap-3">
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type your message..."
                  rows={1}
                  disabled={sendMessage.isPending}
                  className="w-full resize-none rounded-xl border border-border bg-background px-4 py-3 pr-12 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-gold/30 focus:ring-1 focus:ring-gold/20 disabled:opacity-50 transition-colors"
                  style={{ minHeight: '44px', maxHeight: '120px' }}
                  onInput={(e) => {
                    const target = e.target as HTMLTextAreaElement;
                    target.style.height = 'auto';
                    target.style.height = Math.min(target.scrollHeight, 120) + 'px';
                  }}
                />
                <button
                  onClick={handleSend}
                  disabled={sendMessage.isPending || !input.trim()}
                  className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-lg bg-gold flex items-center justify-center text-primary-foreground hover:bg-gold/90 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-sm shadow-gold/20"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            <p className="max-w-3xl mx-auto text-[10px] text-muted-foreground/60 mt-2 text-center">
              Press Enter to send, Shift+Enter for new line
            </p>
          </div>
        )}
      </div>

      {/* Right sidebar */}
      <div className="w-72 border-l border-border bg-card/30 overflow-auto flex flex-col">
        <div className="p-5 space-y-5 flex-1">
          {/* Current Objective */}
          {currentObjective && !isCompleted && (
            <div className="animate-fade-up">
              <div className="flex items-center gap-2 mb-3">
                <Target className="w-3.5 h-3.5 text-gold" />
                <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
                  Current Objective
                </span>
              </div>
              <div className="rounded-xl border border-border bg-card p-4">
                <h3 className="font-display text-sm font-semibold text-card-foreground mb-1.5">
                  {(currentObjective.title as string) || 'Learning Objective'}
                </h3>
                {(currentObjective.description as string) && (
                  <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                    {(currentObjective.description as string)}
                  </p>
                )}
                {stepRoadmap.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex justify-between text-[11px] text-muted-foreground">
                      <span>Step {stepIndex + 1} of {stepRoadmap.length}</span>
                      <span className="text-gold font-medium">{Math.round(stepProgress)}%</span>
                    </div>
                    <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gold rounded-full transition-all duration-500"
                        style={{ width: `${stepProgress}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Completed Sidebar Summary */}
          {isCompleted && (
            <div className="animate-fade-up">
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
                  Session Complete
                </span>
              </div>
              <div className="rounded-xl border border-emerald-400/15 bg-emerald-400/5 p-4">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  All {objectiveQueue.length} objective{objectiveQueue.length !== 1 ? 's' : ''} covered.
                  Scroll down for your full session report.
                </p>
              </div>
            </div>
          )}

          {/* Mastery Progress — with labels */}
          {masteryEntries.length > 0 && (
            <div className="animate-fade-up" style={{ animationDelay: '0.05s' }}>
              <div className="flex items-center gap-2 mb-3">
                <BarChart3 className="w-3.5 h-3.5 text-gold" />
                <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
                  {isCompleted ? 'Final Mastery' : 'Mastery'}
                </span>
              </div>
              <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                {masteryEntries.slice(0, 8).map(([concept, value]) => {
                  const { label, color } = getMasteryLabel(value);
                  return (
                    <div key={concept} className="space-y-1.5">
                      <div className="flex justify-between items-center">
                        <span className="text-xs text-card-foreground truncate capitalize max-w-[120px]">
                          {concept.replace(/_/g, ' ')}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <span className={`text-[9px] font-medium ${color}`}>{label}</span>
                          <span className="text-[11px] text-muted-foreground font-mono">
                            {Math.round(value * 100)}%
                          </span>
                        </div>
                      </div>
                      <div className="h-1 w-full bg-secondary rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${value * 100}%`,
                            backgroundColor: value >= 0.7 ? 'hsl(142 71% 45%)' : value >= 0.4 ? 'hsl(var(--gold))' : 'hsl(var(--muted-foreground))',
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Session Info */}
          <div className="animate-fade-up" style={{ animationDelay: '0.1s' }}>
            <div className="flex items-center gap-2 mb-3">
              <Info className="w-3.5 h-3.5 text-gold" />
              <span className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground font-medium">
                Session Info
              </span>
            </div>
            <div className="rounded-xl border border-border bg-card p-4 space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-xs text-muted-foreground">Status</span>
                <div className={`flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] font-medium ${
                  isCompleted
                    ? 'bg-emerald-400/10 border-emerald-400/20 text-emerald-400'
                    : session.status === 'active'
                      ? 'bg-gold/10 border-gold/20 text-gold'
                      : 'bg-secondary border-border text-muted-foreground'
                }`}>
                  {session.status === 'active' && !lastTurnComplete && <div className="w-1.5 h-1.5 rounded-full bg-gold" />}
                  {isCompleted ? 'completed' : session.status}
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-muted-foreground">Turns</span>
                <span className="text-xs text-card-foreground font-mono">{turnsData?.turns.length || 0}</span>
              </div>
              {objectiveQueue.length > 0 && (
                <div className="flex justify-between items-center">
                  <span className="text-xs text-muted-foreground">Objective</span>
                  <span className="text-xs text-card-foreground font-mono">
                    {isCompleted
                      ? `${objectiveQueue.length} / ${objectiveQueue.length}`
                      : `${currentObjIndex + 1} / ${objectiveQueue.length}`
                    }
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
