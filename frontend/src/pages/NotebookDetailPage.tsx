import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Loader2,
  Plus,
  Sparkles,
  BarChart3,
  Layers,
  MessageSquare,
  Wand2,
  Trash2,
} from 'lucide-react';
import {
  useNotebook,
  useNotebookResources,
  useNotebookSessions,
  useNotebookProgress,
  useNotebookArtifacts,
  useResources,
  useAttachNotebookResource,
  useDetachNotebookResource,
  useCreateNotebookSession,
  useGenerateNotebookArtifact,
} from '../api/hooks';

const MODES = ['learn', 'doubt', 'practice', 'revision'] as const;
const ARTIFACT_TYPES = ['notes', 'flashcards', 'quiz', 'revision_plan'] as const;

export default function NotebookDetailPage() {
  const navigate = useNavigate();
  const { notebookId = '' } = useParams<{ notebookId: string }>();

  const { data: notebook, isLoading: notebookLoading } = useNotebook(notebookId);
  const { data: notebookResources } = useNotebookResources(notebookId);
  const { data: notebookSessions } = useNotebookSessions(notebookId);
  const { data: progress } = useNotebookProgress(notebookId);
  const { data: artifacts } = useNotebookArtifacts(notebookId);
  const { data: allResources } = useResources();

  const attachResource = useAttachNotebookResource(notebookId);
  const detachResource = useDetachNotebookResource(notebookId);
  const createNotebookSession = useCreateNotebookSession(notebookId);
  const generateArtifact = useGenerateNotebookArtifact(notebookId);

  const [resourceToAttach, setResourceToAttach] = useState('');
  const [sessionMode, setSessionMode] = useState<(typeof MODES)[number]>('learn');
  const [artifactType, setArtifactType] = useState<(typeof ARTIFACT_TYPES)[number]>('notes');

  const linkedResourceIds = useMemo(
    () => new Set((notebookResources?.items ?? []).map((item) => item.resource_id)),
    [notebookResources?.items]
  );

  const availableResources = (allResources?.items ?? []).filter((resource) => !linkedResourceIds.has(resource.id));

  if (notebookLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 text-gold animate-spin" />
      </div>
    );
  }

  if (!notebook) {
    return (
      <div className="p-8 text-sm text-muted-foreground">
        Notebook not found.
      </div>
    );
  }

  const handleAttachResource = async () => {
    if (!resourceToAttach) return;
    await attachResource.mutateAsync({ resource_id: resourceToAttach });
    setResourceToAttach('');
  };

  const handleStartSession = async () => {
    const firstResource = notebookResources?.items?.[0]?.resource_id;
    if (!firstResource) return;

    const detail = await createNotebookSession.mutateAsync({
      resource_id: firstResource,
      mode: sessionMode,
    });

    navigate(`/notebooks/${notebookId}/study?sessionId=${detail.session.id}`);
  };

  const handleGenerateArtifact = async () => {
    await generateArtifact.mutateAsync({ artifact_type: artifactType });
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

      <div className="mb-8">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground mb-2">{notebook.title}</h1>
        <p className="text-sm text-muted-foreground max-w-2xl">{notebook.goal || 'No notebook goal set yet.'}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            onClick={() => navigate(`/notebooks/${notebookId}/study`)}
            className="px-3 py-1.5 rounded-md bg-gold text-primary-foreground text-xs font-medium"
          >
            Open Study Workspace
          </button>
          <button
            onClick={() => navigate(`/notebooks/${notebookId}/resources`)}
            className="px-3 py-1.5 rounded-md border border-border text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Resources Screen
          </button>
          <button
            onClick={() => navigate(`/notebooks/${notebookId}/sessions`)}
            className="px-3 py-1.5 rounded-md border border-border text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Sessions History
          </button>
          <button
            onClick={() => navigate(`/notebooks/${notebookId}/progress`)}
            className="px-3 py-1.5 rounded-md border border-border text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            Progress & Artifacts
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-5">
        <section className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 mb-4 text-gold text-sm font-medium">
            <Layers className="w-4 h-4" />
            Resources
          </div>
          <div className="space-y-2 mb-4 max-h-64 overflow-auto">
            {(notebookResources?.items ?? []).map((entry) => (
              <div key={entry.id} className="flex items-center justify-between gap-2 p-2 rounded-lg border border-border/70">
                <span className="text-xs text-foreground font-mono truncate">{entry.resource_id}</span>
                <button
                  onClick={() => detachResource.mutate(entry.resource_id)}
                  className="text-red-400 hover:text-red-300"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {(notebookResources?.items ?? []).length === 0 && (
              <p className="text-xs text-muted-foreground">No resources attached yet.</p>
            )}
          </div>

          <div className="space-y-2">
            <select
              value={resourceToAttach}
              onChange={(e) => setResourceToAttach(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="">Select resource to attach</option>
              {availableResources.map((resource) => (
                <option key={resource.id} value={resource.id}>
                  {resource.filename}
                </option>
              ))}
            </select>
            <button
              onClick={handleAttachResource}
              disabled={attachResource.isPending || !resourceToAttach}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium disabled:opacity-50"
            >
              {attachResource.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Attach Resource
            </button>
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 mb-4 text-gold text-sm font-medium">
            <MessageSquare className="w-4 h-4" />
            Sessions
          </div>

          <div className="space-y-2 mb-4 max-h-64 overflow-auto">
            {(notebookSessions?.items ?? []).map((entry) => (
              <button
                key={entry.id}
                onClick={() => navigate(`/notebooks/${notebookId}/study?sessionId=${entry.session_id}`)}
                className="w-full text-left p-2 rounded-lg border border-border/70 hover:border-gold/20"
              >
                <p className="text-xs text-foreground font-mono truncate">{entry.session_id}</p>
                <p className="text-[11px] text-muted-foreground mt-1">Mode: {entry.mode}</p>
              </button>
            ))}
            {(notebookSessions?.items ?? []).length === 0 && (
              <p className="text-xs text-muted-foreground">No sessions in this notebook yet.</p>
            )}
          </div>

          <div className="space-y-2">
            <select
              value={sessionMode}
              onChange={(e) => setSessionMode(e.target.value as (typeof MODES)[number])}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            >
              {MODES.map((mode) => (
                <option key={mode} value={mode}>{mode}</option>
              ))}
            </select>
            <button
              onClick={handleStartSession}
              disabled={createNotebookSession.isPending || (notebookResources?.items ?? []).length === 0}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium disabled:opacity-50"
            >
              {createNotebookSession.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              Start Notebook Session
            </button>
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 mb-4 text-gold text-sm font-medium">
            <BarChart3 className="w-4 h-4" />
            Progress & Artifacts
          </div>

          <div className="mb-4 text-xs text-muted-foreground space-y-1">
            <p>Sessions: {progress?.sessions_count ?? 0}</p>
            <p>Completed: {progress?.completed_sessions_count ?? 0}</p>
            <p>Weak concepts: {(progress?.weak_concepts_snapshot ?? []).slice(0, 3).join(', ') || 'None'}</p>
          </div>

          <div className="space-y-2 mb-4">
            <select
              value={artifactType}
              onChange={(e) => setArtifactType(e.target.value as (typeof ARTIFACT_TYPES)[number])}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            >
              {ARTIFACT_TYPES.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
            <button
              onClick={handleGenerateArtifact}
              disabled={generateArtifact.isPending}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium disabled:opacity-50"
            >
              {generateArtifact.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
              Generate Artifact
            </button>
          </div>

          <div className="space-y-2 max-h-48 overflow-auto">
            {(artifacts?.items ?? []).slice(0, 8).map((artifact) => (
              <div key={artifact.id} className="p-2 rounded-lg border border-border/70">
                <p className="text-xs text-foreground">{artifact.artifact_type}</p>
                <p className="text-[11px] text-muted-foreground mt-1">{new Date(artifact.created_at).toLocaleString()}</p>
              </div>
            ))}
            {(artifacts?.items ?? []).length === 0 && (
              <p className="text-xs text-muted-foreground">No artifacts generated yet.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
