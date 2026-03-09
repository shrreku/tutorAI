import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Plus, Trash2, Loader2, Upload } from 'lucide-react';
import {
  useNotebook,
  useNotebookResources,
  useResources,
  useAttachNotebookResource,
  useDetachNotebookResource,
  useUploadResource,
} from '../api/hooks';

export default function NotebookResourcesPage() {
  const navigate = useNavigate();
  const { notebookId = '' } = useParams<{ notebookId: string }>();

  const { data: notebook } = useNotebook(notebookId);
  const { data: notebookResources, isLoading } = useNotebookResources(notebookId);
  const { data: resources } = useResources();
  const attach = useAttachNotebookResource(notebookId);
  const detach = useDetachNotebookResource(notebookId);
  const uploadResource = useUploadResource();

  const [selectedResourceId, setSelectedResourceId] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [topic, setTopic] = useState('');
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const linked = notebookResources?.items ?? [];
  const linkedIds = useMemo(() => new Set(linked.map((item) => item.resource_id)), [linked]);
  const available = (resources?.items ?? []).filter((resource) => !linkedIds.has(resource.id));

  const resourceById = new Map((resources?.items ?? []).map((resource) => [resource.id, resource]));

  const handleAttach = async () => {
    if (!selectedResourceId) return;

    setErrorMessage(null);
    setFeedbackMessage(null);

    try {
      await attach.mutateAsync({ resource_id: selectedResourceId });
      setSelectedResourceId('');
      setFeedbackMessage('Resource attached to this notebook.');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to attach resource.');
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setErrorMessage(null);
    setFeedbackMessage(null);

    const formData = new FormData();
    formData.append('file', selectedFile);
    if (topic.trim()) {
      formData.append('topic', topic.trim());
    }

    try {
      const upload = await uploadResource.mutateAsync(formData);
      await attach.mutateAsync({ resource_id: upload.resource_id });
      setSelectedFile(null);
      setTopic('');
      setFeedbackMessage('Upload accepted and attached to this notebook. Processing will continue in the background.');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to upload resource.');
    }
  };

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
        <p className="text-sm text-muted-foreground">Upload new material or attach existing library resources to this notebook.</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2 mb-5 max-w-5xl">
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-gold mb-4">
            <Upload className="w-4 h-4" />
            Upload new resource
          </div>
          <div className="space-y-3">
            <input
              type="file"
              accept=".pdf,.docx,.pptx,.md,.html,.txt,.csv"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
              className="block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-gold/10 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-gold"
            />
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Optional topic label"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
            <button
              onClick={handleUpload}
              disabled={!selectedFile || uploadResource.isPending || attach.isPending}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium disabled:opacity-50"
            >
              {uploadResource.isPending || attach.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              Upload and attach
            </button>
            <p className="text-xs text-muted-foreground">
              Accepted file types: PDF, DOCX, PPTX, Markdown, HTML, TXT, CSV.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-gold mb-4">
            <Plus className="w-4 h-4" />
            Attach from library
          </div>
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
              onClick={handleAttach}
              disabled={!selectedResourceId || attach.isPending}
              className="px-3 py-2 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium disabled:opacity-50 flex items-center gap-2"
            >
              {attach.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Attach
            </button>
          </div>
          <p className="text-xs text-muted-foreground mt-3">
            Use this when the file already exists in your resource library.
          </p>
        </div>
      </div>

      {(feedbackMessage || errorMessage) && (
        <div className={`mb-5 max-w-3xl rounded-xl border px-4 py-3 text-sm ${errorMessage ? 'border-red-500/20 bg-red-500/10 text-red-300' : 'border-gold/20 bg-gold/10 text-gold'}`}>
          {errorMessage || feedbackMessage}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading resources...
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {linked.map((entry) => (
            <div key={entry.id} className="rounded-xl border border-border bg-card p-4">
              <p className="text-sm font-medium text-card-foreground truncate">
                {resourceById.get(entry.resource_id)?.filename || entry.resource_id}
              </p>
              <p className="text-xs text-muted-foreground mt-1">status: {resourceById.get(entry.resource_id)?.status || 'unknown'}</p>
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
