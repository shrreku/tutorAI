import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, MessageSquare, Loader2 } from 'lucide-react';
import { useNotebook, useNotebookSessions } from '../api/hooks';

export default function NotebookSessionsPage() {
  const navigate = useNavigate();
  const { notebookId = '' } = useParams<{ notebookId: string }>();

  const { data: notebook } = useNotebook(notebookId);
  const { data: notebookSessions, isLoading } = useNotebookSessions(notebookId);

  const sessions = notebookSessions?.items ?? [];

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <button
        onClick={() => navigate(`/notebooks/${notebookId}`)}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to notebook
      </button>

      <div className="mb-6">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground mb-1">
          {notebook?.title || 'Notebook'} · Sessions
        </h1>
        <p className="text-sm text-muted-foreground">Notebook-linked tutoring history.</p>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading sessions...
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {sessions.map((session) => (
            <button
              key={session.id}
              onClick={() => navigate(`/notebooks/${notebookId}/study?sessionId=${session.session_id}`)}
              className="group rounded-xl border border-border bg-card p-4 text-left hover:border-gold/20"
            >
              <div className="flex items-center gap-2 mb-2">
                <MessageSquare className="w-4 h-4 text-gold" />
                <span className="text-sm font-medium text-card-foreground">{session.mode}</span>
              </div>
              <p className="text-xs text-muted-foreground font-mono truncate">{session.session_id}</p>
              <p className="text-[11px] text-muted-foreground mt-1">
                {new Date(session.started_at).toLocaleString()}
              </p>
            </button>
          ))}
          {sessions.length === 0 && (
            <div className="text-sm text-muted-foreground">No sessions yet.</div>
          )}
        </div>
      )}
    </div>
  );
}
