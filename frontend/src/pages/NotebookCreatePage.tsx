import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Sparkles, ChevronDown } from 'lucide-react';
import { useCreateNotebook } from '../api/hooks';
import type { NotebookPersonalization } from '../types/api';
import { cn } from '../lib/utils';

const PURPOSE_OPTIONS = [
  { value: 'exam_prep', label: 'Exam prep' },
  { value: 'assignment', label: 'Assignment' },
  { value: 'concept_mastery', label: 'Concept mastery' },
  { value: 'doubt_clearing', label: 'Doubt clearing' },
  { value: 'general', label: 'General learning' },
] as const;

const PACE_OPTIONS = [
  { value: 'relaxed', label: 'Relaxed' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'intensive', label: 'Intensive' },
] as const;

const DEPTH_OPTIONS = [
  { value: 'surface', label: 'Surface' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'deep', label: 'Deep' },
] as const;

export default function NotebookCreatePage() {
  const navigate = useNavigate();
  const createNotebook = useCreateNotebook();

  const [title, setTitle] = useState('');
  const [goal, setGoal] = useState('');
  const [targetDate, setTargetDate] = useState('');

  // Personalization state
  const [showPrefs, setShowPrefs] = useState(false);
  const [purpose, setPurpose] = useState<string | null>(null);
  const [pace, setPace] = useState<string | null>(null);
  const [depth, setDepth] = useState<string | null>(null);
  const [urgency, setUrgency] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    // Build personalization if any fields were set
    const personalization: NotebookPersonalization = {};
    if (purpose) personalization.purpose = purpose as NotebookPersonalization['purpose'];
    if (pace) personalization.study_pace = pace as NotebookPersonalization['study_pace'];
    if (depth) personalization.study_depth = depth as NotebookPersonalization['study_depth'];
    if (urgency) personalization.urgency = true;
    const hasPersonalization = Object.keys(personalization).length > 0;

    const notebook = await createNotebook.mutateAsync({
      title: title.trim(),
      goal: goal.trim() || undefined,
      target_date: targetDate || undefined,
      settings_json: { default_mode: 'learn' },
      ...(hasPersonalization ? { personalization } : {}),
    });

    navigate(`/notebooks/${notebook.id}`);
  };

  const hasAnyPref = purpose || pace || depth || urgency;

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
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium font-ui">Notebook Setup</span>
        </div>
        <h1 className="editorial-title text-3xl text-foreground mb-2">Create Notebook</h1>
        <p className="text-muted-foreground text-sm mb-8 reading-copy">
          Define your learning goal and start attaching resources and sessions.
        </p>

        <form onSubmit={handleSubmit} className="space-y-5 rounded-xl border border-border bg-card p-6">
          <div>
            <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Physics Midterm Prep"
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-gold/30 focus:ring-1 focus:ring-gold/20"
              required
            />
          </div>

          <div>
            <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Goal</label>
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={4}
              placeholder="What do you want to achieve with this notebook?"
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-gold/30 focus:ring-1 focus:ring-gold/20"
            />
          </div>

          <div>
            <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Target date <span className="normal-case tracking-normal text-muted-foreground/60">(optional)</span></label>
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:border-gold/30 focus:ring-1 focus:ring-gold/20"
            />
          </div>

          {/* Study Preferences — collapsible */}
          <div className="rounded-lg border border-border/60 overflow-hidden">
            <button
              type="button"
              onClick={() => setShowPrefs(!showPrefs)}
              className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-foreground hover:bg-muted/30 transition-colors"
            >
              <span className="flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5 text-gold" />
                Study preferences
                {hasAnyPref && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gold/15 text-gold font-medium">
                    {[purpose, pace, depth, urgency && 'deadline'].filter(Boolean).length} set
                  </span>
                )}
              </span>
              <ChevronDown className={cn('w-4 h-4 text-muted-foreground transition-transform', showPrefs && 'rotate-180')} />
            </button>

            {showPrefs && (
              <div className="px-4 pb-4 pt-1 space-y-4 border-t border-border/40">
                <p className="text-xs text-muted-foreground reading-copy">
                  These shape how your tutor approaches this notebook. All optional.
                </p>

                {/* Purpose */}
                <div>
                  <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Purpose</label>
                  <div className="flex flex-wrap gap-1.5">
                    {PURPOSE_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setPurpose(purpose === opt.value ? null : opt.value)}
                        className={cn(
                          'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                          purpose === opt.value
                            ? 'border-gold/40 bg-gold/10 text-gold'
                            : 'border-border/60 text-muted-foreground hover:border-gold/20 hover:text-foreground'
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Pace */}
                <div>
                  <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Pace</label>
                  <div className="flex gap-1.5">
                    {PACE_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setPace(pace === opt.value ? null : opt.value)}
                        className={cn(
                          'flex-1 py-1.5 rounded-lg text-xs font-medium border transition-colors text-center',
                          pace === opt.value
                            ? 'border-gold/40 bg-gold/10 text-gold'
                            : 'border-border/60 text-muted-foreground hover:border-gold/20 hover:text-foreground'
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Depth */}
                <div>
                  <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Depth</label>
                  <div className="flex gap-1.5">
                    {DEPTH_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setDepth(depth === opt.value ? null : opt.value)}
                        className={cn(
                          'flex-1 py-1.5 rounded-lg text-xs font-medium border transition-colors text-center',
                          depth === opt.value
                            ? 'border-gold/40 bg-gold/10 text-gold'
                            : 'border-border/60 text-muted-foreground hover:border-gold/20 hover:text-foreground'
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Urgency */}
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={urgency}
                    onChange={(e) => setUrgency(e.target.checked)}
                    className="h-4 w-4 rounded border-border accent-[hsl(var(--gold))]"
                  />
                  <span className="text-sm text-foreground">I'm preparing for a deadline</span>
                </label>
              </div>
            )}
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
