import { useNavigate } from 'react-router-dom';
import {
  Loader2, FileText, CheckCircle2, AlertCircle, Clock, FolderOpen,
} from 'lucide-react';
import { useResources } from '../api/hooks';
import { getLiveIngestionJob, getResourceDisplayStatus, isResourceDoubtReady, isResourceStudyReady } from '../lib/ingestion';

function getFileExtColor(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase();
  return ({ pdf: 'text-red-400', docx: 'text-blue-400', pptx: 'text-orange-400', md: 'text-emerald-400', html: 'text-purple-400', txt: 'text-muted-foreground', csv: 'text-teal-400' } as Record<string, string>)[ext ?? ''] ?? 'text-muted-foreground';
}

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { icon: typeof CheckCircle2; cls: string; label: string }> = {
    ready: { icon: CheckCircle2, cls: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', label: 'Ready' },
    ingested: { icon: CheckCircle2, cls: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', label: 'Ready' },
    processing: { icon: Clock, cls: 'bg-gold/10 text-gold border-gold/20 animate-pulse-gold', label: 'Processing' },
    failed: { icon: AlertCircle, cls: 'bg-red-500/10 text-red-400 border-red-500/20', label: 'Failed' },
  };
  const c = cfg[status] ?? { icon: Clock, cls: 'bg-muted text-muted-foreground border-border', label: status };
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium border ${c.cls}`}>
      <Icon className="w-3 h-3" /> {c.label}
    </span>
  );
}

export default function ResourcesLibraryPage() {
  const navigate = useNavigate();
  const { data: resources, isLoading } = useResources();
  const items = resources?.items ?? [];

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-5xl mx-auto px-8 py-8">
        <div className="flex items-center gap-2 mb-2">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">Library</span>
        </div>
        <div className="flex items-end justify-between gap-4 mb-1">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Resources</h1>
          <span className="text-sm text-muted-foreground">{items.length} file{items.length !== 1 ? 's' : ''} uploaded</span>
        </div>
        <p className="text-sm text-muted-foreground max-w-xl mb-8">
          All study materials you've uploaded, available to attach to any notebook. Upload new resources from within a notebook.
        </p>

        {isLoading ? (
          <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground py-16">
            <Loader2 className="w-5 h-5 animate-spin text-gold" /> Loading resources…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/60 bg-card/30 py-16 text-center animate-fade-up">
            <FolderOpen className="w-12 h-12 mx-auto text-muted-foreground/20 mb-3" />
            <p className="text-sm text-muted-foreground mb-2">No resources yet</p>
            <p className="text-xs text-muted-foreground/60 mb-4">Upload files from within a notebook to get started.</p>
            <button onClick={() => navigate('/notebooks')}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors">
              Go to Notebooks
            </button>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((resource, i) => (
              <div key={resource.id}
                className="group rounded-xl border border-border bg-card p-4 transition-all hover:border-gold/15 hover:shadow-md hover:shadow-gold/5 animate-fade-up"
                style={{ animationDelay: `${i * 0.03}s` }}>
                {(() => {
                  const liveJob = getLiveIngestionJob(resource);
                  return (
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 shrink-0">
                    <FileText className={`w-5 h-5 ${getFileExtColor(resource.filename)}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{resource.filename}</p>
                    {resource.topic && <p className="text-xs text-muted-foreground truncate mt-0.5">{resource.topic}</p>}
                    <div className="mt-2 flex items-center gap-2 flex-wrap">
                      <StatusBadge status={getResourceDisplayStatus(resource)} />
                      {isResourceStudyReady(resource) && (
                        <span className="text-[10px] text-emerald-400/70">study-ready</span>
                      )}
                      {!isResourceStudyReady(resource) && isResourceDoubtReady(resource) && (
                        <span className="text-[10px] text-sky-400/80">doubt-ready</span>
                      )}
                      {liveJob?.current_stage && (
                        <span className="text-[10px] text-muted-foreground/70">{liveJob.current_stage.split('_').join(' ')}</span>
                      )}
                    </div>
                    <p className="text-[10px] text-muted-foreground/50 mt-2">
                      {new Date(resource.uploaded_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                  );
                })()}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
