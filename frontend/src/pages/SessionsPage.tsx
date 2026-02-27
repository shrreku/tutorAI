import { useNavigate } from 'react-router-dom';
import { MessageSquare, Clock, CheckCircle, XCircle, Loader2, Plus, ArrowRight, Sparkles } from 'lucide-react';
import { useSessions } from '../api/hooks';

export default function SessionsPage() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useSessions();

  const statusConfig: Record<string, { icon: typeof CheckCircle; color: string; bg: string; label: string }> = {
    active: { icon: Sparkles, color: 'text-gold', bg: 'bg-gold/10 border-gold/20', label: 'Active' },
    completed: { icon: CheckCircle, color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20', label: 'Completed' },
    abandoned: { icon: XCircle, color: 'text-muted-foreground', bg: 'bg-secondary border-border', label: 'Abandoned' },
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 text-gold animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="p-4 rounded-xl border border-destructive/30 bg-destructive/10 text-sm text-destructive">
          Error loading sessions: {(error as Error).message}
        </div>
      </div>
    );
  }

  const activeSessions = data?.items?.filter(s => s.status === 'active') ?? [];
  const pastSessions = data?.items?.filter(s => s.status !== 'active') ?? [];

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      {/* Header */}
      <div className="flex justify-between items-start mb-8 animate-fade-up">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
            <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">
              Learning
            </span>
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground mb-1">
            Sessions
          </h1>
          <p className="text-muted-foreground text-sm">
            Your tutoring sessions
          </p>
        </div>
        <button
          onClick={() => navigate('/sessions/new')}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 hover:border-gold/30 transition-all"
        >
          <Plus className="w-4 h-4" />
          New Session
        </button>
      </div>

      {data?.items.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center animate-fade-up">
          <div className="w-16 h-16 rounded-xl bg-card border border-border flex items-center justify-center mb-5">
            <MessageSquare className="w-7 h-7 text-muted-foreground" />
          </div>
          <h3 className="font-display text-xl font-semibold text-foreground mb-2">No sessions yet</h3>
          <p className="text-sm text-muted-foreground mb-6 max-w-sm">
            Start a tutoring session to begin learning with your AI tutor
          </p>
          <button
            onClick={() => navigate('/sessions/new')}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors shadow-lg shadow-gold/20"
          >
            <Sparkles className="w-4 h-4" />
            Start your first session
          </button>
        </div>
      ) : (
        <div className="space-y-8">
          {/* Active Sessions */}
          {activeSessions.length > 0 && (
            <div className="animate-fade-up">
              <h2 className="font-display text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-gold animate-pulse-gold" />
                Active
              </h2>
              <div className="grid gap-3 md:grid-cols-2">
                {activeSessions.map((session, i) => {
                  const config = statusConfig[session.status] || statusConfig.abandoned;
                  const StatusIcon = config.icon;

                  return (
                    <button
                      key={session.id}
                      onClick={() => navigate(`/sessions/${session.id}`)}
                      className="group relative rounded-xl border border-gold/20 bg-gradient-to-br from-gold/[0.04] to-card p-5 text-left transition-all duration-200 hover:border-gold/35 hover:shadow-lg hover:shadow-gold/5 animate-fade-up"
                      style={{ animationDelay: `${0.05 + i * 0.03}s` }}
                    >
                      <div className="flex items-start gap-3 mb-3">
                        <div className="w-10 h-10 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center flex-shrink-0">
                          <MessageSquare className="w-5 h-5 text-gold" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-card-foreground truncate">
                            Session
                          </p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            Started {new Date(session.created_at).toLocaleDateString()}
                          </p>
                        </div>
                        <ArrowRight className="w-4 h-4 text-gold opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all flex-shrink-0" />
                      </div>

                      <div className="flex items-center gap-2">
                        <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs font-medium ${config.bg}`}>
                          <StatusIcon className={`w-3 h-3 ${config.color}`} />
                          <span className={config.color}>{config.label}</span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Past Sessions */}
          {pastSessions.length > 0 && (
            <div className="animate-fade-up" style={{ animationDelay: '0.1s' }}>
              <h2 className="font-display text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
                <Clock className="w-4 h-4 text-muted-foreground" />
                Past Sessions
              </h2>
              <div className="space-y-2">
                {pastSessions.map((session, i) => {
                  const config = statusConfig[session.status] || statusConfig.abandoned;
                  const StatusIcon = config.icon;

                  return (
                    <button
                      key={session.id}
                      onClick={() => navigate(`/sessions/${session.id}`)}
                      className="group w-full flex items-center gap-4 p-4 rounded-xl border border-border bg-card text-left transition-all duration-200 hover:border-gold/15 hover:shadow-md hover:shadow-gold/5 animate-fade-up"
                      style={{ animationDelay: `${0.12 + i * 0.03}s` }}
                    >
                      <div className="w-9 h-9 rounded-lg bg-secondary border border-border flex items-center justify-center flex-shrink-0">
                        <MessageSquare className="w-4 h-4 text-muted-foreground" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-card-foreground truncate">
                          Session
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(session.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs font-medium ${config.bg}`}>
                        <StatusIcon className={`w-3 h-3 ${config.color}`} />
                        <span className={config.color}>{config.label}</span>
                      </div>
                      <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
