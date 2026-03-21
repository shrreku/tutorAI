/**
 * Left context panel for the study workspace (PROD-009).
 *
 * Vertical timeline study map with live updates, collapsible resources,
 * mastery grouped by concept scope, and weak concepts.
 * Section order: Study Map → Resources → Mastery → Needs Review.
 */

import { useMemo, useState } from 'react';
import {
  Target, AlertTriangle, FileText,
  Circle, Brain, ChevronDown, Lock, CheckCircle2,
  Zap, ArrowRight,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import type { TopicInfo } from '../../types/api';
import type { ObjectiveSnapshot, StudyMapSnapshot, StudyMapObjectiveSnapshot } from '../../types/session-events';

interface ResourceItem {
  id: string;
  label: string;
  subtitle?: string;
  status?: string;
  studyReady?: boolean;
}

interface ResourceTopicGroup {
  resourceId: string;
  resourceLabel: string;
  courseTopic?: string | null;
  topics: TopicInfo[];
}

interface MasteryGroupData {
  objectiveId: string;
  title: string;
  subtitle?: string | null;
  status: 'pending' | 'active' | 'completed' | 'skipped';
  isCurrent: boolean;
  avgScore: number;
  conceptGroups: Array<{ label: string; items: [string, number][] }>;
}

interface ContextPanelProps {
  resources: ResourceItem[];
  resourceTopics?: ResourceTopicGroup[];
  objectives: ObjectiveSnapshot[];
  mastery: Record<string, number>;
  weakConcepts: string[];
  mode: string | null;
  collapsed?: boolean;
  studyMapSnapshot?: StudyMapSnapshot | null;
}

/* ── Mastery bar (horizontal with percentage) ──────────────────────── */
function MasteryBar({ score, label }: { score: number; label: string }) {
  const pct = Math.round(score * 100);
  const barColor =
    pct >= 70 ? 'bg-gold' : pct >= 40 ? 'bg-gold/70' : 'bg-muted-foreground/30';
  return (
    <div className="py-0.5">
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-[10px] text-foreground truncate font-reading leading-tight">{label}</span>
        <span className="text-[10px] font-semibold text-foreground tabular-nums shrink-0 font-ui">{pct}%</span>
      </div>
      <div className="h-[3px] rounded-full bg-border/50 overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-700 ease-out', barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/* ── Step indicator (tiny horizontal step dots for an objective) ──── */
function StepProgress({ steps }: { steps: StudyMapObjectiveSnapshot['steps'] }) {
  if (!steps || steps.length === 0) return null;
  return (
    <div className="flex items-center gap-1 mt-2">
      {steps.map((step, i) => {
        const isCompleted = step.status === 'completed';
        const isActive = step.status === 'active';
        return (
          <div key={i} className="flex items-center gap-1">
            <div
              className={cn(
                'h-1.5 rounded-full transition-all duration-500',
                isCompleted ? 'w-4 bg-gold' :
                isActive ? 'w-4 bg-gold/60 animate-pulse' :
                'w-2 bg-border/60',
              )}
              title={`${step.type}: ${step.goal || ''}`}
            />
            {i < steps.length - 1 && (
              <div className={cn(
                'w-1 h-px',
                isCompleted ? 'bg-gold/40' : 'bg-border/30',
              )} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Study map objective (vertical timeline node) ──────────────────── */
function StudyMapNode({
  obj,
  liveObj,
  isLast,
  masteryForObjective,
  isCurrent,
}: {
  obj: ObjectiveSnapshot;
  liveObj?: StudyMapObjectiveSnapshot;
  isLast: boolean;
  masteryForObjective: [string, number][];
  isCurrent: boolean;
}) {
  const [open, setOpen] = useState(isCurrent);

  // Prefer live status from snapshot
  const status = liveObj?.status || obj.status;
  const steps = liveObj?.steps || [];

  const isActive = status === 'active';
  const isCompleted = status === 'completed';
  const isPending = !isActive && !isCompleted;

  const avgMastery = masteryForObjective.length > 0
    ? Math.round((masteryForObjective.reduce((s, [, v]) => s + v, 0) / masteryForObjective.length) * 100)
    : isCompleted ? 100 : isActive ? 40 : 0;

  const completedSteps = steps.filter(s => s.status === 'completed').length;
  const totalSteps = steps.length || obj.step_count || 0;

  // Node dot
  const dotClass = isCompleted
    ? 'bg-gold border-gold'
    : isActive
      ? 'bg-gold/80 border-gold ring-2 ring-gold/20'
      : 'bg-muted-foreground/20 border-border';

  return (
    <div className="relative flex gap-3">
      {/* Vertical line + dot */}
      <div className="flex flex-col items-center pt-0.5">
        <div className={cn('w-3 h-3 rounded-full border-2 shrink-0 z-10 transition-all duration-300', dotClass)}>
          {isCompleted && <CheckCircle2 className="w-2 h-2 text-background m-auto" />}
        </div>
        {!isLast && (
          <div className={cn(
            'w-px flex-1 mt-1 transition-colors',
            isCompleted ? 'bg-gold/40' : 'bg-border/50',
          )} />
        )}
      </div>

      {/* Content */}
      <div className={cn('flex-1 min-w-0 pb-4', isLast && 'pb-1')}>
        <button
          onClick={() => setOpen(!open)}
          className="w-full text-left group"
        >
          <h4 className={cn(
            'text-sm leading-snug transition-colors font-reading',
            isPending ? 'text-muted-foreground' : 'text-foreground font-semibold',
          )}>
            {obj.title}
          </h4>

          {/* Step progress dots (live) */}
          {isActive && steps.length > 0 && <StepProgress steps={steps} />}

          {/* Status line */}
          <div className="mt-1.5 flex items-center gap-2">
            {isPending && <Lock className="w-3 h-3 text-muted-foreground/40" />}
            {isActive && <Zap className="w-3 h-3 text-gold" />}
            <span className={cn(
              'text-[10px] uppercase tracking-wider font-ui',
              isCompleted ? 'text-gold font-semibold' :
              isActive ? 'text-gold/80 font-medium' :
              'text-muted-foreground/60',
            )}>
              {isCompleted
                ? `${avgMastery}% mastery`
                : isActive
                  ? `Step ${completedSteps + 1}/${totalSteps || '?'}`
                  : 'Upcoming'}
            </span>
            {(obj.primary_concepts.length > 0 || obj.description) && (
              <ChevronDown className={cn(
                'w-3 h-3 ml-auto text-muted-foreground/50 transition-transform',
                open && 'rotate-180',
              )} />
            )}
          </div>
        </button>

        {/* Collapsible details */}
        {open && (
          <div className="mt-2 space-y-2 animate-fade-up">
            {obj.description && (
              <p className="text-[11px] leading-relaxed text-muted-foreground/80 reading-copy">
                {obj.description}
              </p>
            )}

            {/* Concept pills grouped by scope */}
            {obj.primary_concepts.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex flex-wrap gap-1">
                  {obj.primary_concepts.map((c) => (
                    <span
                      key={c}
                      className="data-chip rounded-full border border-gold/20 bg-gold/5 px-2 py-0.5 text-[10px] text-gold font-medium"
                    >
                      {c}
                    </span>
                  ))}
                </div>
                {obj.prereq_concepts && obj.prereq_concepts.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    <span className="text-[9px] text-muted-foreground/50 uppercase tracking-wider mr-1 self-center font-ui">prereqs</span>
                    {obj.prereq_concepts.map((c) => (
                      <span
                        key={c}
                        className="data-chip rounded-full border border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                )}
                {obj.support_concepts && obj.support_concepts.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    <span className="text-[9px] text-muted-foreground/50 uppercase tracking-wider mr-1 self-center font-ui">support</span>
                    {obj.support_concepts.map((c) => (
                      <span
                        key={c}
                        className="data-chip rounded-full border border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Mastery bars for this objective's concepts */}
            {masteryForObjective.length > 0 && (
              <div className="mt-1">
                {masteryForObjective.map(([concept, score]) => (
                  <MasteryBar key={concept} label={concept} score={score} />
                ))}
              </div>
            )}

            {/* Live step details for active objective */}
            {isActive && steps.length > 0 && (
              <div className="mt-1 space-y-0.5">
                {steps.map((step, i) => (
                  <div
                    key={i}
                    className={cn(
                      'flex items-center gap-2 px-2 py-1 rounded text-[11px] transition-colors font-ui uppercase tracking-[0.08em]',
                      step.status === 'completed' ? 'text-muted-foreground' :
                      step.status === 'active' ? 'bg-gold/[0.06] text-foreground font-medium' :
                      'text-muted-foreground/50',
                    )}
                  >
                    {step.status === 'completed' ? (
                      <CheckCircle2 className="w-3 h-3 text-gold/60 shrink-0" />
                    ) : step.status === 'active' ? (
                      <ArrowRight className="w-3 h-3 text-gold shrink-0" />
                    ) : (
                      <Circle className="w-2.5 h-2.5 text-muted-foreground/30 shrink-0" />
                    )}
                    <span className="capitalize truncate">{step.type.replace('_', ' ')}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Collapsible section wrapper ───────────────────────────────────── */
function CollapsibleSection({
  icon: Icon,
  title,
  count,
  defaultOpen = true,
  children,
  titleColor,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  count?: number | string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  titleColor?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 mb-2 w-full text-left group"
      >
        <Icon className={cn('w-3.5 h-3.5', titleColor || 'text-muted-foreground')} />
        <h3 className={cn(
          'text-[10px] font-semibold uppercase tracking-[0.16em] font-ui',
          titleColor || 'text-muted-foreground',
        )}>
          {title}
        </h3>
        {count !== undefined && (
          <span className="text-[10px] text-muted-foreground/60 ml-auto tabular-nums mr-1 font-ui">
            {count}
          </span>
        )}
        <ChevronDown className={cn(
          'w-3 h-3 text-muted-foreground/40 transition-transform',
          !open && '-rotate-90',
        )} />
      </button>
      {open && children}
    </section>
  );
}

function MasteryTopicGroup({
  title,
  subtitle,
  status,
  isCurrent,
  avgScore,
  conceptGroups,
  defaultOpen = false,
}: {
  title: string;
  subtitle?: string | null;
  status: 'pending' | 'active' | 'completed' | 'skipped';
  isCurrent: boolean;
  avgScore: number;
  conceptGroups: Array<{ label: string; items: [string, number][] }>;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const conceptCount = conceptGroups.reduce((sum, group) => sum + group.items.length, 0);
  const statusTone = status === 'completed'
    ? 'bg-emerald-500/10 text-emerald-500'
    : status === 'active'
      ? 'bg-gold/10 text-gold'
      : 'bg-muted/50 text-muted-foreground';

  return (
    <div className={cn(
      'rounded-[16px] border border-border/70 bg-card/70 px-3 py-2.5',
      isCurrent && 'border-gold/25 bg-gold/[0.03]',
    )}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-start gap-2 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <p className="font-reading text-sm text-foreground truncate">{title}</p>
            {isCurrent && (
              <span className="data-chip rounded-full border border-gold/15 bg-gold/[0.06] px-2 py-0.5 text-[9px] text-gold">
                Current
              </span>
            )}
          </div>
          {subtitle && (
            <p className="mt-0.5 text-[9px] font-ui uppercase tracking-[0.08em] text-muted-foreground truncate">
              {subtitle}
            </p>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[9px] font-ui uppercase tracking-[0.08em] text-muted-foreground">
            <span className={cn('rounded-full px-2 py-0.5', statusTone)}>{status}</span>
            <span>{conceptCount} concepts</span>
            <span>{avgScore}% avg</span>
          </div>
        </div>
        <ChevronDown className={cn(
          'mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/50 transition-transform',
          open && 'rotate-180',
        )} />
      </button>

      {open && (
        <div className="mt-2.5 space-y-2">
          {conceptGroups.map((group) => (
            group.items.length > 0 ? (
              <div key={group.label}>
                <p className="mb-1 text-[8px] uppercase tracking-wider text-muted-foreground/50 font-ui">{group.label}</p>
                {group.items.map(([concept, score]) => (
                  <MasteryBar key={concept} label={concept} score={score} />
                ))}
              </div>
            ) : null
          ))}
        </div>
      )}
    </div>
  );
}

export default function ContextPanel({
  resources,
  resourceTopics = [],
  objectives,
  mastery,
  weakConcepts,
  mode,
  collapsed = false,
  studyMapSnapshot,
}: ContextPanelProps) {
  const masteryEntries = useMemo(
    () => Object.entries(mastery).sort((a, b) => a[1] - b[1]).slice(0, 20),
    [mastery],
  );

  // Look up live objective data from snapshot
  const liveObjMap = useMemo(() => {
    const map = new Map<string, StudyMapObjectiveSnapshot>();
    if (studyMapSnapshot) {
      for (const obj of studyMapSnapshot.objectives) {
        map.set(obj.objective_id, obj);
      }
    }
    return map;
  }, [studyMapSnapshot]);

  const masteryByObjective = useMemo(() => {
    const byObj = new Map<string, [string, number][]>();
    for (const obj of objectives) {
      const seen = new Set<string>();
      const pairs: [string, number][] = [];
      for (const concept of [...obj.primary_concepts, ...(obj.support_concepts || []), ...(obj.prereq_concepts || [])]) {
        if (!(concept in mastery) || seen.has(concept)) continue;
        seen.add(concept);
        pairs.push([concept, mastery[concept]]);
      }
      byObj.set(obj.objective_id, pairs);
    }
    return byObj;
  }, [mastery, objectives]);

  const { fallbackMasteryGroups, fallbackRemainingMastery } = useMemo(() => {
    const assigned = new Set<string>();
    const groups = objectives.map<MasteryGroupData | null>((obj, index) => {
      const collect = (concepts: string[]) => concepts.reduce<[string, number][]>((items, concept) => {
        if (!(concept in mastery) || assigned.has(concept)) return items;
        assigned.add(concept);
        items.push([concept, mastery[concept]]);
        return items;
      }, []);

      const primary = collect(obj.primary_concepts);
      const support = collect(obj.support_concepts || []);
      const prereq = collect(obj.prereq_concepts || []);
      const flatItems = [...primary, ...support, ...prereq];
      if (flatItems.length === 0) return null;

      const avgScore = Math.round((flatItems.reduce((sum, [, score]) => sum + score, 0) / flatItems.length) * 100);
      const liveObjective = liveObjMap.get(obj.objective_id);
      const status = (liveObjective?.status || obj.status) as 'pending' | 'active' | 'completed' | 'skipped';
      const isCurrent = studyMapSnapshot
        ? index === studyMapSnapshot.current_objective_index
        : status === 'active';

      return {
        objectiveId: obj.objective_id,
        title: liveObjective?.title || obj.title,
        status,
        isCurrent,
        avgScore,
        conceptGroups: [
          { label: 'Core concepts', items: primary },
          { label: 'Support concepts', items: support },
          { label: 'Prerequisites', items: prereq },
        ],
      };
    }).filter((group): group is MasteryGroupData => Boolean(group));

    const remaining = masteryEntries.filter(([concept]) => !assigned.has(concept));
    return {
      fallbackMasteryGroups: groups,
      fallbackRemainingMastery: remaining,
    };
  }, [liveObjMap, mastery, masteryEntries, objectives, studyMapSnapshot]);

  const { topicBundleMasteryGroups, topicBundleRemainingMastery } = useMemo(() => {
    const assigned = new Set<string>();
    const groups = resourceTopics.flatMap((resourceTopic) => {
      return resourceTopic.topics.map<MasteryGroupData | null>((topic) => {
        const primary = (topic.concept_details || []).reduce<[string, number][]>((items, detail) => {
          if (detail.role !== 'primary' || !(detail.concept_id in mastery) || assigned.has(detail.concept_id)) return items;
          assigned.add(detail.concept_id);
          items.push([detail.concept_id, mastery[detail.concept_id]]);
          return items;
        }, []);

        const support = (topic.concept_details || []).reduce<[string, number][]>((items, detail) => {
          if (detail.role !== 'support' || !(detail.concept_id in mastery) || assigned.has(detail.concept_id)) return items;
          assigned.add(detail.concept_id);
          items.push([detail.concept_id, mastery[detail.concept_id]]);
          return items;
        }, []);

        const flatItems = [...primary, ...support];
        if (flatItems.length === 0) return null;

        const relatedObjectiveIndex = objectives.findIndex((objective) => {
          const objectiveConcepts = new Set([
            ...objective.primary_concepts,
            ...(objective.support_concepts || []),
            ...(objective.prereq_concepts || []),
          ]);
          return flatItems.some(([concept]) => objectiveConcepts.has(concept));
        });
        const relatedObjective = relatedObjectiveIndex >= 0 ? objectives[relatedObjectiveIndex] : null;
        const liveObjective = relatedObjective ? liveObjMap.get(relatedObjective.objective_id) : null;
        const status = ((liveObjective?.status || relatedObjective?.status || 'pending') as 'pending' | 'active' | 'completed' | 'skipped');
        const isCurrent = relatedObjective
          ? (studyMapSnapshot
            ? relatedObjectiveIndex === studyMapSnapshot.current_objective_index
            : status === 'active')
          : false;
        const avgScore = Math.round((flatItems.reduce((sum, [, score]) => sum + score, 0) / flatItems.length) * 100);

        return {
          objectiveId: `${resourceTopic.resourceId}:${topic.topic_id}`,
          title: topic.topic_name,
          subtitle: resourceTopic.resourceLabel,
          status,
          isCurrent,
          avgScore,
          conceptGroups: [
            { label: 'Primary concepts', items: primary },
            { label: 'Support concepts', items: support },
          ],
        };
      }).filter((group): group is MasteryGroupData => Boolean(group));
    });

    const remaining = masteryEntries.filter(([concept]) => !assigned.has(concept));
    return {
      topicBundleMasteryGroups: groups,
      topicBundleRemainingMastery: remaining,
    };
  }, [liveObjMap, mastery, masteryEntries, objectives, resourceTopics, studyMapSnapshot]);

  const masteryTopicGroups = topicBundleMasteryGroups.length > 0 ? topicBundleMasteryGroups : fallbackMasteryGroups;
  const remainingMastery = topicBundleMasteryGroups.length > 0 ? topicBundleRemainingMastery : fallbackRemainingMastery;

  const completedCount = useMemo(() => {
    if (studyMapSnapshot) {
      return studyMapSnapshot.objectives.filter(o => o.status === 'completed').length;
    }
    return objectives.filter(o => o.status === 'completed').length;
  }, [objectives, studyMapSnapshot]);

  const progressionBadge = useMemo(() => {
    const decision = studyMapSnapshot?.last_decision;
    if (!decision) return null;
    const adHocLabel = studyMapSnapshot?.last_ad_hoc_type
      ? `Ad-hoc: ${studyMapSnapshot.last_ad_hoc_type.replace(/_/g, ' ')}`
      : 'Ad-hoc';
    const mapping: Record<string, { label: string; tone: string }> = {
      CONTINUE_STEP: { label: 'Stay', tone: 'bg-muted/40 text-muted-foreground' },
      ADVANCE_STEP: { label: 'Next step', tone: 'bg-gold/10 text-gold' },
      SKIP_TO_STEP: { label: 'Skip ahead', tone: 'bg-gold/10 text-gold' },
      INSERT_AD_HOC: { label: adHocLabel, tone: 'bg-gold/10 text-gold' },
      ADVANCE_OBJECTIVE: { label: 'Next objective', tone: 'bg-gold/10 text-gold' },
      END_SESSION: { label: 'Completed', tone: 'bg-emerald-500/10 text-emerald-500' },
    };
    return mapping[decision] || { label: decision.toLowerCase().replace(/_/g, ' '), tone: 'bg-muted/40 text-muted-foreground' };
  }, [studyMapSnapshot]);

  const hasMasteryGroups = masteryTopicGroups.length > 0 || remainingMastery.length > 0;

  if (collapsed) {
    return (
      <div className="flex flex-col items-center py-4 gap-4">
        <Target className="w-4 h-4 text-muted-foreground" />
        <FileText className="w-4 h-4 text-muted-foreground" />
        <Brain className="w-4 h-4 text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden surface-scholarly">
      <div className="flex-1 overflow-y-auto p-4 space-y-5">

        {/* ── 1. Study Map (FIRST — vertical timeline) ──────────── */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Target className="w-3.5 h-3.5 text-gold" />
            <h3 className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground font-ui">
              Study Map
            </h3>
            {objectives.length > 0 && (
              <span className="text-[10px] text-muted-foreground/60 ml-auto tabular-nums font-ui">
                {completedCount}/{objectives.length}
              </span>
            )}
            {progressionBadge && (
              <span
                className={cn('text-[9px] px-1.5 py-0.5 rounded-full font-ui uppercase', progressionBadge.tone)}
                title={studyMapSnapshot?.last_transition || undefined}
              >
                {progressionBadge.label}
              </span>
            )}
            {studyMapSnapshot && studyMapSnapshot.ad_hoc_count > 0 && (
              <span className="text-[9px] bg-gold/10 text-gold px-1.5 py-0.5 rounded-full font-ui uppercase">
                {studyMapSnapshot.ad_hoc_count} ad-hoc
              </span>
            )}
          </div>

          {objectives.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border py-6 text-center">
              <Circle className="mx-auto mb-2 w-6 h-6 text-muted-foreground/20" />
              <p className="text-[11px] text-muted-foreground/60">
                Start a study session to build your map
              </p>
            </div>
          ) : (
            <div className="pl-1">
              {objectives.map((obj, i) => (
                <StudyMapNode
                  key={obj.objective_id}
                  obj={obj}
                  liveObj={liveObjMap.get(obj.objective_id)}
                  isLast={i === objectives.length - 1}
                  masteryForObjective={masteryByObjective.get(obj.objective_id) || []}
                  isCurrent={studyMapSnapshot
                    ? i === studyMapSnapshot.current_objective_index
                    : obj.status === 'active'}
                />
              ))}
            </div>
          )}
        </section>

        {/* ── 2. Resources (collapsible) ──────────────────────────── */}
        <CollapsibleSection
          icon={FileText}
          title="Resources"
          count={resources.length}
          defaultOpen={resources.length <= 3}
        >
          {resources.length === 0 ? (
            <p className="text-[11px] text-muted-foreground/60 italic pl-1 reading-copy">No resources attached</p>
          ) : (
            <div className="space-y-0.5">
              {resources.map((r) => (
                <div key={r.id} className="flex items-center gap-2 py-1.5 px-1">
                  <div className={cn(
                    'h-2 w-2 rounded-full shrink-0',
                    r.studyReady ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse',
                  )} />
                  <span className="text-xs text-foreground truncate flex-1 font-reading">{r.label}</span>
                  <span className={cn(
                    'text-[9px] uppercase tracking-wider shrink-0 font-ui',
                    r.studyReady ? 'text-emerald-500' : 'text-amber-500',
                  )}>
                    {r.studyReady ? 'ready' : r.status || 'processing'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CollapsibleSection>

        {/* ── 3. Mastery (grouped by curriculum topics/objectives) ── */}
        {hasMasteryGroups && (
          <CollapsibleSection icon={Brain} title="Mastery" defaultOpen>
            <div className="space-y-3">
              {masteryTopicGroups.map((group) => (
                <MasteryTopicGroup
                  key={group.objectiveId}
                  title={group.title}
                  subtitle={group.subtitle}
                  status={group.status}
                  isCurrent={group.isCurrent}
                  avgScore={group.avgScore}
                  conceptGroups={group.conceptGroups}
                  defaultOpen={group.isCurrent}
                />
              ))}
              {remainingMastery.length > 0 && (
                <div className="rounded-[16px] border border-border/70 bg-card/60 px-3 py-2.5">
                  <p className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground font-ui">Additional concepts</p>
                  <div className="mt-1.5">
                    {remainingMastery.map(([concept, score]) => (
                      <MasteryBar key={concept} label={concept} score={score} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CollapsibleSection>
        )}

        {/* ── 4. Needs Review ──────────────────────────────────────── */}
        {weakConcepts.length > 0 && (
          <CollapsibleSection
            icon={AlertTriangle}
            title="Needs Review"
            titleColor="text-amber-600"
            defaultOpen
          >
            <div className="flex flex-wrap gap-1.5">
              {weakConcepts.slice(0, 8).map((c) => (
                <span
                  key={c}
                  className="data-chip rounded-full border border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 px-2.5 py-1 text-[10px] text-amber-700 dark:text-amber-400"
                >
                  {c}
                </span>
              ))}
            </div>
          </CollapsibleSection>
        )}
      </div>

      {/* Mode indicator at bottom */}
      {mode && (
        <div className="shrink-0 px-3 py-2 border-t border-border/40">
          <div className="flex items-center gap-2">
            <div className={cn(
              'w-2 h-2 rounded-full',
              mode === 'learn' ? 'bg-blue-500' :
              mode === 'doubt' ? 'bg-emerald-500' :
              mode === 'practice' ? 'bg-orange-500' :
              'bg-purple-500',
            )} />
            <span className="text-[11px] font-medium text-foreground capitalize font-ui">{mode} mode</span>
          </div>
        </div>
      )}
    </div>
  );
}
