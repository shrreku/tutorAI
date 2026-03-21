import { useNavigate } from 'react-router-dom';
import { BookOpenText, Plus, ArrowRight, Loader2 } from 'lucide-react';
import { useNotebooks } from '../api/hooks';

export default function NotebooksPage() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useNotebooks();

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

  const notebooks = data?.items ?? [];

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <div className="flex justify-between items-start mb-8 animate-fade-up">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
            <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">Notebook OS</span>
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground mb-1">Notebooks</h1>
          <p className="text-muted-foreground text-sm">Course-sized learning containers for resources, sessions, and progress.</p>
        </div>
        <button
          onClick={() => navigate('/notebooks/new')}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-all"
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
          <h3 className="font-display text-xl font-semibold text-foreground mb-2">No notebooks yet</h3>
          <p className="text-sm text-muted-foreground mb-6 max-w-sm">
            Create your first notebook to organize resources and run notebook-scoped tutoring.
          </p>
          <button
            onClick={() => navigate('/notebooks/new')}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Create notebook
          </button>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {notebooks.map((notebook, i) => (
            <button
              key={notebook.id}
              onClick={() => navigate(`/notebooks/${notebook.id}`)}
              className="group rounded-xl border border-border bg-card p-5 text-left transition-all duration-200 hover:border-gold/20 animate-fade-up"
              style={{ animationDelay: `${0.05 + i * 0.03}s` }}
            >
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <p className="text-sm font-semibold text-card-foreground">{notebook.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 capitalize">{notebook.status}</p>
                </div>
                <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
              </div>
              <p className="text-xs text-muted-foreground line-clamp-3 min-h-[48px]">
                {notebook.goal || 'No goal set yet. Add a goal to guide tutoring sessions.'}
              </p>
              <div className="mt-4 pt-3 border-t border-border/50 text-[11px] text-muted-foreground">
                Created {new Date(notebook.created_at).toLocaleDateString()}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
