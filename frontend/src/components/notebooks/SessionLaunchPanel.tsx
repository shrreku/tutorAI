import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
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
type SessionMode = (typeof MODES)[number];

const MODE_META: Record<SessionMode, { icon: typeof BookOpen; label: string; description: string; accent: string }> = {
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

const MODE_INPUT_META: Record<SessionMode, { label: string; helper: string; placeholder: string; preview: string; required: boolean }> = {
  learn: {
    label: 'Where should this session begin?',
    helper: 'Optional. Point the tutor toward the chapter, concept, or depth you want first.',
    placeholder: 'Optional: limits, Newton\'s laws, Mughal administration',
    preview: 'The curriculum will foreground this topic first.',
    required: false,
  },
  doubt: {
    label: 'What exactly is confusing you?',
    helper: 'Required in doubt mode. Describe the exact step, equation, citation, or concept that feels unclear.',
    placeholder: 'Required: why is the electric field zero inside the shell?',
    preview: 'The session will open by resolving this doubt directly.',
    required: true,
  },
  practice: {
    label: 'What do you want to practice?',
    helper: 'Optional. Narrow practice to a chapter, concept cluster, or difficulty preference.',
    placeholder: 'Optional: practice integration by parts, medium difficulty',
    preview: 'Practice prompts will bias toward this target.',
    required: false,
  },
  revision: {
    label: 'What should this revision focus on?',
    helper: 'Optional. Focus revision on an exam unit, chapter, or fast recap area.',
    placeholder: 'Optional: recap cell biology unit 3',
    preview: 'Revision will prioritize this review target.',
    required: false,
  },
};

type ScopeType = 'focused' | 'selected' | 'notebook';

type LaunchResource = {
  id: string;
  label: string;
  subtitle?: string | null;
  status?: string;
  studyReady?: boolean;
  doubtReady?: boolean;
};

function isResourceReadyForMode(resource: LaunchResource, mode: (typeof MODES)[number]) {
  if (mode === 'doubt') {
    return Boolean(resource.doubtReady || resource.studyReady);
  }
  return Boolean(resource.studyReady);
}

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

function parseTopicInput(value: string, mode: SessionMode) {
  const normalized = value.trim();
  if (!normalized) {
    return {
      topic: undefined,
      selected_topics: undefined,
    };
  }

  if (mode === 'doubt') {
    return {
      topic: normalized,
      selected_topics: undefined,
    };
  }

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
  const blockedResources = includedResources.filter((resource) => !isResourceReadyForMode(resource, mode));
  const hasBlockedResources = blockedResources.length > 0;
  const learnerInputMeta = MODE_INPUT_META[mode];
  const parsedTopics = useMemo(() => parseTopicInput(topicInput, mode), [mode, topicInput]);
  const hasLearnerInput = Boolean(parsedTopics.topic || (parsedTopics.selected_topics?.length ?? 0) > 0);
  const requiresLearnerInput = learnerInputMeta.required;
  const learnerInputSummary = parsedTopics.selected_topics?.length
    ? parsedTopics.selected_topics.join(', ')
    : parsedTopics.topic;
  const launchDisabled = pending
    || !anchorResourceId
    || includedResourceIds.length === 0
    || hasBlockedResources
    || (requiresLearnerInput && !hasLearnerInput);

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

    if (requiresLearnerInput && !hasLearnerInput) return;

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
    <div className={`surface-scholarly rounded-[28px] border border-border/70 ${compact ? 'p-4' : 'p-5 md:p-6'} ${layoutClass}`}>
      <div className="space-y-1">
        <div className="section-kicker inline-flex items-center gap-2 rounded-full border border-gold/20 bg-gold/10 px-3 py-1 text-[11px] font-medium text-gold">
          Session Builder
        </div>
        <h3 className="editorial-title text-3xl text-foreground">{title}</h3>
        <p className="max-w-2xl text-base text-muted-foreground reading-copy">{subtitle}</p>
      </div>

      {recommendedReason && (
        <div className="rounded-[24px] border border-gold/20 bg-gold/[0.04] px-4 py-3 text-sm text-foreground">
          <div className="section-kicker mb-1 flex items-center gap-2 text-xs font-semibold text-gold">
            <Sparkles className="h-3.5 w-3.5" />
            Recommended next move
          </div>
          <p className="reading-copy text-base text-foreground">
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
              className={`rounded-[22px] border p-4 text-left transition-all ${active ? 'border-gold/30 bg-gold/[0.08] shadow-[0_18px_30px_-24px_hsl(155_28%_38%_/_0.6)]' : 'border-border/80 bg-card/70 hover:border-gold/20 hover:bg-muted/50'}`}
            >
              <div className="mb-3 flex items-center justify-between">
                <Icon className={`h-5 w-5 ${active ? 'text-gold' : meta.accent}`} />
                {active && <CheckCircle2 className="h-4 w-4 text-gold" />}
              </div>
              <div className="font-ui text-sm font-semibold text-foreground">{meta.label}</div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{meta.description}</p>
            </button>
          );
        })}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-4 rounded-[24px] border border-border/70 bg-background/70 p-4">
          <div>
            <p className="section-kicker text-[11px] font-semibold text-muted-foreground">Scope</p>
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
                  className={`rounded-[20px] border px-4 py-3 text-left transition-all ${scope === option.value ? 'border-gold/30 bg-gold/10' : 'border-border hover:border-gold/20 hover:bg-muted/60'}`}
                >
                  <div className="font-ui text-sm font-medium text-foreground">{option.label}</div>
                  <p className="mt-1 text-xs text-muted-foreground">{option.detail}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-2">
              <span className="section-kicker text-[11px] font-semibold text-muted-foreground">Anchor resource</span>
              <select
                value={anchorResourceId}
                onChange={(event) => setAnchorResourceId(event.target.value)}
                className="w-full rounded-[20px] border border-border bg-card px-3 py-3 text-sm text-foreground outline-none transition-colors focus:border-gold/30"
              >
                {resources.map((resource) => (
                  <option key={resource.id} value={resource.id}>{resource.label}</option>
                ))}
              </select>
            </label>

            <label className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span className="section-kicker text-[11px] font-semibold text-muted-foreground">{learnerInputMeta.label}</span>
                {requiresLearnerInput && (
                  <span className="data-chip rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase text-amber-600 dark:text-amber-300">
                    Required
                  </span>
                )}
              </div>
              <input
                value={topicInput}
                onChange={(event) => setTopicInput(event.target.value)}
                placeholder={learnerInputMeta.placeholder}
                className={`w-full rounded-[20px] border bg-card px-3 py-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-gold/30 ${requiresLearnerInput && !hasLearnerInput ? 'border-amber-500/40 bg-amber-500/[0.04]' : 'border-border'}`}
              />
              <p className={`text-xs leading-relaxed ${requiresLearnerInput && !hasLearnerInput ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground'}`}>
                {learnerInputMeta.helper}
              </p>
            </label>
          </div>

          {scope === 'selected' && resources.length > 1 && (
            <div className="space-y-2">
              <div className="section-kicker flex items-center gap-2 text-[11px] font-semibold text-muted-foreground">
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
                      className={`rounded-[20px] border px-4 py-3 text-left transition-all ${active ? 'border-gold/30 bg-gold/10' : 'border-border hover:border-gold/20 hover:bg-muted/60'}`}
                    >
                      <div className="flex items-start gap-3">
                        <span className={`mt-0.5 flex h-4 w-4 items-center justify-center rounded-full border ${active ? 'border-gold bg-gold text-primary-foreground' : 'border-border bg-card'}`}>
                          {active && <CheckCircle2 className="h-3 w-3" />}
                        </span>
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="text-sm font-medium text-foreground">{resource.label}</div>
                            {resource.studyReady === true && (
                              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                                Study-ready
                              </span>
                            )}
                            {!resource.studyReady && resource.doubtReady && (
                              <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-0.5 text-[10px] font-medium text-sky-300">
                                Doubt-ready
                              </span>
                            )}
                            {!resource.studyReady && !resource.doubtReady && (
                              <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-300">
                                Not ready yet
                              </span>
                            )}
                          </div>
                          {resource.subtitle && <p className="mt-1 text-xs text-muted-foreground">{resource.subtitle}</p>}
                          {!resource.studyReady && !resource.doubtReady && (
                            <p className="mt-1 text-xs text-amber-300">
                              This resource is still being parsed and indexed, so even doubt mode is blocked for now.
                            </p>
                          )}
                          {!resource.studyReady && resource.doubtReady && mode !== 'doubt' && (
                            <p className="mt-1 text-xs text-sky-300">
                              Core indexing is ready, so doubt mode can start now. Learn, practice, and revision still wait for curriculum preparation.
                            </p>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col justify-between rounded-[24px] border border-border bg-card/90 p-4">
          <div>
            <p className="section-kicker text-[11px] font-semibold text-muted-foreground">Session preview</p>
            <div className="mt-3 rounded-[22px] border border-border/70 bg-card/80 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground font-ui">
                {(() => {
                  const Icon = MODE_META[mode].icon;
                  return <Icon className={`h-4 w-4 ${MODE_META[mode].accent}`} />;
                })()}
                <span>{MODE_META[mode].label} session</span>
              </div>
              <p className="mt-2 text-sm text-muted-foreground reading-copy">
                {scope === 'focused' && 'Tight scope on one anchor resource.'}
                {scope === 'selected' && `Cross-resource context from ${includedResources.length} selected resources.`}
                {scope === 'notebook' && `Notebook-wide context across ${includedResources.length} active resources.`}
              </p>
              <div className="mt-3 space-y-2 rounded-[18px] border border-border/60 bg-background/70 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="section-kicker text-[10px] font-semibold text-muted-foreground">Learner input</span>
                  <span className={`data-chip rounded-full px-2 py-1 text-[10px] font-semibold uppercase ${hasLearnerInput ? 'border border-gold/20 bg-gold/10 text-gold' : requiresLearnerInput ? 'border border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-300' : 'border border-border bg-card text-muted-foreground'}`}>
                    {hasLearnerInput ? 'Shaping session' : requiresLearnerInput ? 'Needed' : 'Optional'}
                  </span>
                </div>
                <p className="text-sm text-foreground reading-copy">
                  {learnerInputSummary || 'No learner input added yet.'}
                </p>
                <p className="text-xs text-muted-foreground">{learnerInputMeta.preview}</p>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {includedResources.slice(0, 4).map((resource) => (
                  <span
                    key={resource.id}
                    className={`data-chip rounded-full border px-2.5 py-1 text-[11px] ${!isResourceReadyForMode(resource, mode) ? 'border-amber-500/20 bg-amber-500/10 text-amber-300' : 'border-border bg-background text-foreground'}`}
                  >
                    {resource.label}
                  </span>
                ))}
                {includedResources.length > 4 && (
                  <span className="data-chip rounded-full border border-border bg-background px-2.5 py-1 text-[11px] text-muted-foreground">
                    +{includedResources.length - 4} more
                  </span>
                )}
              </div>
            </div>

            {hasBlockedResources && (
              <div className="mt-3 rounded-[22px] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                <div className="section-kicker flex items-center gap-2 text-[11px] font-semibold text-amber-300">
                  <AlertCircle className="h-3.5 w-3.5" />
                  {mode === 'doubt' ? 'Core indexing required' : 'Curriculum readiness required'}
                </div>
                <p className="mt-2 text-sm text-amber-100/90">
                  {mode === 'doubt'
                    ? 'Remove resources that are still parsing or chunking before starting this session. Doubt mode starts as soon as the searchable core index is ready.'
                    : 'Remove resources that are still preparing before starting this session. Learn, practice, and revision wait for curriculum preparation to finish.'}
                </p>
                <p className="mt-2 text-xs text-amber-200/90">
                  Blocked: {blockedResources.map((resource) => resource.label).join(', ')}
                </p>
              </div>
            )}
          </div>

          <div className="mt-4 space-y-3">
            <label className="flex items-start gap-3 rounded-[20px] border border-border/70 bg-card/80 px-4 py-3 text-sm text-muted-foreground">
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
              disabled={launchDisabled}
              onClick={() => void handleLaunch()}
              className="font-ui inline-flex w-full items-center justify-center gap-2 rounded-[20px] bg-gold px-4 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-gold/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {ctaLabel || `Start ${MODE_META[mode].label} session`}
            </button>
            {requiresLearnerInput && !hasLearnerInput && !hasBlockedResources && (
              <p className="text-xs text-amber-700 dark:text-amber-300">
                Add the learner's doubt first so the session can be scoped correctly.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}