import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpenText, Plus, ArrowRight, Loader2, FileText, BarChart3, Clock } from 'lucide-react';
import { useNotebooks, useNotebookProgressBatch, useNotebookResourceCountBatch } from '../api/hooks';

function formatRelativeTime(dateString: string): string {
  const diff = Date.now() - new Date(dateString).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(dateString).toLocaleDateString();
}

export default function NotebooksPage() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useNotebooks();

  const notebooks = data?.items ?? [];
  const notebookIds = useMemo(() => notebooks.map((n) => n.id), [notebooks]);
  const progressMap = useNotebookProgressBatch(notebookIds);
  const resourceCountMap = useNotebookResourceCountBatch(notebookIds);

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
          Error loading notebooks: {(error as Error).message}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <div className="flex justify-between items-start mb-8 animate-fade-up">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
            <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium font-ui">Notebook OS</span>
          </div>
          <h1 className="editorial-title text-3xl text-foreground mb-1">Notebooks</h1>
          <p className="text-muted-foreground text-sm reading-copy">Course-sized learning containers for resources, sessions, and progress.</p>
        </div>
        <button
          onClick={() => navigate('/notebooks/new')}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-all font-ui"
        >
          <Plus className="w-4 h-4" />
          New Notebook
        </button>
      </div>

      {notebooks.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center animate-fade-up">
          <div className="w-16 h-16 rounded-xl bg-card border border-border flex items-center justify-center mb-5">
            <BookOpenText className="w-7 h-7 text-muted-foreground" />
          </div>
          <h3 className="editorial-title text-xl text-foreground mb-2">No notebooks yet</h3>
          <p className="text-sm text-muted-foreground mb-6 max-w-sm reading-copy">
            Create your first notebook to organize resources and run notebook-scoped tutoring.
          </p>
          <button
            onClick={() => navigate('/notebooks/new')}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors font-ui"
          >
            <Plus className="w-4 h-4" />
            Create notebook
          </button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {notebooks.map((notebook, i) => {
            const progress = progressMap.get(notebook.id);
            const resourceCount = resourceCountMap.get(notebook.id) ?? 0;
            const masteryEntries = Object.values(progress?.mastery_snapshot ?? {});
            const avgMastery = masteryEntries.length > 0
              ? Math.round(masteryEntries.reduce((a, b) => a + b, 0) / masteryEntries.length)
              : null;
            const lastStudied = progress?.updated_at || notebook.updated_at;

            return (
              <button
                key={notebook.id}
                onClick={() => navigate(`/notebooks/${notebook.id}`)}
                className="group rounded-2xl border border-border bg-card p-5 text-left transition-all duration-200 hover:border-gold/25 hover:shadow-sm animate-fade-up"
                style={{ animationDelay: `${0.05 + i * 0.03}s` }}
              >
                <div className="flex items-start justify-between gap-3 mb-2">
                  <p className="text-sm font-semibold text-card-foreground leading-snug line-clamp-2">{notebook.title}</p>
                  <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all shrink-0 mt-0.5" />
                </div>

                <p className="text-xs text-muted-foreground line-clamp-2 mb-4 reading-copy">
                  {notebook.goal || 'No goal set yet.'}
                </p>

                {/* Stats row */}
                <div className="flex items-center gap-3 text-[11px] text-muted-foreground mb-3">
                  <span className="inline-flex items-center gap-1">
                    <FileText className="w-3 h-3" />
                    {resourceCount} {resourceCount === 1 ? 'resource' : 'resources'}
                  </span>
                  {avgMastery !== null && (
                    <span className="inline-flex items-center gap-1">
                      <BarChart3 className="w-3 h-3" />
                      {avgMastery}% mastery
                    </span>
                  )}
                  {progress?.sessions_count != null && progress.sessions_count > 0 && (
                    <span className="inline-flex items-center gap-1">
                      {progress.sessions_count} {progress.sessions_count === 1 ? 'session' : 'sessions'}
                    </span>
                  )}
                </div>

                <div className="pt-3 border-t border-border/50 flex items-center gap-1.5 text-[11px] text-muted-foreground/70">
                  <Clock className="w-3 h-3" />
                  {lastStudied ? formatRelativeTime(lastStudied) : `Created ${new Date(notebook.created_at).toLocaleDateString()}`}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
