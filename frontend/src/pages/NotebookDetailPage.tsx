import { useMemo } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Loader2, Sparkles, BarChart3, Layers,
  MessageSquare, LayoutDashboard, AlertTriangle,
  FileText, StickyNote, Plus,
  BookOpen, Target,
} from 'lucide-react';
import {
  useNotebook, useNotebookResources, useNotebookSessions,
  useNotebookProgress, useNotebookArtifacts, useResources,
  useCreateNotebookSession,
} from '../api/hooks';
import SessionLaunchPanel from '../components/notebooks/SessionLaunchPanel';
import ResourcesTab from '../components/notebooks/ResourcesTab';
import SessionsTab from '../components/notebooks/SessionsTab';
import ProgressTab from '../components/notebooks/ProgressTab';
import RichTutorContent from '../components/ui/RichTutorContent';
import type { NotebookSessionCreateRequest } from '../types/api';
import { getResourceDisplayStatus, isResourceDoubtReady, isResourceStudyReady } from '../lib/ingestion';
import { readNotebookPersonalNotes } from '../lib/notebookPersonalNotes';
import { cn } from '../lib/utils';

export default function NotebookDetailPage() {
  const navigate = useNavigate();
  const { notebookId = '' } = useParams<{ notebookId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'overview';

  const { data: notebook, isLoading: notebookLoading } = useNotebook(notebookId);
  const { data: notebookResources } = useNotebookResources(notebookId);
  const { data: notebookSessions } = useNotebookSessions(notebookId);
  const { data: progress } = useNotebookProgress(notebookId);
  const { data: artifacts } = useNotebookArtifacts(notebookId);
  const { data: allResources } = useResources();
  const createNotebookSession = useCreateNotebookSession(notebookId);

  const resourceItems = notebookResources?.items ?? [];
  const sessions = notebookSessions?.items ?? [];
  const artifactItems = artifacts?.items ?? [];
  const mastery = progress?.mastery_snapshot ?? {};
  const masteryValues = Object.values(mastery);
  const avgMastery = masteryValues.length ? Math.round((masteryValues.reduce((a, b) => a + b, 0) / masteryValues.length) * 100) : 0;
  const weakConcepts = progress?.weak_concepts_snapshot ?? [];
  const hasResources = resourceItems.length > 0;
  const activeSession = sessions.find((session) => !session.ended_at) ?? null;
  const personalNotes = useMemo(() => readNotebookPersonalNotes(notebook?.settings_json), [notebook?.settings_json]);
  const hasPersonalNotes = personalNotes.markdown.trim().length > 0;
  const resourceById = useMemo(() => new Map((allResources?.items ?? []).map((r) => [r.id, r])), [allResources?.items]);

  if (notebookLoading) return <div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 text-gold animate-spin" /></div>;
  if (!notebook) return <div className="p-8 text-sm text-muted-foreground">Notebook not found.</div>;


  const setTab = (tab: string) => {
    setSearchParams(tab === 'overview' ? {} : { tab }, { replace: true });
  };

  const recommendedMode = weakConcepts.length >= 3
    ? 'revision'
    : sessions.length === 0
      ? 'learn'
      : avgMastery < 55
        ? 'practice'
        : 'doubt';

  const recommendedReason = weakConcepts.length >= 3
    ? `You have ${weakConcepts.length} weak concepts flagged, so a revision pass should produce the most immediate gain.`
    : sessions.length === 0
      ? 'You have resources ready but no study history yet, so a structured learn session is the cleanest first step.'
      : avgMastery < 55
        ? `Average mastery is ${avgMastery}%, which suggests retrieval practice is more valuable than more passive review right now.`
        : 'Use doubt mode when you mostly understand the material but want to clear specific uncertainty before moving on.';

  const modeMeta = {
    learn: { label: 'Learn', icon: BookOpen },
    doubt: { label: 'Doubt', icon: MessageSquare },
    practice: { label: 'Practice', icon: Target },
    revision: { label: 'Revision', icon: Sparkles },
  } as const;

  const openSessionBuilder = () => {
    setTab('overview');
    window.setTimeout(() => {
      document.getElementById('session-launch-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
  };

  const recommendationModeMeta = modeMeta[recommendedMode];
  const activeModeMeta = activeSession ? modeMeta[activeSession.mode as keyof typeof modeMeta] ?? null : null;
  const recommendation = !hasResources
    ? {
        icon: FileText,
        kicker: 'Resources needed',
        title: 'Upload a resource before you start studying.',
        body: 'Add lecture notes, slides, or a chapter in the Resources tab so this notebook can generate session plans and study context.',
        actionLabel: 'Upload',
        action: () => setTab('resources'),
      }
    : activeSession
      ? {
          icon: activeModeMeta?.icon ?? MessageSquare,
          kicker: 'Session in progress',
          title: `Resume your ${activeModeMeta?.label.toLowerCase() ?? activeSession.mode} session.`,
          body: 'You already have an active study thread. Continue that session, or open the builder below if you want to branch into a different mode or scope.',
          actionLabel: 'Resume',
          action: () => navigate(`/notebooks/${notebookId}/study?sessionId=${activeSession.session_id}`),
        }
      : {
          icon: recommendationModeMeta.icon,
          kicker: 'Recommended next move',
          title: `${recommendationModeMeta.label} mode is the best next step right now.`,
          body: recommendedReason,
          actionLabel:
            recommendedMode === 'revision'
              ? 'Plan revision'
              : recommendedMode === 'practice'
                ? 'Set up practice'
                : recommendedMode === 'doubt'
                  ? 'Set up doubt mode'
                  : 'Start learning',
          action: openSessionBuilder,
        };
  const RecommendationIcon = recommendation.icon;

  const launchResources = resourceItems.map((entry) => {
    const resource = resourceById.get(entry.resource_id) ?? entry.resource ?? undefined;
    return {
      id: entry.resource_id,
      label: resource?.filename ?? 'Untitled resource',
      subtitle: resource?.topic || resource?.status || 'Attached resource',
      status: getResourceDisplayStatus(resource),
      studyReady: isResourceStudyReady(resource),
      doubtReady: isResourceDoubtReady(resource),
    };
  });

  const handleStartSession = async (request: NotebookSessionCreateRequest) => {
    const detail = await createNotebookSession.mutateAsync(request);
    navigate(`/notebooks/${notebookId}/study?sessionId=${detail.session.id}`, {
      state: { launchSummary: detail.preparation_summary },
    });
  };

  const tabs = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'resources', label: 'Resources', icon: Layers, badge: resourceItems.length || undefined },
    { id: 'sessions', label: 'Sessions', icon: MessageSquare, badge: sessions.length || undefined },
    { id: 'notes', label: 'Personal Notes', icon: StickyNote, badge: hasPersonalNotes ? `${personalNotes.wordCount}` : undefined },
    { id: 'progress', label: 'Progress & Artifacts', icon: BarChart3, badge: artifactItems.length > 0 ? `${artifactItems.length}` : undefined },
  ];

  return (
    <div className="h-full flex flex-col">
      {/* Header — compact and informational */}
      <div className="px-6 lg:px-8 pt-5 pb-0 shrink-0">
        <button onClick={() => navigate('/notebooks')} className="font-ui flex items-center gap-1.5 text-[11px] uppercase tracking-[0.22em] text-muted-foreground hover:text-foreground mb-3 transition-colors group">
          <ArrowLeft className="w-3 h-3 group-hover:-translate-x-0.5 transition-transform" /> Notebooks
        </button>

        <div className="surface-scholarly rounded-[30px] border border-border/70 px-5 py-4 md:px-6 md:py-5">
          <div className="flex items-center gap-4 md:gap-5">
            {/* Left: notebook identity */}
            <div className="shrink-0 min-w-0 max-w-[220px] md:max-w-[280px]">
              <p className="font-ui text-[9px] uppercase tracking-[0.26em] text-gold/80 mb-1">Course Notebook</p>
              <h1
                className="font-reading text-xl md:text-2xl font-bold text-foreground leading-tight tracking-tight truncate"
                title={notebook.title}
              >
                {notebook.title}
              </h1>
            </div>

            {/* Divider */}
            <div className="self-stretch w-px bg-border/50 hidden sm:block shrink-0" />

            {/* Middle: recommendation / status */}
            <div className="flex-1 min-w-0 flex items-start gap-2.5 py-0.5">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-gold/25 bg-gold/[0.07] mt-0.5">
                <RecommendationIcon className="w-3.5 h-3.5 text-gold" />
              </div>
              <div className="min-w-0">
                <p className="font-ui text-[10px] font-semibold uppercase tracking-[0.16em] text-gold/90">{recommendation.kicker}:</p>
                <p className="text-[12px] text-muted-foreground reading-copy leading-snug line-clamp-2 max-w-sm md:max-w-md">{recommendation.body}</p>
              </div>
            </div>

            {/* Right: stats + action button */}
            <div className="shrink-0 flex flex-col items-end gap-2.5 ml-auto">
              <div className="hidden md:flex items-center gap-4 text-[11px] text-muted-foreground font-ui">
                <button onClick={() => setTab('resources')} className="inline-flex items-center gap-1.5 hover:text-foreground transition-colors">
                  <FileText className="w-3 h-3" />
                  <span>{resourceItems.length} resource{resourceItems.length !== 1 ? 's' : ''}</span>
                </button>
                <button onClick={() => setTab('progress')} className="inline-flex items-center gap-1.5 hover:text-foreground transition-colors">
                  <svg viewBox="0 0 36 36" className="w-3.5 h-3.5 -rotate-90 shrink-0">
                    <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none" stroke="hsl(var(--border))" strokeWidth="5" />
                    <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                      fill="none" stroke="hsl(var(--gold))" strokeWidth="5" strokeLinecap="round"
                      strokeDasharray={`${avgMastery}, 100`} />
                  </svg>
                  <span>{avgMastery}% mastery</span>
                </button>
                {weakConcepts.length > 0 && (
                  <button onClick={() => setTab('progress')} className="inline-flex items-center gap-1 text-red-400/80 hover:text-red-400 transition-colors">
                    <AlertTriangle className="w-3 h-3" />
                    <span>{weakConcepts.length} weak</span>
                  </button>
                )}
              </div>
              <button
                onClick={recommendation.action}
                className="font-ui inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-foreground text-background text-sm font-semibold hover:opacity-85 transition-opacity whitespace-nowrap"
              >
                <RecommendationIcon className="w-3.5 h-3.5" />
                {!hasResources ? 'Upload resource' : activeSession ? 'Resume session' : `${recommendationModeMeta.label} session`}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="px-6 lg:px-8 mt-4 shrink-0">
        <div className="flex gap-0.5 border-b border-border/40">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setTab(tab.id)}
                className={cn(
                  'relative flex items-center gap-1.5 px-3 py-2.5 text-[13px] font-medium transition-colors font-ui uppercase tracking-[0.08em]',
                  isActive
                    ? 'text-gold'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/30 rounded-t-md'
                )}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
                {tab.badge != null && (
                  <span className={cn(
                    'px-1.5 py-0.5 text-[9px] rounded-full font-medium leading-none',
                    isActive ? 'bg-gold/15 text-gold' : 'bg-muted text-muted-foreground'
                  )}>
                    {tab.badge}
                  </span>
                )}
                {isActive && (
                  <span className="absolute bottom-0 left-2 right-2 h-[2px] bg-gold rounded-full" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        {activeTab === 'overview' && (
          <div className="px-6 lg:px-8 py-5 animate-tab-enter">
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">

              {/* Left: Session builder */}
              <div id="session-launch-panel" className="surface-scholarly rounded-[28px] border border-border/70 p-5">
                <div className="mb-4">
                  <h2 className="editorial-title text-2xl text-foreground">Start the right session</h2>
                  <p className="mt-1 text-sm text-muted-foreground reading-copy">Choose a mode and resources, then launch.</p>
                </div>
                <SessionLaunchPanel
                  resources={launchResources}
                  recommendedMode={recommendedMode}
                  pending={createNotebookSession.isPending}
                  onLaunch={handleStartSession}
                  onManageResources={() => setTab('resources')}
                  manageResourcesLabel="Upload resource"
                />
              </div>

              {/* Right: Sidebar */}
              <div className="space-y-4">

                {/* Resources in scope */}
                <div className="rounded-[24px] border border-border/70 bg-card/80 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-ui text-sm font-semibold text-foreground">Resources in scope</h3>
                    <button
                      onClick={() => setTab('resources')}
                      className="flex h-6 w-6 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:border-gold/30 hover:text-gold"
                    >
                      <Plus className="h-3 w-3" />
                    </button>
                  </div>
                  {resourceItems.length > 0 ? (
                    <div className="space-y-2.5">
                      {resourceItems.slice(0, 5).map((entry) => {
                        const resource = resourceById.get(entry.resource_id) ?? entry.resource ?? undefined;
                        return (
                          <div key={entry.resource_id} className="flex items-start gap-2.5">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-muted/40">
                              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium text-foreground leading-tight">{resource?.filename ?? 'Resource'}</p>
                              <p className="truncate text-xs text-muted-foreground">{resource?.topic ?? getResourceDisplayStatus(resource)}</p>
                            </div>
                          </div>
                        );
                      })}
                      {resourceItems.length > 5 && (
                        <p className="text-xs text-muted-foreground">+{resourceItems.length - 5} more</p>
                      )}
                      <button
                        onClick={() => setTab('resources')}
                        className="mt-1 w-full rounded-[14px] border border-border/60 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-gold/20 hover:text-foreground"
                      >
                        View all materials
                      </button>
                    </div>
                  ) : (
                    <div className="py-3 text-center">
                      <p className="text-xs text-muted-foreground">No resources yet.</p>
                      <button onClick={() => setTab('resources')} className="mt-2 text-xs font-medium text-gold hover:text-gold/80 transition-colors">
                        Upload material →
                      </button>
                    </div>
                  )}
                </div>

                {/* Mastery insight */}
                {(avgMastery > 0 || weakConcepts.length > 0) && (
                  <div className="rounded-[24px] border border-border/70 bg-card/80 p-4">
                    <div className="mb-2 flex items-center gap-2">
                      <BarChart3 className="h-3.5 w-3.5 text-gold" />
                      <h3 className="font-ui text-sm font-semibold text-foreground">Mastery Insight</h3>
                    </div>
                    <p className="text-sm text-foreground reading-copy">
                      {weakConcepts.length > 0
                        ? <><span className="font-medium">{weakConcepts.length} weak concept{weakConcepts.length !== 1 ? 's' : ''}</span> flagged{avgMastery > 0 ? <>. Mastery: <span className="font-medium text-gold">{avgMastery}%</span></> : '.'}</>  
                        : <>Current mastery: <span className="font-medium text-gold">{avgMastery}%</span>.</>}
                    </p>
                    <button
                      onClick={() => setTab('progress')}
                      className="mt-2.5 text-[11px] font-medium uppercase tracking-[0.10em] text-muted-foreground transition-colors hover:text-foreground"
                    >
                      View details →
                    </button>
                  </div>
                )}

                {/* Stats */}
                {sessions.length > 0 && (
                  <div className="grid grid-cols-2 gap-2.5">
                    <div className="rounded-[18px] border border-border/60 bg-card/70 p-3 text-center">
                      <p className="section-kicker text-[9px] text-muted-foreground">Sessions</p>
                      <p className="mt-1 font-reading text-2xl font-semibold text-foreground">{sessions.length}</p>
                    </div>
                    <div className="rounded-[18px] border border-border/60 bg-card/70 p-3 text-center">
                      <p className="section-kicker text-[9px] text-muted-foreground">Mastery</p>
                      <p className="mt-1 font-reading text-2xl font-semibold text-foreground">{avgMastery}%</p>
                    </div>
                  </div>
                )}

              </div>
            </div>
          </div>
        )}

        {activeTab === 'resources' && <ResourcesTab notebookId={notebookId} />}
        {activeTab === 'sessions' && <SessionsTab notebookId={notebookId} />}
        {activeTab === 'notes' && (
          <div className="px-6 lg:px-8 py-6 animate-tab-enter">
            <div className="max-w-5xl space-y-4">
              <div className="surface-scholarly rounded-[28px] border border-border/70 px-5 py-5 md:px-6 md:py-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="section-kicker text-[11px] text-gold">Notebook memory</p>
                    <h2 className="font-reading text-2xl text-foreground">Personal notes</h2>
                    <p className="mt-2 max-w-2xl text-sm text-muted-foreground reading-copy">
                      These notes are saved on the notebook itself, so they persist across reloads and remain available from the notebook page.
                    </p>
                  </div>
                  <button
                    onClick={() => navigate(`/notebooks/${notebookId}/study`)}
                    className="font-ui inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors"
                  >
                    <Sparkles className="w-3.5 h-3.5" /> Open in study workspace
                  </button>
                </div>

                <div className="mt-4 flex flex-wrap gap-2 text-[10px] font-ui uppercase tracking-[0.12em] text-muted-foreground">
                  <span className="rounded-full border border-border bg-card/80 px-2.5 py-1">{personalNotes.wordCount} words</span>
                  <span className="rounded-full border border-border bg-card/80 px-2.5 py-1">{personalNotes.captureCount} captured snippets</span>
                  <span className="rounded-full border border-border bg-card/80 px-2.5 py-1">{personalNotes.manualSaveCount} manual saves</span>
                  {personalNotes.updatedAt ? (
                    <span className="rounded-full border border-border bg-card/80 px-2.5 py-1">
                      Updated {new Date(personalNotes.updatedAt).toLocaleString()}
                    </span>
                  ) : null}
                </div>
              </div>

              <div className="rounded-[28px] border border-border/70 bg-card/80 px-5 py-5 md:px-6 md:py-6">
                {hasPersonalNotes ? (
                  <RichTutorContent content={personalNotes.markdown} />
                ) : (
                  <div className="flex min-h-[220px] flex-col items-center justify-center rounded-[22px] border border-dashed border-border/70 bg-background/60 px-6 text-center">
                    <StickyNote className="h-8 w-8 text-muted-foreground/30" />
                    <p className="mt-4 font-reading text-xl text-foreground">No saved notes yet</p>
                    <p className="mt-2 max-w-xl text-sm text-muted-foreground reading-copy">
                      Capture phrases from tutor responses or artifacts in the study workspace and they will appear here automatically.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
        {activeTab === 'progress' && <ProgressTab notebookId={notebookId} />}
      </div>
    </div>
  );
}
