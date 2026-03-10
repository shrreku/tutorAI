import { useCallback, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Plus, Trash2, Loader2, Upload, FileText,
  CheckCircle2, AlertCircle, Clock, Coins, ShieldCheck,
  X, Upload as CloudUpload, Link2,
} from 'lucide-react';
import { getApiErrorMessage } from '../api/client';
import {
  useNotebook, useNotebookResources, useResources,
  useAttachNotebookResource, useDetachNotebookResource,
  useUserSettings, useUploadResource, useIngestionStatus,
} from '../api/hooks';
import type { IngestionBillingStatus, IngestionAsyncByokStatus } from '../types/api';

function formatCredits(n: number) { return n.toLocaleString(); }

function ResourceStatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { icon: typeof CheckCircle2; cls: string; label: string }> = {
    ingested: { icon: CheckCircle2, cls: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', label: 'Ready' },
    processing: { icon: Clock, cls: 'bg-gold/10 text-gold border-gold/20 animate-pulse-gold', label: 'Processing' },
    failed: { icon: AlertCircle, cls: 'bg-red-500/10 text-red-400 border-red-500/20', label: 'Failed' },
  };
  const c = cfg[status] ?? { icon: Clock, cls: 'bg-muted text-muted-foreground border-border', label: status };
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium border ${c.cls}`}>
      <Icon className="w-3 h-3" /> {c.label}
    </span>
  );
}

function IngestionTracker({ jobId, billing, asyncByok }: {
  jobId: string; billing?: IngestionBillingStatus | null; asyncByok?: IngestionAsyncByokStatus | null;
}) {
  const { data: status } = useIngestionStatus(jobId);
  const isActive = status && status.status !== 'completed' && status.status !== 'failed';
  const liveBilling = status?.billing ?? billing;
  const liveAsyncByok = status?.async_byok ?? asyncByok;

  return (
    <div className="rounded-lg border border-gold/15 bg-gold/[0.04] p-3 space-y-2">
      <div className="flex items-center gap-2">
        {isActive ? <Loader2 className="w-3.5 h-3.5 text-gold animate-spin" />
          : status?.status === 'completed' ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          : status?.status === 'failed' ? <AlertCircle className="w-3.5 h-3.5 text-red-400" />
          : <Clock className="w-3.5 h-3.5 text-gold" />}
        <span className="text-xs font-medium text-foreground capitalize">{status?.status ?? 'queued'}</span>
        {status?.current_stage && <span className="text-[11px] text-muted-foreground">· {status.current_stage}</span>}
        {status?.progress_percent != null && status.progress_percent > 0 && (
          <span className="text-[11px] text-muted-foreground ml-auto">{status.progress_percent}%</span>
        )}
      </div>
      {isActive && (
        <div className="h-1 rounded-full bg-border overflow-hidden">
          <div className="h-full rounded-full bg-gradient-to-r from-gold to-amber-400 transition-all duration-500"
            style={{ width: `${Math.max(status?.progress_percent ?? 5, 5)}%` }} />
        </div>
      )}
      {liveBilling && liveBilling.uses_platform_credits && (
        <div className="flex items-center gap-4 text-[11px] text-muted-foreground pt-1 flex-wrap">
          <span className="inline-flex items-center gap-1"><Coins className="w-3 h-3 text-gold" /> Est. {formatCredits(liveBilling.estimated_credits)} credits</span>
          {liveBilling.reserved_credits > 0 && <span>Reserved: {formatCredits(liveBilling.reserved_credits)}</span>}
          {liveBilling.actual_credits != null && <span className="text-emerald-400">Charged: {formatCredits(liveBilling.actual_credits)}</span>}
          <span className="capitalize ml-auto text-[10px] px-1.5 py-0.5 rounded bg-muted">{liveBilling.status}</span>
        </div>
      )}
      {liveAsyncByok?.enabled && (
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <ShieldCheck className="w-3 h-3 text-gold" />
          <span>BYOK escrow active{liveAsyncByok.expires_at ? ` until ${new Date(liveAsyncByok.expires_at).toLocaleTimeString()}` : ''}</span>
        </div>
      )}
      {status?.error_message && <p className="text-[11px] text-red-400 mt-1">{status.error_message}</p>}
    </div>
  );
}

function getFileExtColor(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase();
  return ({ pdf: 'text-red-400', docx: 'text-blue-400', pptx: 'text-orange-400', md: 'text-emerald-400', html: 'text-purple-400', txt: 'text-muted-foreground', csv: 'text-teal-400' } as Record<string, string>)[ext ?? ''] ?? 'text-muted-foreground';
}

export default function NotebookResourcesPage() {
  const navigate = useNavigate();
  const { notebookId = '' } = useParams<{ notebookId: string }>();
  const { data: notebook } = useNotebook(notebookId);
  const { data: notebookResources, isLoading } = useNotebookResources(notebookId);
  const { data: resources } = useResources();
  const { data: userSettings } = useUserSettings();
  const attach = useAttachNotebookResource(notebookId);
  const detach = useDetachNotebookResource(notebookId);
  const uploadResource = useUploadResource();

  const [selectedResourceId, setSelectedResourceId] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [topic, setTopic] = useState('');
  const [useAsyncByok, setUseAsyncByok] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [confirmDetach, setConfirmDetach] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [lastBilling, setLastBilling] = useState<IngestionBillingStatus | null>(null);
  const [lastAsyncByok, setLastAsyncByok] = useState<IngestionAsyncByokStatus | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const hasLocalByok = typeof window !== 'undefined' && Boolean(window.localStorage.getItem('byok_api_key'));
  const asyncByokAvailable = Boolean(userSettings?.async_byok_escrow_enabled && hasLocalByok);

  const linked = useMemo(() => notebookResources?.items ?? [], [notebookResources?.items]);
  const linkedIds = useMemo(() => new Set(linked.map((item) => item.resource_id)), [linked]);
  const available = (resources?.items ?? []).filter((r) => !linkedIds.has(r.id));
  const resourceById = new Map((resources?.items ?? []).map((r) => [r.id, r]));

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true); }, []);
  const handleDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); }, []);
  const handleDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); const f = e.dataTransfer.files?.[0]; if (f) setSelectedFile(f); }, []);

  const handleUpload = async () => {
    if (!selectedFile) return;
    setErrorMessage(null); setFeedbackMessage(null); setActiveJobId(null);
    const formData = new FormData();
    formData.append('file', selectedFile);
    if (topic.trim()) formData.append('topic', topic.trim());
    if (asyncByokAvailable && useAsyncByok) formData.append('use_async_byok', 'true');
    try {
      const upload = await uploadResource.mutateAsync(formData);
      await attach.mutateAsync({ resource_id: upload.resource_id });
      setSelectedFile(null); setTopic(''); setUseAsyncByok(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
      setActiveJobId(upload.job_id);
      setLastBilling(upload.billing ?? null);
      setLastAsyncByok(upload.async_byok ?? null);
      const rc = upload.billing?.reserved_credits ?? 0;
      setFeedbackMessage(rc > 0 ? `Uploaded and attached. ${formatCredits(rc)} credits reserved for processing.` : 'Uploaded and attached. Processing continues in the background.');
    } catch (error) {
      setErrorMessage(getApiErrorMessage(error, 'Upload failed. Check file type and try again.'));
    }
  };

  const handleAttach = async () => {
    if (!selectedResourceId) return;
    setErrorMessage(null); setFeedbackMessage(null);
    try {
      await attach.mutateAsync({ resource_id: selectedResourceId });
      const r = resourceById.get(selectedResourceId);
      setSelectedResourceId('');
      setFeedbackMessage(`Attached "${r?.filename ?? 'resource'}" to this notebook.`);
    } catch (error) { setErrorMessage(getApiErrorMessage(error, 'Failed to attach resource.')); }
  };

  const handleDetach = async (resourceId: string) => {
    try { await detach.mutateAsync(resourceId); setConfirmDetach(null); setFeedbackMessage('Resource detached.'); }
    catch (error) { setErrorMessage(getApiErrorMessage(error, 'Failed to detach.')); }
  };

  return (
    <div className="h-full flex flex-col overflow-auto">
      <div className="px-8 pt-8 pb-2">
        <button onClick={() => navigate(`/notebooks/${notebookId}`)} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-5 transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to notebook
        </button>
        <div className="flex items-center gap-2 mb-2">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">Resources</span>
        </div>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground mb-1">
          {notebook?.title || 'Notebook'} <span className="italic text-gold">· Resources</span>
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl mb-6">Upload study material or attach files from your library. Processing runs in the background and credit usage is tracked per upload.</p>
      </div>

      <div className="flex-1 px-8 pb-8">
        {(feedbackMessage || errorMessage) && (
          <div className={`mb-5 max-w-5xl rounded-xl border px-4 py-3 text-sm flex items-start gap-3 animate-fade-up ${errorMessage ? 'border-red-500/20 bg-red-500/[0.06] text-red-300' : 'border-gold/20 bg-gold/[0.06] text-gold'}`}>
            {errorMessage ? <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" /> : <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />}
            <div className="flex-1">{errorMessage || feedbackMessage}</div>
            <button onClick={() => { setErrorMessage(null); setFeedbackMessage(null); }} className="shrink-0 p-0.5 rounded hover:bg-white/[0.06]"><X className="w-3.5 h-3.5" /></button>
          </div>
        )}

        {activeJobId && (
          <div className="mb-5 max-w-5xl animate-fade-up">
            <IngestionTracker jobId={activeJobId} billing={lastBilling} asyncByok={lastAsyncByok} />
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-5 mb-8 max-w-5xl">
          <div className="lg:col-span-3 rounded-xl border border-border bg-card overflow-hidden animate-fade-up">
            <div className="px-5 py-4 border-b border-border/50 flex items-center gap-2">
              <CloudUpload className="w-4 h-4 text-gold" />
              <h2 className="text-sm font-semibold text-foreground">Upload new resource</h2>
            </div>
            <div className="p-5 space-y-4">
              <div onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} onClick={() => fileInputRef.current?.click()}
                className={`relative cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-all duration-200 ${isDragging ? 'border-gold bg-gold/[0.06] scale-[1.01]' : selectedFile ? 'border-emerald-500/30 bg-emerald-500/[0.04]' : 'border-border/60 bg-background/30 hover:border-gold/30 hover:bg-gold/[0.02]'}`}>
                <input ref={fileInputRef} type="file" accept=".pdf,.docx,.pptx,.md,.html,.txt,.csv" onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)} className="hidden" />
                {selectedFile ? (
                  <div className="flex items-center justify-center gap-3">
                    <FileText className={`w-8 h-8 ${getFileExtColor(selectedFile.name)}`} />
                    <div className="text-left">
                      <p className="text-sm font-medium text-foreground">{selectedFile.name}</p>
                      <p className="text-xs text-muted-foreground">{(selectedFile.size / 1024).toFixed(1)} KB · Click or drop to replace</p>
                    </div>
                  </div>
                ) : (
                  <>
                    <Upload className="w-8 h-8 mx-auto text-muted-foreground/50 mb-3" />
                    <p className="text-sm text-muted-foreground mb-1">{isDragging ? 'Drop file here' : 'Click or drag a file to upload'}</p>
                    <p className="text-xs text-muted-foreground/60">PDF, DOCX, PPTX, Markdown, HTML, TXT, CSV</p>
                  </>
                )}
              </div>

              <input type="text" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Topic label (optional) — helps organize your material"
                className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:border-gold/30 focus:ring-1 focus:ring-gold/20" />

              {userSettings?.async_byok_escrow_enabled && (
                <label className={`flex items-start gap-3 rounded-lg border px-3.5 py-3 text-sm cursor-pointer transition-all ${useAsyncByok ? 'border-gold/30 bg-gold/[0.06]' : 'border-border/50 bg-background/30'} ${!asyncByokAvailable ? 'opacity-50 cursor-not-allowed' : ''}`}>
                  <input type="checkbox" checked={useAsyncByok} onChange={(e) => setUseAsyncByok(e.target.checked)} disabled={!asyncByokAvailable} className="mt-0.5 h-4 w-4 rounded border-border accent-[hsl(var(--gold))]" />
                  <div>
                    <p className="font-medium text-foreground text-sm">Use my BYOK for background processing</p>
                    <p className="text-xs text-muted-foreground mt-0.5">Creates encrypted server-side escrow for up to {userSettings.async_byok_escrow_ttl_minutes} min.{!asyncByokAvailable && ' Save a BYOK key in Settings first.'}</p>
                  </div>
                </label>
              )}

              <div className="flex items-center gap-3">
                <button onClick={handleUpload} disabled={!selectedFile || uploadResource.isPending || attach.isPending}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                  {uploadResource.isPending || attach.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                  Upload & attach
                </button>
                <p className="text-[11px] text-muted-foreground">Uploads use platform infrastructure{userSettings?.async_byok_escrow_enabled ? ' unless BYOK escrow is enabled' : ''}.</p>
              </div>
            </div>
          </div>

          <div className="lg:col-span-2 rounded-xl border border-border bg-card overflow-hidden animate-fade-up" style={{ animationDelay: '0.05s' }}>
            <div className="px-5 py-4 border-b border-border/50 flex items-center gap-2">
              <Link2 className="w-4 h-4 text-gold" />
              <h2 className="text-sm font-semibold text-foreground">Attach from library</h2>
            </div>
            <div className="p-5 space-y-4">
              <p className="text-xs text-muted-foreground">Previously uploaded resources can be linked to multiple notebooks.</p>
              <select value={selectedResourceId} onChange={(e) => setSelectedResourceId(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:border-gold/30 focus:ring-1 focus:ring-gold/20">
                <option value="">Select a resource…</option>
                {available.map((r) => <option key={r.id} value={r.id}>{r.filename}{r.status === 'processing' ? ' (processing…)' : ''}</option>)}
              </select>
              <button onClick={handleAttach} disabled={!selectedResourceId || attach.isPending}
                className="w-full inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 transition-colors disabled:opacity-50">
                {attach.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Attach resource
              </button>
              {available.length === 0 && <p className="text-xs text-muted-foreground/60 text-center py-2">All library resources are already attached.</p>}
            </div>
          </div>
        </div>

        <div className="max-w-5xl animate-fade-up" style={{ animationDelay: '0.1s' }}>
          <h2 className="font-display text-xl font-semibold text-foreground mb-4">
            Linked resources <span className="text-sm font-body font-normal text-muted-foreground ml-2">{linked.length} file{linked.length !== 1 ? 's' : ''}</span>
          </h2>
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center"><Loader2 className="w-4 h-4 animate-spin" /> Loading resources…</div>
          ) : linked.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/60 bg-card/30 py-12 text-center">
              <FileText className="w-10 h-10 mx-auto text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground mb-1">No resources attached yet</p>
              <p className="text-xs text-muted-foreground/60">Upload a file or attach one from your library above.</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {linked.map((entry, i) => {
                const r = resourceById.get(entry.resource_id);
                return (
                  <div key={entry.id} className="group rounded-xl border border-border bg-card p-4 transition-all hover:border-gold/15 hover:shadow-md hover:shadow-gold/5 animate-fade-up" style={{ animationDelay: `${0.12 + i * 0.03}s` }}>
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 shrink-0"><FileText className={`w-5 h-5 ${r ? getFileExtColor(r.filename) : 'text-muted-foreground'}`} /></div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{r?.filename ?? 'Unknown file'}</p>
                        {r?.topic && <p className="text-xs text-muted-foreground truncate mt-0.5">{r.topic}</p>}
                        <div className="mt-2 flex items-center gap-2 flex-wrap">
                          <ResourceStatusBadge status={r?.status ?? 'processing'} />
                          <span className="text-[10px] text-muted-foreground/60 capitalize">{entry.role}</span>
                          {r?.capabilities?.study_ready && <span className="text-[10px] text-emerald-400/70">study-ready</span>}
                        </div>
                      </div>
                      <div className="shrink-0">
                        {confirmDetach === entry.resource_id ? (
                          <div className="flex items-center gap-1">
                            <button onClick={() => handleDetach(entry.resource_id)} className="text-[10px] px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors">Confirm</button>
                            <button onClick={() => setConfirmDetach(null)} className="text-[10px] px-2 py-1 rounded bg-muted text-muted-foreground hover:text-foreground transition-colors">Cancel</button>
                          </div>
                        ) : (
                          <button onClick={() => setConfirmDetach(entry.resource_id)} className="p-1.5 rounded-md text-muted-foreground/40 opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition-all" title="Detach resource">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
