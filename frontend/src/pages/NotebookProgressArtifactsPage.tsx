import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, BarChart3, Loader2, Wand2 } from 'lucide-react';
import { useNotebook, useNotebookProgress, useNotebookArtifacts, useGenerateNotebookArtifact } from '../api/hooks';

const ARTIFACT_TYPES = ['notes', 'flashcards', 'quiz', 'revision_plan'] as const;

export default function NotebookProgressArtifactsPage() {
  const navigate = useNavigate();
  const { notebookId = '' } = useParams<{ notebookId: string }>();

  const { data: notebook } = useNotebook(notebookId);
  const { data: progress, isLoading: progressLoading } = useNotebookProgress(notebookId);
  const { data: artifacts, isLoading: artifactsLoading } = useNotebookArtifacts(notebookId);
  const generateArtifact = useGenerateNotebookArtifact(notebookId);

  const [artifactType, setArtifactType] = useState<(typeof ARTIFACT_TYPES)[number]>('notes');

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <button
        onClick={() => navigate(`/notebooks/${notebookId}`)}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to notebook
      </button>

      <div className="mb-6">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground mb-1">
          {notebook?.title || 'Notebook'} · Progress & Artifacts
        </h1>
        <p className="text-sm text-muted-foreground">Track weak concepts and generate study outputs.</p>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <section className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 mb-4 text-gold text-sm font-medium">
            <BarChart3 className="w-4 h-4" />
            Progress Snapshot
          </div>

          {progressLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading progress...
            </div>
          ) : (
            <>
              <div className="space-y-1 text-sm mb-4">
                <p className="text-muted-foreground">Sessions: <span className="text-foreground">{progress?.sessions_count ?? 0}</span></p>
                <p className="text-muted-foreground">Completed: <span className="text-foreground">{progress?.completed_sessions_count ?? 0}</span></p>
                <p className="text-muted-foreground">Updated: <span className="text-foreground">{progress?.updated_at ? new Date(progress.updated_at).toLocaleString() : 'n/a'}</span></p>
              </div>

              <div>
                <h3 className="text-xs uppercase tracking-wide text-muted-foreground mb-2">Weak concepts</h3>
                <div className="flex flex-wrap gap-2">
                  {(progress?.weak_concepts_snapshot ?? []).length === 0 ? (
                    <span className="text-xs text-muted-foreground">No weak concepts currently.</span>
                  ) : (
                    (progress?.weak_concepts_snapshot ?? []).map((concept) => (
                      <span key={concept} className="px-2 py-1 rounded-md text-xs border border-gold/20 bg-gold/10 text-gold">
                        {concept}
                      </span>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 mb-4 text-gold text-sm font-medium">
            <Wand2 className="w-4 h-4" />
            Artifacts
          </div>

          <div className="flex gap-2 mb-4">
            <select
              value={artifactType}
              onChange={(e) => setArtifactType(e.target.value as (typeof ARTIFACT_TYPES)[number])}
              className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm"
            >
              {ARTIFACT_TYPES.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
            <button
              onClick={() => generateArtifact.mutate({ artifact_type: artifactType })}
              disabled={generateArtifact.isPending}
              className="px-3 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium disabled:opacity-50"
            >
              {generateArtifact.isPending ? 'Generating...' : 'Generate'}
            </button>
          </div>

          {artifactsLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading artifacts...
            </div>
          ) : (
            <div className="space-y-2 max-h-80 overflow-auto">
              {(artifacts?.items ?? []).map((artifact) => (
                <div key={artifact.id} className="p-3 rounded-lg border border-border/70">
                  <p className="text-sm font-medium text-foreground">{artifact.artifact_type}</p>
                  <p className="text-xs text-muted-foreground mt-1">{new Date(artifact.created_at).toLocaleString()}</p>
                  <pre className="mt-2 text-[11px] text-muted-foreground whitespace-pre-wrap break-words">
                    {JSON.stringify(artifact.payload_json, null, 2).slice(0, 300)}
                  </pre>
                </div>
              ))}
              {(artifacts?.items ?? []).length === 0 && (
                <div className="text-sm text-muted-foreground">No artifacts yet.</div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
