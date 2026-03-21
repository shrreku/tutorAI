import { useMemo } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Loader2, Sparkles, BarChart3, Layers,
  MessageSquare, Calendar, LayoutDashboard, AlertTriangle,
  FileText, StickyNote,
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

        <div className="surface-scholarly rounded-[30px] border border-border/70 px-5 py-5 md:px-6 md:py-6">
          <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="section-kicker text-[11px] text-gold mb-2">Course notebook</p>
            <h1 className="editorial-title text-3xl md:text-5xl text-foreground truncate leading-tight">{notebook.title}</h1>
            <div className="flex items-center gap-3 mt-2">
              {notebook.goal && <p className="reading-copy text-base text-muted-foreground truncate max-w-2xl">{notebook.goal}</p>}
              {notebook.target_date && (
                <span className="data-chip inline-flex items-center gap-1 text-[10px] uppercase text-muted-foreground shrink-0">
                  <Calendar className="w-2.5 h-2.5" /> {new Date(notebook.target_date).toLocaleDateString()}
                </span>
              )}
            </div>
          </div>

          {/* Compact inline stats + study button */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="hidden md:flex items-center gap-3 text-[11px] text-muted-foreground font-ui uppercase tracking-[0.14em]">
              {resourceItems.length > 0 && (
                <button onClick={() => setTab('resources')} className="inline-flex items-center gap-1.5 hover:text-foreground transition-colors">
                  <FileText className="w-3 h-3" />
                  <span>{resourceItems.length} resource{resourceItems.length !== 1 ? 's' : ''}</span>
                </button>
              )}
              {masteryValues.length > 0 && (
                <button onClick={() => setTab('progress')} className="inline-flex items-center gap-1.5 hover:text-foreground transition-colors">
                  <div className="relative w-4 h-4">
                    <svg viewBox="0 0 36 36" className="w-4 h-4 -rotate-90">
                      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        fill="none" stroke="hsl(var(--border))" strokeWidth="4" />
                      <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                        fill="none" stroke="hsl(var(--gold))" strokeWidth="4" strokeLinecap="round"
                        strokeDasharray={`${avgMastery}, 100`} />
                    </svg>
                  </div>
                  <span>{avgMastery}% mastery</span>
                </button>
              )}
              {weakConcepts.length > 0 && (
                <button onClick={() => setTab('progress')} className="inline-flex items-center gap-1 text-red-400/80 hover:text-red-400 transition-colors">
                  <AlertTriangle className="w-3 h-3" />
                  <span>{weakConcepts.length} weak</span>
                </button>
              )}
            </div>
            <button
              onClick={() => navigate(`/notebooks/${notebookId}/study`)}
              className="font-ui inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5" /> Study
            </button>
          </div>
        </div>

          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <div className="rounded-[22px] border border-border/70 bg-card/80 px-4 py-4">
              <p className="section-kicker text-[10px] text-muted-foreground">Resources in scope</p>
              <p className="mt-2 font-reading text-2xl text-foreground">{resourceItems.length || 0}</p>
              <p className="mt-1 text-sm text-muted-foreground">Attached files that can contribute to notebook study and cross-resource sessions.</p>
            </div>
            <div className="rounded-[22px] border border-border/70 bg-card/80 px-4 py-4">
              <p className="section-kicker text-[10px] text-muted-foreground">Average mastery</p>
              <p className="mt-2 font-reading text-2xl text-foreground">{avgMastery}%</p>
              <p className="mt-1 text-sm text-muted-foreground">Use learn, practice, or revision depending on whether you need structure, recall, or reinforcement.</p>
            </div>
            <div className="rounded-[22px] border border-border/70 bg-card/80 px-4 py-4">
              <p className="section-kicker text-[10px] text-muted-foreground">Recommended mode</p>
              <p className="mt-2 font-reading text-2xl text-foreground capitalize">{recommendedMode}</p>
              <p className="mt-1 text-sm text-muted-foreground">{recommendedReason}</p>
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
          <div className="px-6 lg:px-8 py-6 animate-tab-enter">
            <div className="max-w-5xl">
              <SessionLaunchPanel
                resources={launchResources}
                recommendedMode={recommendedMode}
                recommendedReason={recommendedReason}
                pending={createNotebookSession.isPending}
                onLaunch={handleStartSession}
                title="Start the right session"
                subtitle="Study mode, scope, and learner input all shape the session plan. Build the session around what you actually need to understand, practise, or revise."
              />
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
