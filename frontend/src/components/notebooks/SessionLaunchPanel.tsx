import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Loader2,
  MessageSquare,
  Sparkles,
  Target,
} from 'lucide-react';
import type { NotebookSessionCreateRequest, SessionPersonalization } from '../../types/api';
import { useTaskModels } from '../../api/hooks';
import { cn } from '../../lib/utils';

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
  pending?: boolean;
  title?: string;
  subtitle?: string;
  ctaLabel?: string;
  onManageResources?: () => void;
  manageResourcesLabel?: string;
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
  pending = false,
  title = '',
  subtitle = '',
  ctaLabel,
  onManageResources,
  manageResourcesLabel = 'Manage resources',
  onLaunch,
}: SessionLaunchPanelProps) {
  const [mode, setMode] = useState<(typeof MODES)[number]>(recommendedMode);
  const [selectedResourceIds, setSelectedResourceIds] = useState<string[]>(resources[0] ? [resources[0].id] : []);
  const [topicInput, setTopicInput] = useState('');
  const [resumeExisting, setResumeExisting] = useState(true);
  const [curriculumModelId, setCurriculumModelId] = useState('');

  // Session personalization state
  const [showSessionPrefs, setShowSessionPrefs] = useState(false);
  const [interactionStyle, setInteractionStyle] = useState<string | null>(null);
  const [wantHints, setWantHints] = useState<boolean | null>(null);
  const [timeBudget, setTimeBudget] = useState<number | null>(null);
  const [confidence, setConfidence] = useState<string | null>(null);

  const { data: curriculumTaskModels } = useTaskModels('curriculum');

  useEffect(() => {
    if (!resources.length) {
      setSelectedResourceIds([]);
      return;
    }
    setSelectedResourceIds((current) => {
      const valid = current.filter((resourceId) => resources.some((resource) => resource.id === resourceId));
      return valid.length > 0 ? valid : [resources[0].id];
    });
  }, [resources]);

  useEffect(() => {
    setMode(recommendedMode);
  }, [recommendedMode]);

  const includedResourceIds = selectedResourceIds;
  const anchorResourceId = selectedResourceIds[0] ?? '';
  const allSelected = resources.length > 0 && selectedResourceIds.length === resources.length;

  const includedResources = resources.filter((resource) => includedResourceIds.includes(resource.id));
  const blockedResources = includedResources.filter((resource) => !isResourceReadyForMode(resource, mode));
  const hasBlockedResources = blockedResources.length > 0;
  const hasResources = resources.length > 0;
  const learnerInputMeta = MODE_INPUT_META[mode];
  const parsedTopics = useMemo(() => parseTopicInput(topicInput, mode), [mode, topicInput]);
  const hasLearnerInput = Boolean(parsedTopics.topic || (parsedTopics.selected_topics?.length ?? 0) > 0);
  const requiresLearnerInput = learnerInputMeta.required;
  const launchDisabled = pending
    || !anchorResourceId
    || includedResourceIds.length === 0
    || hasBlockedResources
    || (requiresLearnerInput && !hasLearnerInput);

  const handleToggleResource = (resourceId: string) => {
    setSelectedResourceIds((current) => {
      if (current.includes(resourceId)) {
        if (current.length === 1) return current;
        return current.filter((id) => id !== resourceId);
      }
      return [...current, resourceId];
    });
  };

  const handleSelectAll = () => setSelectedResourceIds(resources.map((r) => r.id));

  const handleLaunch = async () => {
    if (!anchorResourceId) return;

    if (requiresLearnerInput && !hasLearnerInput) return;

    // Build session personalization
    const personalization: SessionPersonalization = {};
    if (interactionStyle) personalization.interaction_style = interactionStyle as SessionPersonalization['interaction_style'];
    if (wantHints !== null) personalization.want_hints = wantHints;
    if (timeBudget) personalization.time_budget_minutes = timeBudget;
    if (confidence) personalization.confidence = confidence as SessionPersonalization['confidence'];
    const hasPersonalization = Object.keys(personalization).length > 0;

    await onLaunch({
      resource_id: anchorResourceId,
      selected_resource_ids: !allSelected ? selectedResourceIds : [],
      notebook_wide: allSelected,
      mode,
      topic: parsedTopics.topic,
      selected_topics: parsedTopics.selected_topics,
      resume_existing: resumeExisting,
      curriculum_model_id: curriculumModelId || undefined,
      ...(hasPersonalization ? { personalization } : {}),
    });
  };

  const ModeIcon = MODE_META[mode].icon;

  if (!hasResources) {
    return (
      <div className="space-y-3">
        {title && (
          <div>
            <h3 className="editorial-title text-2xl text-foreground">{title}</h3>
            {subtitle && <p className="mt-1 text-sm text-muted-foreground reading-copy">{subtitle}</p>}
          </div>
        )}
        <div className="rounded-[20px] border border-dashed border-gold/25 bg-gradient-to-br from-gold/[0.06] via-card/85 to-card/95 px-4 py-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="inline-flex items-center gap-1.5 rounded-full border border-gold/20 bg-card/80 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.15em] text-gold">
                <AlertCircle className="h-3 w-3" />
                No resources yet
              </div>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground reading-copy">
                Upload a lecture PDF, notes, or slides to begin. Once attached, choose a study mode and start.
              </p>
            </div>
            {onManageResources && (
              <button
                type="button"
                onClick={onManageResources}
                className="font-ui inline-flex shrink-0 items-center gap-1.5 rounded-[16px] bg-gold px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-gold/90"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {manageResourcesLabel}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {title && (
        <div>
          <h3 className="editorial-title text-2xl text-foreground">{title}</h3>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground reading-copy">{subtitle}</p>}
        </div>
      )}

      {/* Mode grid — 2×2 */}
      <div className="grid grid-cols-2 gap-2">
        {MODES.map((item) => {
          const meta = MODE_META[item];
          const Icon = meta.icon;
          const active = item === mode;
          const recommended = item === recommendedMode;
          return (
            <button
              key={item}
              type="button"
              onClick={() => setMode(item)}
              className={`relative rounded-[20px] border p-4 text-left transition-all ${active ? 'border-gold/30 bg-gold/[0.08] shadow-[0_12px_24px_-16px_hsl(155_28%_38%_/_0.5)]' : 'border-border/70 bg-card/60 hover:border-gold/20 hover:bg-muted/40'}`}
            >
              {recommended && (
                <span className={`absolute right-2.5 top-2.5 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.10em] ${active ? 'border-gold/20 bg-gold/10 text-gold' : 'border-border bg-background text-muted-foreground'}`}>
                  Suggested
                </span>
              )}
              {active && !recommended && (
                <CheckCircle2 className="absolute right-2.5 top-2.5 h-3.5 w-3.5 text-gold" />
              )}
              <Icon className={`mb-2.5 h-6 w-6 ${active ? 'text-gold' : meta.accent}`} />
              <div className="font-ui text-sm font-semibold text-foreground">{meta.label}</div>
              <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{meta.description}</p>
            </button>
          );
        })}
      </div>

      {/* Resources + topic */}
      <div className="rounded-[20px] border border-border/60 bg-background/50 p-3.5 space-y-3">
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="section-kicker text-[10px] font-semibold text-muted-foreground">
              Scope · {selectedResourceIds.length} of {resources.length}
            </span>
            {resources.length > 1 && (
              <button
                type="button"
                onClick={allSelected ? () => setSelectedResourceIds([resources[0].id]) : handleSelectAll}
                className="text-[10px] font-medium text-gold/70 hover:text-gold transition-colors"
              >
                {allSelected ? 'Clear' : 'All'}
              </button>
            )}
          </div>
          <div className="space-y-1">
            {resources.map((resource) => {
              const selected = selectedResourceIds.includes(resource.id);
              const blocked = selected && !isResourceReadyForMode(resource, mode);
              return (
                <label
                  key={resource.id}
                  className={`flex items-center gap-2.5 rounded-[12px] border px-2.5 py-1.5 cursor-pointer transition-all ${selected ? 'border-gold/20 bg-gold/[0.04]' : 'border-border/50 hover:border-gold/10 hover:bg-muted/20'}`}
                >
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => handleToggleResource(resource.id)}
                    className="h-3 w-3 shrink-0 accent-[hsl(var(--gold))]"
                  />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{resource.label}</span>
                  {blocked && (
                    <span className="shrink-0 text-[9px] font-medium text-amber-400">
                      {mode === 'doubt' ? 'Parsing' : 'Preparing'}
                    </span>
                  )}
                </label>
              );
            })}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="section-kicker text-[10px] font-semibold text-muted-foreground">{learnerInputMeta.label}</span>
            {requiresLearnerInput && (
              <span className="text-[9px] font-semibold uppercase text-amber-500 dark:text-amber-400">Required</span>
            )}
          </div>
          <input
            value={topicInput}
            onChange={(event) => setTopicInput(event.target.value)}
            placeholder={learnerInputMeta.placeholder}
            className={`w-full rounded-[14px] border bg-card px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/50 focus:border-gold/30 ${requiresLearnerInput && !hasLearnerInput ? 'border-amber-500/40 bg-amber-500/[0.03]' : 'border-border/60'}`}
          />
        </div>
      </div>

      {/* Blocked warning */}
      {hasBlockedResources && (
        <div className="flex items-start gap-2 rounded-[16px] border border-amber-500/20 bg-amber-500/[0.08] px-3 py-2.5">
          <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5 text-amber-400" />
          <p className="text-xs text-amber-200/90 leading-relaxed">
            {mode === 'doubt' ? 'Deselect resources still parsing.' : 'Deselect resources still preparing.'}
            {' '}<span className="text-amber-300/70">{blockedResources.map((r) => r.label).join(', ')}</span>
          </p>
        </div>
      )}

      {/* Curriculum model — shown only for non-doubt modes (which need curriculum) */}
      {mode !== 'doubt' && (curriculumTaskModels?.allowed_models?.length ?? 0) > 0 && (
        <div className="flex items-center gap-2 px-0.5">
          <Cpu className="w-3 h-3 text-muted-foreground/60 shrink-0" />
          <span className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground/70 shrink-0">Curriculum model</span>
          <select
            value={curriculumModelId}
            onChange={(e) => setCurriculumModelId(e.target.value)}
            className="flex-1 min-w-0 rounded-lg border border-border/60 bg-background/60 px-2 py-1 text-[11px] text-foreground focus:outline-none focus:border-gold/30"
          >
            <option value="">Default ({curriculumTaskModels?.default_model_id?.split('/').pop() ?? '…'})</option>
            {(curriculumTaskModels?.allowed_models ?? []).map((m) => (
              <option key={m.model_id} value={m.model_id}>{m.display_name}</option>
            ))}
          </select>
        </div>
      )}

      {/* Session personalization — collapsible "Tutor me today as…" */}
      <div className="rounded-[16px] border border-border/50 overflow-hidden">
        <button
          type="button"
          onClick={() => setShowSessionPrefs(!showSessionPrefs)}
          className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-foreground hover:bg-muted/20 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-gold" />
            Tutor me today as…
            {(interactionStyle || wantHints !== null || timeBudget || confidence) && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gold/15 text-gold font-medium">customized</span>
            )}
          </span>
          <ChevronDown className={cn('w-3.5 h-3.5 text-muted-foreground transition-transform', showSessionPrefs && 'rotate-180')} />
        </button>

        {showSessionPrefs && (
          <div className="px-3 pb-3 pt-1 space-y-3 border-t border-border/30">
            <p className="text-[10px] text-muted-foreground reading-copy">Shape this session only. These won't persist to future sessions.</p>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-1.5">Style</label>
                <select
                  value={interactionStyle ?? ''}
                  onChange={(e) => setInteractionStyle(e.target.value || null)}
                  className="w-full rounded-lg border border-border/50 bg-background/60 px-2 py-1.5 text-[11px] text-foreground focus:outline-none focus:border-gold/30 transition-colors"
                >
                  <option value="">Default</option>
                  <option value="explanation-heavy">Explanation heavy</option>
                  <option value="practice-heavy">Practice heavy</option>
                  <option value="balanced">Balanced</option>
                  <option value="revision">Revision</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-1.5">Confidence</label>
                <select
                  value={confidence ?? ''}
                  onChange={(e) => setConfidence(e.target.value || null)}
                  className="w-full rounded-lg border border-border/50 bg-background/60 px-2 py-1.5 text-[11px] text-foreground focus:outline-none focus:border-gold/30 transition-colors"
                >
                  <option value="">Not set</option>
                  <option value="unsure">Unsure</option>
                  <option value="somewhat">Somewhat</option>
                  <option value="confident">Confident</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-1.5">Time budget</label>
                <select
                  value={timeBudget ?? ''}
                  onChange={(e) => setTimeBudget(e.target.value ? Number(e.target.value) : null)}
                  className="w-full rounded-lg border border-border/50 bg-background/60 px-2 py-1.5 text-[11px] text-foreground focus:outline-none focus:border-gold/30 transition-colors"
                >
                  <option value="">No limit</option>
                  <option value="15">15 min</option>
                  <option value="30">30 min</option>
                  <option value="45">45 min</option>
                  <option value="60">1 hour</option>
                  <option value="90">1.5 hours</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-1.5">Hints first</label>
                <select
                  value={wantHints === true ? 'yes' : ''}
                  onChange={(e) => setWantHints(e.target.value === 'yes' ? true : null)}
                  className="w-full rounded-lg border border-border/50 bg-background/60 px-2 py-1.5 text-[11px] text-foreground focus:outline-none focus:border-gold/30 transition-colors"
                >
                  <option value="">No preference</option>
                  <option value="yes">Yes, give hints</option>
                </select>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Launch row */}
      <div className="flex items-center gap-3 pt-1">
        <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
          <input
            type="checkbox"
            checked={resumeExisting}
            onChange={(event) => setResumeExisting(event.target.checked)}
            className="h-3 w-3 accent-[hsl(var(--gold))]"
          />
          <span className="text-xs text-muted-foreground">Reuse active</span>
        </label>

        <div className="flex items-center gap-2 ml-auto">
          {onManageResources && (
            <button
              type="button"
              onClick={onManageResources}
              className="font-ui inline-flex items-center gap-1.5 rounded-[16px] border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:border-gold/20 hover:text-gold"
            >
              {manageResourcesLabel}
            </button>
          )}
          <button
            type="button"
            disabled={launchDisabled}
            onClick={() => void handleLaunch()}
            className="font-ui inline-flex items-center gap-1.5 rounded-[16px] bg-gold px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-gold/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ModeIcon className="h-3.5 w-3.5" />}
            {ctaLabel || `Start ${MODE_META[mode].label}`}
          </button>
        </div>
      </div>

      {requiresLearnerInput && !hasLearnerInput && !hasBlockedResources && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          Add your doubt first so the session can open correctly.
        </p>
      )}
    </div>
  );
}