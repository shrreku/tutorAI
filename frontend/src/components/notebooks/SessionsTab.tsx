import { useNavigate } from 'react-router-dom';
import {
  Loader2, MessageSquare, BookOpen, Target, Sparkles,
  ArrowRight, Clock,
} from 'lucide-react';
import { useNotebookSessions } from '../../api/hooks';

const MODE_META: Record<string, { icon: typeof BookOpen; label: string; color: string; bg: string }> = {
  learn:    { icon: BookOpen,      label: 'Learn',    color: 'text-blue-400',    bg: 'bg-blue-400/10 border-blue-400/20' },
  doubt:    { icon: MessageSquare, label: 'Doubt',    color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20' },
  practice: { icon: Target,        label: 'Practice', color: 'text-orange-400',  bg: 'bg-orange-400/10 border-orange-400/20' },
  revision: { icon: Sparkles,      label: 'Revision', color: 'text-purple-400',  bg: 'bg-purple-400/10 border-purple-400/20' },
};

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

  return (
    <div className="px-6 lg:px-8 py-6 animate-tab-enter">
      <div className="max-w-3xl">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading sessions…
          </div>
        ) : sessions.length === 0 ? (
          <div className="rounded-xl border border-border bg-card p-10 text-center animate-fade-up">
            <MessageSquare className="w-10 h-10 text-muted-foreground/20 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground mb-3">No sessions yet.</p>
            <button onClick={() => navigate(`/notebooks/${notebookId}/study`)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors">
              <Sparkles className="w-4 h-4" /> Start a session
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            {dateKeys.map((dateKey) => (
              <div key={dateKey} className="animate-fade-up">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2 px-1">{dateKey}</p>
                <div className="space-y-2">
                  {grouped[dateKey].map((session) => {
                    const meta = MODE_META[session.mode] ?? MODE_META.learn;
                    const Icon = meta.icon;
                    const startTime = new Date(session.started_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
                    const endTime = session.ended_at ? new Date(session.ended_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : null;

                    return (
                      <button key={session.id}
                        onClick={() => navigate(`/notebooks/${notebookId}/study?sessionId=${session.session_id}`)}
                        className="w-full group rounded-xl border border-border bg-card p-4 text-left hover:border-gold/20 transition-all flex items-center gap-4">
                        <div className={`w-10 h-10 rounded-xl border ${meta.bg} flex items-center justify-center shrink-0`}>
                          <Icon className={`w-5 h-5 ${meta.color}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground capitalize">{meta.label} session</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <Clock className="w-3 h-3 text-muted-foreground" />
                            <span className="text-[11px] text-muted-foreground">{startTime}{endTime ? ` – ${endTime}` : ' · in progress'}</span>
                          </div>
                        </div>
                        <ArrowRight className="w-4 h-4 text-muted-foreground/30 group-hover:text-gold transition-colors" />
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
