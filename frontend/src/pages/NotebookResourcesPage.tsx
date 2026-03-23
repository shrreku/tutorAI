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
  useUserSettings, useUploadResource, useIngestionStatus, useRetryIngestion,
  useIngestionEstimate,
} from '../api/hooks';
import { formatCredits } from '../lib/credits';
import {
  getLiveIngestionJob,
  getResourceDisplayStatus,
  isResourceDoubtReady,
  isResourceStudyReady,
} from '../lib/ingestion';
import type {
  IngestionBillingStatus,
  IngestionAsyncByokStatus,
  IngestionCurriculumBillingStatus,
  IngestionEstimateResponse,
} from '../types/api';

function formatIngestionStage(stage?: string | null) {
  const labels: Record<string, string> = {
    worker_pickup: 'Queued',
    initializing_models: 'Initializing models',
    parse: 'Parsing document',
    chunk: 'Chunking document',
    embed: 'Embedding chunks',
    persist: 'Saving index',
    core_ready: 'Core index ready',
    curriculum_ontology: 'Extracting curriculum',
    curriculum_enrichment: 'Enriching chunks',
    curriculum_kb: 'Building knowledge base',
    curriculum_bundles: 'Preparing topic bundles',
    curriculum_finalize: 'Finalizing readiness',
    complete: 'Complete',
  };
  return labels[stage ?? ''] ?? (stage ? stage.split('_').join(' ') : null);
}

function ResourceStatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { icon: typeof CheckCircle2; cls: string; label: string }> = {
    ready: { icon: CheckCircle2, cls: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', label: 'Ready' },
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
  const liveCurriculumBilling: IngestionCurriculumBillingStatus | null | undefined = status?.curriculum_billing;
  const liveAsyncByok = status?.async_byok ?? asyncByok;
  const documentMetrics = status?.document_metrics;
  const capabilityProgress = status?.capability_progress;
  const stageLabel = formatIngestionStage(status?.current_stage);

  return (
    <div className="rounded-lg border border-gold/15 bg-gold/[0.04] p-3 space-y-2">
      <div className="flex items-center gap-2">
        {isActive ? <Loader2 className="w-3.5 h-3.5 text-gold animate-spin" />
          : status?.status === 'completed' ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          : status?.status === 'failed' ? <AlertCircle className="w-3.5 h-3.5 text-red-400" />
          : <Clock className="w-3.5 h-3.5 text-gold" />}
        <span className="text-xs font-medium text-foreground capitalize">{status?.status ?? 'queued'}</span>
        {stageLabel && <span className="text-[11px] text-muted-foreground">· {stageLabel}</span>}
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
          <span className="inline-flex items-center gap-1"><Coins className="w-3 h-3 text-gold" /> Upload est. {formatCredits(liveBilling.estimated_credits)} credits</span>
          {liveBilling.reserved_credits > 0 && <span>Upload reserved: {formatCredits(liveBilling.reserved_credits)}</span>}
          {liveBilling.actual_credits != null && <span className="text-emerald-400">Upload charged: {formatCredits(liveBilling.actual_credits)}</span>}
          <span className="capitalize ml-auto text-[10px] px-1.5 py-0.5 rounded bg-muted">{liveBilling.status}</span>
        </div>
      )}
      {liveCurriculumBilling && (
        <div className="flex items-center gap-4 text-[11px] text-muted-foreground flex-wrap">
          <span className="inline-flex items-center gap-1"><Coins className="w-3 h-3 text-gold" /> Curriculum est. {formatCredits(liveCurriculumBilling.estimated_credits_low)}–{formatCredits(liveCurriculumBilling.estimated_credits_high)} credits</span>
          {liveCurriculumBilling.reserved_credits > 0 && <span>Curriculum reserved: {formatCredits(liveCurriculumBilling.reserved_credits)}</span>}
          {liveCurriculumBilling.actual_credits != null && <span className="text-emerald-400">Curriculum charged: {formatCredits(liveCurriculumBilling.actual_credits)}</span>}
          <span className="capitalize text-[10px] px-1.5 py-0.5 rounded bg-muted">{liveCurriculumBilling.status.split('_').join(' ')}</span>
        </div>
      )}
      {documentMetrics && (documentMetrics.chunk_count_actual > 0 || documentMetrics.page_count_actual > 0) && (
        <div className="flex items-center gap-4 text-[11px] text-muted-foreground flex-wrap">
          {documentMetrics.page_count_actual > 0 && <span>{documentMetrics.page_count_actual} pages</span>}
          {documentMetrics.chunk_count_actual > 0 && <span>{documentMetrics.chunk_count_actual} chunks</span>}
          {documentMetrics.token_count_actual > 0 && <span>~{documentMetrics.token_count_actual.toLocaleString()} tokens</span>}
        </div>
      )}
      {capabilityProgress && (
        <div className="flex items-center gap-2 text-[11px] flex-wrap">
          {capabilityProgress.search_ready && <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-0.5 text-sky-300">search-ready</span>}
          {capabilityProgress.doubt_ready && <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-emerald-300">doubt-ready</span>}
          {capabilityProgress.learn_ready && <span className="rounded-full border border-gold/20 bg-gold/10 px-2 py-0.5 text-gold">learn-ready</span>}
        </div>
      )}
      {liveAsyncByok?.enabled && (
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <ShieldCheck className="w-3 h-3 text-gold" />
          <span>BYOK escrow active{liveAsyncByok.expires_at ? ` until ${new Date(liveAsyncByok.expires_at).toLocaleTimeString()}` : ''}</span>
        </div>
      )}
      {status?.error_stage && (
        <p className="text-[11px] text-muted-foreground">Failed at: {formatIngestionStage(status.error_stage)}</p>
      )}
      {status?.resume_hint && (
        <p className="text-[11px] text-gold">{status.resume_hint}</p>
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
  const retryIngestion = useRetryIngestion();
  const estimateIngestion = useIngestionEstimate();

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
  const [uploadEstimate, setUploadEstimate] = useState<IngestionEstimateResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const hasLocalByok = typeof window !== 'undefined' && Boolean(window.localStorage.getItem('byok_api_key'));
  const asyncByokAvailable = Boolean(userSettings?.async_byok_escrow_enabled && hasLocalByok);

  const linked = useMemo(() => notebookResources?.items ?? [], [notebookResources?.items]);
  const linkedIds = useMemo(() => new Set(linked.map((item) => item.resource_id)), [linked]);
  const available = (resources?.items ?? []).filter((r) => !linkedIds.has(r.id));
  const resourceById = useMemo(() => new Map((resources?.items ?? []).map((r) => [r.id, r])), [resources?.items]);
  const shouldShowDetailedEstimate = Boolean(
    selectedFile
      && uploadEstimate
      && (
        selectedFile.size >= 10 * 1024 * 1024
        || uploadEstimate.warnings.length > 0
        || uploadEstimate.chunk_count_estimate >= 150
      )
  );
  const trackerEntries = useMemo(() => {
    const entries: Array<{
      jobId: string;
      label: string;
      billing?: IngestionBillingStatus | null;
      asyncByok?: IngestionAsyncByokStatus | null;
    }> = [];
    const seen = new Set<string>();

    linked.forEach((entry) => {
      const resource = resourceById.get(entry.resource_id);
      const liveJob = getLiveIngestionJob(resource);
      if (!liveJob || seen.has(liveJob.job_id)) return;
      seen.add(liveJob.job_id);
      entries.push({
        jobId: liveJob.job_id,
        label: resource?.filename ?? 'Processing resource',
        billing: liveJob.billing ?? null,
        asyncByok: liveJob.async_byok ?? null,
      });
    });

    if (activeJobId && !seen.has(activeJobId)) {
      entries.unshift({
        jobId: activeJobId,
        label: selectedFile?.name ?? 'Latest upload',
        billing: lastBilling,
        asyncByok: lastAsyncByok,
      });
    }

    return entries;
  }, [activeJobId, lastAsyncByok, lastBilling, linked, resourceById, selectedFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true); }, []);
  const handleDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); }, []);
  const handleDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); const f = e.dataTransfer.files?.[0]; if (f) setSelectedFile(f); }, []);

  // CM-014: Auto-estimate credits when a file is selected
  const fetchEstimate = useCallback(async (file: File) => {
    try {
      const result = await estimateIngestion.mutateAsync({
        filename: file.name,
        file_size_bytes: file.size,
      });
      setUploadEstimate(result);
    } catch {
      setUploadEstimate(null);
    }
  }, [estimateIngestion]);

  // Trigger estimate when file changes
  const prevFileRef = useRef<File | null>(null);
  if (selectedFile !== prevFileRef.current) {
    prevFileRef.current = selectedFile;
    if (selectedFile) {
      void fetchEstimate(selectedFile);
    } else {
      setUploadEstimate(null);
    }
  }

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
      setFeedbackMessage(
        rc > 0
          ? `Uploaded and attached. ${formatCredits(rc)} credits reserved now for upload processing; curriculum preparation is billed separately if it runs.`
          : 'Uploaded and attached. Processing continues in the background; curriculum preparation is billed separately if it runs.',
      );
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

  const handleRetry = async (resourceId: string, filename: string) => {
    setErrorMessage(null);
    setFeedbackMessage(null);
    try {
      const retried = await retryIngestion.mutateAsync(resourceId);
      setActiveJobId(retried.job_id);
      setLastBilling(retried.billing ?? null);
      setLastAsyncByok(retried.async_byok ?? null);
      setFeedbackMessage(
        retried.resumable
          ? `Resumed ingestion for "${filename}" from the last safe checkpoint.`
          : `Retried ingestion for "${filename}". Processing restarted from the beginning.`,
      );
    } catch (error) {
      setErrorMessage(getApiErrorMessage(error, 'Failed to retry ingestion.'));
    }
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

        {trackerEntries.length > 0 && (
          <div className="mb-5 max-w-5xl animate-fade-up">
            <div className="space-y-3">
              {trackerEntries.map((tracker) => (
                <div key={tracker.jobId} className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">{tracker.label}</p>
                  <IngestionTracker jobId={tracker.jobId} billing={tracker.billing} asyncByok={tracker.asyncByok} />
                </div>
              ))}
            </div>
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

              {/* CM-014: Pre-upload credit estimate */}
              {estimateIngestion.isPending && selectedFile && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-gold" />
                  <span>Checking credit usage…</span>
                </div>
              )}
              {uploadEstimate && selectedFile && !estimateIngestion.isPending && (
                <div className="rounded-lg border border-gold/15 bg-gold/[0.04] px-4 py-3 space-y-1.5">
                  <div className="flex items-center gap-2 text-xs font-medium text-foreground">
                    <Coins className="w-3.5 h-3.5 text-gold" />
                    <span>{shouldShowDetailedEstimate ? 'Estimated processing credits' : 'Processing credits'}</span>
                    {shouldShowDetailedEstimate && (
                      <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${uploadEstimate.estimate_confidence === 'high' ? 'bg-emerald-500/10 text-emerald-400' : uploadEstimate.estimate_confidence === 'medium' ? 'bg-gold/10 text-gold' : 'bg-orange-500/10 text-orange-400'}`}>
                        {uploadEstimate.estimate_confidence} confidence
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 text-[11px] text-muted-foreground flex-wrap">
                    <span>Reserve now: {formatCredits(uploadEstimate.core_upload_credits)} credits</span>
                  </div>
                  {shouldShowDetailedEstimate ? (
                    <>
                      <div className="flex items-center gap-4 text-[11px] text-muted-foreground flex-wrap">
                        <span>Curriculum later: {formatCredits(uploadEstimate.curriculum_credits_low)}–{formatCredits(uploadEstimate.curriculum_credits_high)} credits</span>
                      </div>
                      <div className="flex items-center gap-4 text-[11px] text-muted-foreground flex-wrap">
                        <span>Total projected: {formatCredits(uploadEstimate.estimated_credits_low)}–{formatCredits(uploadEstimate.estimated_credits_high)} credits</span>
                        <span>~{uploadEstimate.chunk_count_estimate} chunks</span>
                      </div>
                      <div className="text-[11px] text-muted-foreground">Core upload is reserved immediately. Curriculum preparation is reserved only when that stage starts.</div>
                    </>
                  ) : (
                    <div className="text-[11px] text-muted-foreground">
                      Curriculum preparation is billed separately if and when it runs. Detailed estimates appear automatically for larger documents.
                    </div>
                  )}
                  {uploadEstimate.warnings.length > 0 && (
                    <div className="flex items-start gap-1.5 text-[11px] text-orange-400">
                      <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                      <span>{uploadEstimate.warnings.join('. ')}</span>
                    </div>
                  )}
                </div>
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
                {available.map((r) => <option key={r.id} value={r.id}>{r.filename}{getResourceDisplayStatus(r) === 'processing' ? ' (processing…)' : ''}</option>)}
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
                const liveJob = getLiveIngestionJob(r);
                const displayStatus = getResourceDisplayStatus(r);
                return (
                  <div key={entry.id} className="group rounded-xl border border-border bg-card p-4 transition-all hover:border-gold/15 animate-fade-up" style={{ animationDelay: `${0.12 + i * 0.03}s` }}>
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 shrink-0"><FileText className={`w-5 h-5 ${r ? getFileExtColor(r.filename) : 'text-muted-foreground'}`} /></div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{r?.filename ?? 'Unknown file'}</p>
                        {r?.topic && <p className="text-xs text-muted-foreground truncate mt-0.5">{r.topic}</p>}
                        <div className="mt-2 flex items-center gap-2 flex-wrap">
                          <ResourceStatusBadge status={displayStatus} />
                          <span className="text-[10px] text-muted-foreground/60 capitalize">{entry.role}</span>
                          {isResourceStudyReady(r) && <span className="text-[10px] text-emerald-400/70">study-ready</span>}
                          {!isResourceStudyReady(r) && isResourceDoubtReady(r) && <span className="text-[10px] text-sky-400/80">doubt-ready</span>}
                          {liveJob?.current_stage && <span className="text-[10px] text-muted-foreground/70">{formatIngestionStage(liveJob.current_stage)}</span>}
                          {r?.latest_job?.status === 'failed' && r.latest_job.resumable && <span className="text-[10px] text-gold">resumable</span>}
                        </div>
                        {r?.latest_job?.error_message && displayStatus === 'failed' && (
                          <p className="mt-2 text-[11px] text-red-400 line-clamp-3">{r.latest_job.error_message}</p>
                        )}
                        {r?.latest_job?.resume_hint && displayStatus === 'failed' && (
                          <p className="mt-1 text-[11px] text-gold line-clamp-2">{r.latest_job.resume_hint}</p>
                        )}
                      </div>
                      <div className="shrink-0">
                        {displayStatus === 'failed' ? (
                          <button
                            onClick={() => handleRetry(entry.resource_id, r?.filename ?? 'resource')}
                            disabled={retryIngestion.isPending}
                            className="text-[10px] px-2 py-1 rounded bg-gold/10 text-gold hover:bg-gold/20 transition-colors disabled:opacity-50"
                          >
                            {retryIngestion.isPending ? 'Retrying…' : (r?.latest_job?.resumable ? 'Resume' : 'Retry')}
                          </button>
                        ) : confirmDetach === entry.resource_id ? (
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
