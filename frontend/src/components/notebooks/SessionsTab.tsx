import { useNavigate } from 'react-router-dom';
import {
  Loader2, MessageSquare, BookOpen, Target, Sparkles,
  ArrowRight, Clock, Calendar, Brain,
} from 'lucide-react';
import { useNotebookSessions } from '../../api/hooks';
import { cn } from '../../lib/utils';

const MODE_META: Record<string, { icon: typeof BookOpen; label: string; color: string; bg: string; accent: string }> = {
  learn:    { icon: BookOpen,      label: 'Learn',    color: 'text-blue-400',    bg: 'bg-blue-400/10 border-blue-400/20',    accent: 'bg-blue-400' },
  doubt:    { icon: MessageSquare, label: 'Doubt',    color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20', accent: 'bg-emerald-400' },
  practice: { icon: Target,        label: 'Practice', color: 'text-orange-400',  bg: 'bg-orange-400/10 border-orange-400/20',  accent: 'bg-orange-400' },
  revision: { icon: Sparkles,      label: 'Revision', color: 'text-purple-400',  bg: 'bg-purple-400/10 border-purple-400/20',  accent: 'bg-purple-400' },
};

function formatRelativeDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export default function SessionsTab({ notebookId }: { notebookId: string }) {
  const navigate = useNavigate();
  const { data: notebookSessions, isLoading } = useNotebookSessions(notebookId);
  const sessions = notebookSessions?.items ?? [];

  const grouped = sessions.reduce<Record<string, typeof sessions>>((acc, s) => {
    const dateKey = new Date(s.started_at).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
    (acc[dateKey] ??= []).push(s);
    return acc;
  }, {});
  const dateKeys = Object.keys(grouped);

  const totalSessions = sessions.length;
  const activeSessions = sessions.filter((s) => !s.ended_at).length;
  const completedSessions = totalSessions - activeSessions;

  return (
    <div className="px-6 lg:px-8 py-6 animate-tab-enter">
      <div className="max-w-3xl">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading sessions…
          </div>
        ) : sessions.length === 0 ? (
          <div className="rounded-[24px] border border-dashed border-border bg-card/60 p-10 text-center animate-fade-up">
            <MessageSquare className="w-10 h-10 text-muted-foreground/20 mx-auto mb-3" />
            <p className="text-base font-medium text-foreground mb-1">No sessions yet</p>
            <p className="text-sm text-muted-foreground mb-4 reading-copy">Start a study session to begin learning from your resources.</p>
            <button onClick={() => navigate(`/notebooks/${notebookId}/study`)}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-gold text-primary-foreground text-sm font-semibold hover:bg-gold/90 transition-colors">
              <Sparkles className="w-4 h-4" /> Start a session
            </button>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Summary bar */}
            <div className="flex items-center gap-4 rounded-[20px] border border-border/60 bg-card/60 px-4 py-3">
              <div className="flex items-center gap-2">
                <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-sm text-foreground font-medium">{totalSessions} session{totalSessions !== 1 ? 's' : ''}</span>
              </div>
              <div className="h-4 w-px bg-border/60" />
              <span className="text-xs text-muted-foreground">{completedSessions} completed</span>
              {activeSessions > 0 && (
                <>
                  <div className="h-4 w-px bg-border/60" />
                  <span className="text-xs text-emerald-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    {activeSessions} in progress
                  </span>
                </>
              )}
            </div>

            {dateKeys.map((dateKey) => (
              <div key={dateKey} className="animate-fade-up">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground mb-2.5 px-1 font-ui">{dateKey}</p>
                <div className="space-y-2">
                  {grouped[dateKey].map((session) => {
                    const meta = MODE_META[session.mode] ?? MODE_META.learn;
                    const Icon = meta.icon;
                    const startTime = new Date(session.started_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
                    const endTime = session.ended_at ? new Date(session.ended_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : null;
                    const isActive = !session.ended_at;
                    const lastActivity = formatRelativeDate(session.updated_at || session.started_at);
                    const masteryPct = session.mastery_avg != null ? Math.round(session.mastery_avg * 100) : null;

                    return (
                      <button key={session.id}
                        onClick={() => navigate(`/notebooks/${notebookId}/study?sessionId=${session.session_id}`)}
                        className={cn(
                          'w-full group rounded-[18px] border bg-card p-3.5 text-left transition-all hover:shadow-sm',
                          isActive
                            ? 'border-gold/25 hover:border-gold/40'
                            : 'border-border hover:border-gold/20',
                        )}
                      >
                        <div className="flex items-center gap-3">
                          {/* Mode icon */}
                          <div className={`w-9 h-9 rounded-lg border ${meta.bg} flex items-center justify-center shrink-0`}>
                            <Icon className={`w-4 h-4 ${meta.color}`} />
                          </div>

                          {/* Main content */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-semibold text-foreground capitalize">{meta.label} session</p>
                              {isActive && (
                                <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-emerald-400">
                                  <span className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" />
                                  Active
                                </span>
                              )}
                            </div>

                            {/* Topic + detail row */}
                            {session.topic && (
                              <p className="text-xs text-foreground/70 truncate mt-0.5">{session.topic}</p>
                            )}
                            <div className="flex items-center gap-2 mt-0.5">
                              <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                                <Clock className="w-3 h-3" />
                                <span>{startTime}{endTime ? ` – ${endTime}` : ''}</span>
                              </div>
                              {masteryPct != null && (
                                <>
                                  <span className="text-[10px] text-muted-foreground/50">·</span>
                                  <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                                    <Brain className="w-3 h-3 text-gold" />
                                    <span>{masteryPct}%</span>
                                  </div>
                                </>
                              )}
                              {session.concepts_count > 0 && (
                                <>
                                  <span className="text-[10px] text-muted-foreground/50">·</span>
                                  <span className="text-[11px] text-muted-foreground">{session.concepts_count} concepts</span>
                                </>
                              )}
                              <span className="text-[10px] text-muted-foreground/50">·</span>
                              <span className="text-[10px] text-muted-foreground/60">
                                {lastActivity.toLowerCase()}
                              </span>
                            </div>
                          </div>

                          {/* Arrow */}
                          <ArrowRight className="w-4 h-4 text-muted-foreground/20 group-hover:text-gold transition-colors shrink-0" />
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
