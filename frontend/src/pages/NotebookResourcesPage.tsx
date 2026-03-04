import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Plus, Trash2, Loader2 } from 'lucide-react';
import {
  useNotebook,
  useNotebookResources,
  useResources,
  useAttachNotebookResource,
  useDetachNotebookResource,
} from '../api/hooks';

export default function NotebookResourcesPage() {
  const navigate = useNavigate();
  const { notebookId = '' } = useParams<{ notebookId: string }>();

  const { data: notebook } = useNotebook(notebookId);
  const { data: notebookResources, isLoading } = useNotebookResources(notebookId);
  const { data: resources } = useResources();
  const attach = useAttachNotebookResource(notebookId);
  const detach = useDetachNotebookResource(notebookId);

  const [selectedResourceId, setSelectedResourceId] = useState('');

  const linked = notebookResources?.items ?? [];
  const linkedIds = new Set(linked.map((item) => item.resource_id));
  const available = (resources?.items ?? []).filter((resource) => !linkedIds.has(resource.id));

  const resourceNameById = new Map((resources?.items ?? []).map((resource) => [resource.id, resource.filename]));

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
          {notebook?.title || 'Notebook'} · Resources
        </h1>
        <p className="text-sm text-muted-foreground">Manage which resources are active in this notebook.</p>
      </div>

      <div className="rounded-xl border border-border bg-card p-5 mb-5 max-w-2xl">
        <div className="flex gap-2">
          <select
            value={selectedResourceId}
            onChange={(e) => setSelectedResourceId(e.target.value)}
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm"
          >
            <option value="">Select resource to attach</option>
            {available.map((resource) => (
              <option key={resource.id} value={resource.id}>
                {resource.filename}
              </option>
            ))}
          </select>
          <button
            onClick={() => attach.mutate({ resource_id: selectedResourceId })}
            disabled={!selectedResourceId || attach.isPending}
            className="px-3 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium disabled:opacity-50 flex items-center gap-2"
          >
            {attach.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Attach
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading resources...
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {linked.map((entry) => (
            <div key={entry.id} className="rounded-xl border border-border bg-card p-4">
              <p className="text-sm font-medium text-card-foreground truncate">
                {resourceNameById.get(entry.resource_id) || entry.resource_id}
              </p>
              <p className="text-xs text-muted-foreground mt-1">role: {entry.role}</p>
              <p className="text-xs text-muted-foreground">active: {entry.is_active ? 'yes' : 'no'}</p>
              <button
                onClick={() => detach.mutate(entry.resource_id)}
                className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium text-red-400 hover:bg-red-400/10"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Detach
              </button>
            </div>
          ))}
          {linked.length === 0 && (
            <div className="text-sm text-muted-foreground">No resources attached yet.</div>
          )}
        </div>
      )}
    </div>
  );
}
