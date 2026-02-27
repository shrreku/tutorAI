import { useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, FileText, CheckCircle, Clock, XCircle, AlertCircle, Loader2, Sparkles, Plus } from 'lucide-react';
import { useResources, useUploadResource } from '../api/hooks';

export default function ResourcesPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { data, isLoading, error } = useResources();
  const uploadMutation = useUploadResource();

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      try {
        await uploadMutation.mutateAsync({ file });
      } catch (err) {
        console.error('Upload failed:', err);
      }
    }
  };

  const statusConfig: Record<string, { icon: typeof CheckCircle; color: string; bg: string }> = {
    ready: { icon: CheckCircle, color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20' },
    completed: { icon: CheckCircle, color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20' },
    processing: { icon: Clock, color: 'text-gold', bg: 'bg-gold/10 border-gold/20' },
    failed: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-400/10 border-red-400/20' },
    pending: { icon: AlertCircle, color: 'text-muted-foreground', bg: 'bg-secondary border-border' },
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 text-gold animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="p-4 rounded-xl border border-destructive/30 bg-destructive/10 text-sm text-destructive">
          Error loading resources: {(error as Error).message}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      {/* Header */}
      <div className="flex justify-between items-start mb-8 animate-fade-up">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
            <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">
              Library
            </span>
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground mb-1">
            Resources
          </h1>
          <p className="text-muted-foreground text-sm">
            Upload and manage your learning materials
          </p>
        </div>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            onChange={handleUpload}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-gold/10 border border-gold/20 text-gold text-sm font-medium hover:bg-gold/20 hover:border-gold/30 transition-all disabled:opacity-50"
          >
            {uploadMutation.isPending ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Uploading...</>
            ) : (
              <><Upload className="w-4 h-4" /> Upload PDF</>
            )}
          </button>
        </div>
      </div>

      {/* Upload error */}
      {uploadMutation.isError && (
        <div className="mb-6 p-3 rounded-lg border border-destructive/30 bg-destructive/10 text-sm text-destructive animate-fade-up">
          Upload failed. Please try again.
        </div>
      )}

      {/* Content */}
      {data?.items.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center animate-fade-up">
          <div className="w-16 h-16 rounded-xl bg-card border border-border flex items-center justify-center mb-5">
            <FileText className="w-7 h-7 text-muted-foreground" />
          </div>
          <h3 className="font-display text-xl font-semibold text-foreground mb-2">No resources yet</h3>
          <p className="text-sm text-muted-foreground mb-6 max-w-sm">
            Upload a PDF to build your knowledge base. Your AI tutor will use it to create learning sessions.
          </p>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors shadow-lg shadow-gold/20"
          >
            <Plus className="w-4 h-4" />
            Upload your first PDF
          </button>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {data?.items.map((resource, i) => {
            const config = statusConfig[resource.status] || statusConfig.pending;
            const StatusIcon = config.icon;
            const isReady = resource.status === 'ready' || resource.status === 'completed';

            return (
              <div
                key={resource.id}
                className="group relative rounded-xl border border-border bg-card p-5 transition-all duration-200 hover:border-gold/20 hover:shadow-lg hover:shadow-gold/5 animate-fade-up"
                style={{ animationDelay: `${0.05 + i * 0.03}s` }}
              >
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-10 h-10 rounded-lg bg-secondary border border-border flex items-center justify-center flex-shrink-0">
                    <FileText className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-card-foreground truncate">
                      {resource.filename}
                    </p>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      {resource.topic || 'No topic assigned'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs font-medium ${config.bg}`}>
                      <StatusIcon className={`w-3 h-3 ${config.color} ${resource.status === 'processing' ? 'animate-pulse-gold' : ''}`} />
                      <span className={config.color}>{resource.status}</span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {new Date(resource.uploaded_at).toLocaleDateString()}
                    </span>
                  </div>

                  {isReady && (
                    <button
                      onClick={() => navigate('/sessions/new')}
                      className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium text-gold hover:bg-gold/10 transition-colors opacity-0 group-hover:opacity-100"
                    >
                      <Sparkles className="w-3 h-3" />
                      Study
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
