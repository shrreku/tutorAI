import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Sparkles } from 'lucide-react';
import { useCreateNotebook } from '../api/hooks';

export default function NotebookCreatePage() {
  const navigate = useNavigate();
  const createNotebook = useCreateNotebook();

  const [title, setTitle] = useState('');
  const [goal, setGoal] = useState('');
  const [targetDate, setTargetDate] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    const notebook = await createNotebook.mutateAsync({
      title: title.trim(),
      goal: goal.trim() || undefined,
      target_date: targetDate || undefined,
      settings_json: { default_mode: 'learn' },
    });

    navigate(`/notebooks/${notebook.id}`);
  };

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <button
        onClick={() => navigate('/notebooks')}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to notebooks
      </button>

      <div className="max-w-2xl animate-fade-up">
        <div className="flex items-center gap-2 mb-3">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">Notebook Setup</span>
        </div>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground mb-2">Create Notebook</h1>
        <p className="text-muted-foreground text-sm mb-8">
          Define your learning goal and start attaching resources and sessions.
        </p>

        <form onSubmit={handleSubmit} className="space-y-5 rounded-xl border border-border bg-card p-6">
          <div>
            <label className="block text-xs uppercase tracking-wide text-muted-foreground mb-2">Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Physics Midterm Prep"
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-gold/30 focus:ring-1 focus:ring-gold/20"
              required
            />
          </div>

          <div>
            <label className="block text-xs uppercase tracking-wide text-muted-foreground mb-2">Goal</label>
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={4}
              placeholder="What do you want to achieve with this notebook?"
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-gold/30 focus:ring-1 focus:ring-gold/20"
            />
          </div>

          <div>
            <label className="block text-xs uppercase tracking-wide text-muted-foreground mb-2">Target Date (optional)</label>
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-gold/30 focus:ring-1 focus:ring-gold/20"
            />
          </div>

          <button
            type="submit"
            disabled={createNotebook.isPending || !title.trim()}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors disabled:opacity-50"
          >
            {createNotebook.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            Create notebook
          </button>

          {createNotebook.isError && (
            <div className="p-3 rounded-lg border border-destructive/30 bg-destructive/10 text-sm text-destructive">
              Failed to create notebook.
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
