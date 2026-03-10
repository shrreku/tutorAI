import { useEffect, useMemo, useState } from 'react';
import {
  BookOpen,
  CheckCircle2,
  Layers3,
  Loader2,
  MessageSquare,
  Sparkles,
  Target,
} from 'lucide-react';
import type { NotebookSessionCreateRequest } from '../../types/api';

const MODES = ['learn', 'doubt', 'practice', 'revision'] as const;

const MODE_META: Record<(typeof MODES)[number], { icon: typeof BookOpen; label: string; description: string; accent: string }> = {
  learn: {
    icon: BookOpen,
    label: 'Learn',
    description: 'Structured teaching through objectives and examples.',
    accent: 'text-blue-500',
  },
  doubt: {
    icon: MessageSquare,
    label: 'Doubt',
    description: 'Fast clarification for a confusing point or citation check.',
    accent: 'text-emerald-500',
  },
  practice: {
    icon: Target,
    label: 'Practice',
    description: 'Work through recall, questions, and challenge prompts.',
    accent: 'text-orange-500',
  },
  revision: {
    icon: Sparkles,
    label: 'Revision',
    description: 'Target weak areas and lock in what still feels shaky.',
    accent: 'text-fuchsia-500',
  },
};

type ScopeType = 'focused' | 'selected' | 'notebook';

type LaunchResource = {
  id: string;
  label: string;
  subtitle?: string | null;
  status?: string;
};

type SessionLaunchPanelProps = {
  resources: LaunchResource[];
  recommendedMode?: (typeof MODES)[number];
  recommendedReason?: string;
  pending?: boolean;
  title?: string;
  subtitle?: string;
  ctaLabel?: string;
  compact?: boolean;
  onLaunch: (request: NotebookSessionCreateRequest) => Promise<void> | void;
};

function parseTopicInput(value: string) {
  const topics = value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

  return {
    topic: topics[0] || undefined,
    selected_topics: topics.length > 1 ? topics : undefined,
  };
}

export default function SessionLaunchPanel({
  resources,
  recommendedMode = 'learn',
  recommendedReason,
  pending = false,
  title = 'Start a study session',
  subtitle = 'Pick the learning mode, choose how wide the context should be, and optionally focus the tutor on a topic.',
  ctaLabel,
  compact = false,
  onLaunch,
}: SessionLaunchPanelProps) {
  const [mode, setMode] = useState<(typeof MODES)[number]>(recommendedMode);
  const [scope, setScope] = useState<ScopeType>('focused');
  const [anchorResourceId, setAnchorResourceId] = useState(resources[0]?.id || '');
  const [selectedResourceIds, setSelectedResourceIds] = useState<string[]>(resources[0] ? [resources[0].id] : []);
  const [topicInput, setTopicInput] = useState('');
  const [resumeExisting, setResumeExisting] = useState(true);

  useEffect(() => {
    if (!resources.length) {
      setAnchorResourceId('');
      setSelectedResourceIds([]);
      return;
    }

    setAnchorResourceId((current) => {
      if (current && resources.some((resource) => resource.id === current)) {
        return current;
      }
      return resources[0].id;
    });

    setSelectedResourceIds((current) => {
      const valid = current.filter((resourceId) => resources.some((resource) => resource.id === resourceId));
      return valid.length > 0 ? valid : [resources[0].id];
    });
  }, [resources]);

  useEffect(() => {
    setMode(recommendedMode);
  }, [recommendedMode]);

  const includedResourceIds = useMemo(() => {
    if (scope === 'notebook') {
      return resources.map((resource) => resource.id);
    }
    if (scope === 'selected') {
      const merged = new Set(selectedResourceIds);
      if (anchorResourceId) merged.add(anchorResourceId);
      return Array.from(merged);
    }
    return anchorResourceId ? [anchorResourceId] : [];
  }, [anchorResourceId, resources, scope, selectedResourceIds]);

  const includedResources = resources.filter((resource) => includedResourceIds.includes(resource.id));

  const handleToggleResource = (resourceId: string) => {
    setSelectedResourceIds((current) => {
      if (current.includes(resourceId)) {
        if (resourceId === anchorResourceId && current.length === 1) {
          return current;
        }
        return current.filter((id) => id !== resourceId);
      }
      return [...current, resourceId];
    });
  };

  const handleLaunch = async () => {
    if (!anchorResourceId) return;

    const parsedTopics = parseTopicInput(topicInput);
    await onLaunch({
      resource_id: anchorResourceId,
      selected_resource_ids: scope === 'selected' ? includedResourceIds : [],
      notebook_wide: scope === 'notebook',
      mode,
      topic: parsedTopics.topic,
      selected_topics: parsedTopics.selected_topics,
      resume_existing: resumeExisting,
    });
  };

  const layoutClass = compact ? 'space-y-4' : 'space-y-5';

  return (
    <div className={`rounded-[1.5rem] border border-border bg-card/90 shadow-[0_20px_80px_-40px_rgba(15,23,42,0.35)] ${compact ? 'p-4' : 'p-5 md:p-6'} ${layoutClass}`}>
      <div className="space-y-1">
        <div className="inline-flex items-center gap-2 rounded-full border border-gold/20 bg-gold/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.24em] text-gold">
          Session Builder
        </div>
        <h3 className="font-display text-2xl text-foreground">{title}</h3>
        <p className="max-w-2xl text-sm text-muted-foreground">{subtitle}</p>
      </div>

      {recommendedReason && (
        <div className="rounded-2xl border border-gold/20 bg-[linear-gradient(135deg,rgba(245,158,11,0.14),rgba(255,255,255,0.7))] px-4 py-3 text-sm text-foreground">
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-gold">
            <Sparkles className="h-3.5 w-3.5" />
            Recommended next move
          </div>
          <p>
            <span className="font-medium capitalize">{MODE_META[recommendedMode].label}</span>
            {' '}
            session. {recommendedReason}
          </p>
        </div>
      )}

      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {MODES.map((item) => {
          const meta = MODE_META[item];
          const Icon = meta.icon;
          const active = item === mode;
          return (
            <button
              key={item}
              type="button"
              onClick={() => setMode(item)}
              className={`rounded-2xl border p-4 text-left transition-all ${active ? 'border-gold/30 bg-gold/10 shadow-[0_16px_36px_-24px_rgba(245,158,11,0.65)]' : 'border-border hover:border-gold/20 hover:bg-muted/60'}`}
            >
              <div className="mb-3 flex items-center justify-between">
                <Icon className={`h-5 w-5 ${active ? 'text-gold' : meta.accent}`} />
                {active && <CheckCircle2 className="h-4 w-4 text-gold" />}
              </div>
              <div className="text-sm font-semibold text-foreground">{meta.label}</div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{meta.description}</p>
            </button>
          );
        })}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-4 rounded-2xl border border-border/70 bg-background/70 p-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">Scope</p>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              {[
                { value: 'focused', label: 'One resource', detail: 'Keep the session tightly anchored.' },
                { value: 'selected', label: 'Selected resources', detail: 'Blend a few files into one thread.' },
                { value: 'notebook', label: 'Whole notebook', detail: 'Use everything attached to this notebook.' },
              ].map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setScope(option.value as ScopeType)}
                  className={`rounded-2xl border px-4 py-3 text-left transition-all ${scope === option.value ? 'border-gold/30 bg-gold/10' : 'border-border hover:border-gold/20 hover:bg-muted/60'}`}
                >
                  <div className="text-sm font-medium text-foreground">{option.label}</div>
                  <p className="mt-1 text-xs text-muted-foreground">{option.detail}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">Anchor resource</span>
              <select
                value={anchorResourceId}
                onChange={(event) => setAnchorResourceId(event.target.value)}
                className="w-full rounded-2xl border border-border bg-card px-3 py-3 text-sm text-foreground outline-none transition-colors focus:border-gold/30"
              >
                {resources.map((resource) => (
                  <option key={resource.id} value={resource.id}>{resource.label}</option>
                ))}
              </select>
            </label>

            <label className="space-y-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">Topic focus</span>
              <input
                value={topicInput}
                onChange={(event) => setTopicInput(event.target.value)}
                placeholder="Optional: derivatives, Newton's laws, cardiac cycle"
                className="w-full rounded-2xl border border-border bg-card px-3 py-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-gold/30"
              />
            </label>
          </div>

          {scope === 'selected' && resources.length > 1 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                <Layers3 className="h-3.5 w-3.5" />
                Included resources
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {resources.map((resource) => {
                  const active = includedResourceIds.includes(resource.id);
                  return (
                    <button
                      key={resource.id}
                      type="button"
                      onClick={() => handleToggleResource(resource.id)}
                      className={`rounded-2xl border px-4 py-3 text-left transition-all ${active ? 'border-gold/30 bg-gold/10' : 'border-border hover:border-gold/20 hover:bg-muted/60'}`}
                    >
                      <div className="flex items-start gap-3">
                        <span className={`mt-0.5 flex h-4 w-4 items-center justify-center rounded-full border ${active ? 'border-gold bg-gold text-primary-foreground' : 'border-border bg-card'}`}>
                          {active && <CheckCircle2 className="h-3 w-3" />}
                        </span>
                        <div>
                          <div className="text-sm font-medium text-foreground">{resource.label}</div>
                          {resource.subtitle && <p className="mt-1 text-xs text-muted-foreground">{resource.subtitle}</p>}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col justify-between rounded-2xl border border-border/70 bg-[radial-gradient(circle_at_top,rgba(245,158,11,0.08),transparent_55%)] p-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">Session preview</p>
            <div className="mt-3 rounded-2xl border border-border/70 bg-card/80 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                {(() => {
                  const Icon = MODE_META[mode].icon;
                  return <Icon className={`h-4 w-4 ${MODE_META[mode].accent}`} />;
                })()}
                <span>{MODE_META[mode].label} session</span>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                {scope === 'focused' && 'Tight scope on one anchor resource.'}
                {scope === 'selected' && `Cross-resource context from ${includedResources.length} selected resources.`}
                {scope === 'notebook' && `Notebook-wide context across ${includedResources.length} active resources.`}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {includedResources.slice(0, 4).map((resource) => (
                  <span key={resource.id} className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] text-foreground">
                    {resource.label}
                  </span>
                ))}
                {includedResources.length > 4 && (
                  <span className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] text-muted-foreground">
                    +{includedResources.length - 4} more
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            <label className="flex items-start gap-3 rounded-2xl border border-border/70 bg-card/80 px-4 py-3 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={resumeExisting}
                onChange={(event) => setResumeExisting(event.target.checked)}
                className="mt-1 h-4 w-4 rounded border-border text-gold focus:ring-gold/30"
              />
              <span>
                Reuse an active matching session when available. Turn this off when you want a clean branch for a new study thread.
              </span>
            </label>

            <button
              type="button"
              disabled={pending || !anchorResourceId || includedResourceIds.length === 0}
              onClick={() => void handleLaunch()}
              className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-gold px-4 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-gold/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {ctaLabel || `Start ${MODE_META[mode].label} session`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}