import { useEffect, useState } from 'react';
import { CheckCircle2, Key, Loader2, Save, ShieldAlert, Sparkles, Trash2, Cpu, FileText } from 'lucide-react';
import { cn } from '../lib/utils';
import { getApiErrorMessage } from '../api/client';
import { useAsyncByokEscrows, useRevokeAsyncByokEscrow, useUserSettings, useUpdateUserSettings, useModelCatalog, useModelPreferences, useUpdateModelPreferences } from '../api/hooks';

export default function SettingsPage() {
  const { data, isLoading } = useUserSettings();
  const { data: asyncByokEscrows, isLoading: asyncByokEscrowsLoading } = useAsyncByokEscrows();
  const revokeAsyncByokEscrow = useRevokeAsyncByokEscrow();
  const updateSettings = useUpdateUserSettings();

  // BYOK state — stored only in localStorage, never sent to server
  const [byokApiKey, setByokApiKey] = useState('');
  const [byokBaseUrl, setByokBaseUrl] = useState('');
  const [byokSaved, setByokSaved] = useState(false);
  const [byokError, setByokError] = useState<string | null>(null);
  const [asyncByokFeedback, setAsyncByokFeedback] = useState<string | null>(null);

  // Model selection state (CM-013)
  const { data: modelCatalog } = useModelCatalog();
  const { data: modelPrefs } = useModelPreferences();
  const updateModelPrefs = useUpdateModelPreferences();
  const [selectedTutoringModel, setSelectedTutoringModel] = useState('');
  const [selectedArtifactModel, setSelectedArtifactModel] = useState('');
  const [selectedUploadModel, setSelectedUploadModel] = useState('');
  const [modelSaved, setModelSaved] = useState(false);

  // Learning preferences state (PROD-025)
  const [lpPace, setLpPace] = useState<string | null>(null);
  const [lpDepth, setLpDepth] = useState<string | null>(null);
  const [lpStyle, setLpStyle] = useState<string | null>(null);
  const [lpHintLevel, setLpHintLevel] = useState<string | null>(null);
  const [lpSaved, setLpSaved] = useState(false);

  useEffect(() => {
    if (data) {
      if (data.learning_preferences) {
        setLpPace(data.learning_preferences.pace ?? null);
        setLpDepth(data.learning_preferences.depth ?? null);
        setLpStyle(data.learning_preferences.tutoring_style ?? null);
        setLpHintLevel(data.learning_preferences.hint_level ?? null);
      }
    }
  }, [data]);

  // Load BYOK from localStorage on mount
  useEffect(() => {
    try {
      setByokApiKey(localStorage.getItem('byok_api_key') ?? '');
      setByokBaseUrl(localStorage.getItem('byok_api_base_url') ?? '');
    } catch { /* noop */ }
  }, []);

  // Load model preferences
  useEffect(() => {
    if (modelPrefs?.preferences) {
      setSelectedTutoringModel(modelPrefs.preferences.tutoring_model_id || '');
      setSelectedArtifactModel(modelPrefs.preferences.artifact_model_id || '');
      setSelectedUploadModel(modelPrefs.preferences.upload_model_id || '');
    }
  }, [modelPrefs]);

  const handleSaveByok = () => {
    try {
      setByokError(null);
      if (byokBaseUrl.trim()) {
        const parsed = new URL(byokBaseUrl.trim());
        if (parsed.protocol !== 'https:') {
          setByokError('Custom BYOK base URLs must use HTTPS.');
          return;
        }
        const blockedHosts = new Set(['localhost', '127.0.0.1', '0.0.0.0', '::1']);
        if (blockedHosts.has(parsed.hostname.toLowerCase()) || parsed.hostname.toLowerCase().endsWith('.local')) {
          setByokError('Local or private BYOK base URLs are not allowed.');
          return;
        }
      }
      if (byokApiKey) {
        localStorage.setItem('byok_api_key', byokApiKey);
      } else {
        localStorage.removeItem('byok_api_key');
      }
      if (byokBaseUrl) {
        localStorage.setItem('byok_api_base_url', byokBaseUrl);
      } else {
        localStorage.removeItem('byok_api_base_url');
      }
      setByokSaved(true);
      setTimeout(() => setByokSaved(false), 2000);
    } catch { /* noop */ }
  };

  const handleSaveModelPrefs = async () => {
    try {
      await updateModelPrefs.mutateAsync({
        tutoring_model_id: selectedTutoringModel || undefined,
        artifact_model_id: selectedArtifactModel || undefined,
        upload_model_id: selectedUploadModel || undefined,
      });
      setModelSaved(true);
      setTimeout(() => setModelSaved(false), 2000);
    } catch (err) {
      console.error('Failed to save model preferences', err);
    }
  };

  const handleRevokeAsyncByokEscrow = async (escrowId: string) => {
    setAsyncByokFeedback(null);
    try {
      await revokeAsyncByokEscrow.mutateAsync(escrowId);
      setAsyncByokFeedback('Async BYOK escrow revoked. Queued jobs will no longer be able to decrypt it.');
    } catch (error) {
      setAsyncByokFeedback(getApiErrorMessage(error, 'Failed to revoke async BYOK escrow.'));
    }
  };

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <div className="max-w-3xl animate-fade-up">
        <div className="flex items-center gap-2 mb-3">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium font-ui">Settings</span>
        </div>
        <h1 className="editorial-title text-3xl md:text-4xl text-foreground leading-tight mb-2">
          Account <span className="italic text-gold">preferences</span>
        </h1>
        <p className="text-muted-foreground max-w-2xl text-sm reading-copy">
          Manage your learning defaults, AI model choices, and account tools.
        </p>
      </div>

      <div className="max-w-3xl mt-8 space-y-6">
        {/* ── 1. Learning Preferences (PROD-025) ─────────────── */}
        <div className="rounded-2xl border border-border bg-card p-6 animate-fade-up" style={{ animationDelay: '0.03s' }}>
          <div className="flex items-start gap-3 mb-5">
            <div className="w-9 h-9 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4 text-gold" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-card-foreground">Learning preferences</h2>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                Account-wide defaults. Notebooks and sessions can override these.
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Study pace</label>
                <div className="flex gap-1.5">
                  {(['relaxed', 'moderate', 'intensive'] as const).map((opt) => (
                    <button key={opt} type="button" onClick={() => setLpPace(lpPace === opt ? null : opt)}
                      className={cn('flex-1 py-2 rounded-lg text-xs font-medium border transition-colors text-center capitalize',
                        lpPace === opt ? 'border-gold/40 bg-gold/10 text-gold' : 'border-border/60 text-muted-foreground hover:border-gold/20 hover:text-foreground')}>
                      {opt}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Depth</label>
                <div className="flex gap-1.5">
                  {(['surface', 'balanced', 'deep'] as const).map((opt) => (
                    <button key={opt} type="button" onClick={() => setLpDepth(lpDepth === opt ? null : opt)}
                      className={cn('flex-1 py-2 rounded-lg text-xs font-medium border transition-colors text-center capitalize',
                        lpDepth === opt ? 'border-gold/40 bg-gold/10 text-gold' : 'border-border/60 text-muted-foreground hover:border-gold/20 hover:text-foreground')}>
                      {opt}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Tutoring style</label>
                <div className="flex flex-wrap gap-1.5">
                  {(['explanation-heavy', 'practice-heavy', 'balanced', 'socratic'] as const).map((opt) => (
                    <button key={opt} type="button" onClick={() => setLpStyle(lpStyle === opt ? null : opt)}
                      className={cn('px-3 py-1.5 rounded-full text-xs font-medium border transition-colors capitalize',
                        lpStyle === opt ? 'border-gold/40 bg-gold/10 text-gold' : 'border-border/60 text-muted-foreground hover:border-gold/20 hover:text-foreground')}>
                      {opt.replace('-', ' ')}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-2">Hint level</label>
                <div className="flex gap-1.5">
                  {(['none', 'gentle', 'full'] as const).map((opt) => (
                    <button key={opt} type="button" onClick={() => setLpHintLevel(lpHintLevel === opt ? null : opt)}
                      className={cn('flex-1 py-2 rounded-lg text-xs font-medium border transition-colors text-center capitalize',
                        lpHintLevel === opt ? 'border-gold/40 bg-gold/10 text-gold' : 'border-border/60 text-muted-foreground hover:border-gold/20 hover:text-foreground')}>
                      {opt}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-3 pt-1">
                <button
                  onClick={async () => {
                    const prefs: Record<string, unknown> = {};
                    if (lpPace) prefs.pace = lpPace;
                    if (lpDepth) prefs.depth = lpDepth;
                    if (lpStyle) prefs.tutoring_style = lpStyle;
                    if (lpHintLevel) prefs.hint_level = lpHintLevel;
                    await updateSettings.mutateAsync({
                      learning_preferences: Object.keys(prefs).length > 0 ? prefs as any : undefined,
                    });
                    setLpSaved(true);
                    setTimeout(() => setLpSaved(false), 2000);
                  }}
                  disabled={updateSettings.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors disabled:opacity-60"
                >
                  {updateSettings.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save preferences
                </button>
                <button
                  onClick={async () => {
                    setLpPace(null); setLpDepth(null); setLpStyle(null); setLpHintLevel(null);
                    await updateSettings.mutateAsync({ learning_preferences: {} as any });
                    setLpSaved(true);
                    setTimeout(() => setLpSaved(false), 2000);
                  }}
                  disabled={updateSettings.isPending}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-destructive/30 text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-60"
                >
                  <Trash2 className="w-3.5 h-3.5" /> Clear all
                </button>
                {lpSaved && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600">
                    <CheckCircle2 className="w-4 h-4" /> Saved
                  </span>
                )}
              </div>

              <p className="text-[10px] text-muted-foreground/70 font-ui">
                Set: {[lpPace && 'pace', lpDepth && 'depth', lpStyle && 'style', lpHintLevel && 'hints'].filter(Boolean).join(', ') || 'none'}
              </p>
            </div>
          )}
        </div>

        {/* ── 2. Model Preferences (CM-013) ─────────────────── */}
        {modelCatalog && modelCatalog.length > 0 && (
          <div className="rounded-2xl border border-border bg-card p-6 animate-fade-up" style={{ animationDelay: '0.06s' }}>
            <div className="flex items-start gap-3 mb-5">
              <div className="w-9 h-9 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center shrink-0">
                <Cpu className="w-4 h-4 text-gold" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-card-foreground">Model preferences</h2>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                  Choose AI models for each task. Economy models use fewer credits.
                </p>
              </div>
            </div>

            <div className="space-y-4">
              {[
                { label: 'Tutoring model', value: selectedTutoringModel, setter: setSelectedTutoringModel },
                { label: 'Artifact generation', value: selectedArtifactModel, setter: setSelectedArtifactModel },
                { label: 'Upload processing', value: selectedUploadModel, setter: setSelectedUploadModel },
              ].map(({ label, value, setter }) => (
                <div key={label}>
                  <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-1.5">{label}</label>
                  <select value={value} onChange={(e) => setter(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-border bg-background/30 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-gold/40">
                    <option value="">System default</option>
                    {['economy', 'standard', 'premium_small'].map((cls) => {
                      const models = modelCatalog.filter((m) => m.model_class === cls && m.is_active);
                      if (!models.length) return null;
                      return (
                        <optgroup key={cls} label={cls.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}>
                          {models.map((m) => (
                            <option key={m.model_id} value={m.model_id}>{m.display_name} — {cls.replace('_', ' ')}</option>
                          ))}
                        </optgroup>
                      );
                    })}
                  </select>
                </div>
              ))}

              <div className="flex items-center gap-3 pt-1">
                <button onClick={handleSaveModelPrefs} disabled={updateModelPrefs.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors disabled:opacity-60">
                  {updateModelPrefs.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save model preferences
                </button>
                {modelSaved && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600">
                    <CheckCircle2 className="w-4 h-4" /> Saved
                  </span>
                )}
              </div>

              <p className="text-[10px] text-muted-foreground/70 font-ui">
                Economy models use fewer credits. The system may auto-route to a fallback if your model is unavailable.
              </p>
            </div>
          </div>
        )}

        {/* ── 3. Parse Page Allowance ───────────────────────── */}
        <div className="rounded-2xl border border-border bg-card p-6 animate-fade-up" style={{ animationDelay: '0.09s' }}>
          <div className="flex items-start gap-3 mb-5">
            <div className="w-9 h-9 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center shrink-0">
              <FileText className="w-4 h-4 text-gold" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-card-foreground">Parse page allowance</h2>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                Upload parsing is limited by total pages processed. Admins can extend this.
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-4">
              {[
                { label: 'Remaining', value: data?.parse_page_remaining ?? 0 },
                { label: 'Limit', value: data?.parse_page_limit ?? 0 },
                { label: 'Used', value: data?.parse_page_used ?? 0 },
                { label: 'Reserved', value: data?.parse_page_reserved ?? 0 },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-lg border border-border/70 bg-background/40 p-3">
                  <p className="text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
                  <p className="mt-1.5 text-xl font-semibold text-foreground">{value}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── 4. BYOK ──────────────────────────────────────── */}
        <div className="rounded-2xl border border-border bg-card p-6 animate-fade-up" style={{ animationDelay: '0.12s' }}>
          <div className="flex items-start gap-3 mb-5">
            <div className="w-9 h-9 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center shrink-0">
              <Key className="w-4 h-4 text-gold" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-card-foreground">Bring Your Own Key</h2>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                Your key stays <strong>only in your browser</strong> unless you use async BYOK escrow.
              </p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-1.5">API Key</label>
              <input type="password" placeholder="sk-..." value={byokApiKey} onChange={(e) => setByokApiKey(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background/30 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-gold/40" />
            </div>
            <div>
              <label className="block text-[10px] font-ui uppercase tracking-[0.14em] text-muted-foreground mb-1.5">
                API Base URL <span className="normal-case tracking-normal text-muted-foreground/60">(optional)</span>
              </label>
              <input type="text" placeholder="https://api.openai.com/v1" value={byokBaseUrl} onChange={(e) => setByokBaseUrl(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background/30 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-gold/40" />
            </div>

            <div className="flex items-center gap-3">
              <button onClick={handleSaveByok}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors">
                <Save className="w-4 h-4" /> Save BYOK
              </button>
              {byokSaved && (
                <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600">
                  <CheckCircle2 className="w-4 h-4" /> Saved locally
                </span>
              )}
            </div>

            {byokError && <p className="text-xs text-red-300">{byokError}</p>}

            <p className="text-[10px] text-muted-foreground/70 font-ui">
              Live tutoring can use BYOK. Uploads and queued flows always use platform credits.
            </p>
          </div>
        </div>

        {/* ── 5. Async BYOK Escrow ─────────────────────────── */}
        {data?.async_byok_escrow_enabled && (
          <div className="rounded-2xl border border-border bg-card p-6 animate-fade-up" style={{ animationDelay: '0.15s' }}>
            <div className="flex items-start gap-3 mb-5">
              <div className="w-9 h-9 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center shrink-0">
                <ShieldAlert className="w-4 h-4 text-gold" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-card-foreground">Async BYOK escrow</h2>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                  Backend: {data.async_byok_escrow_backend || 'unknown'} · TTL: {data.async_byok_escrow_ttl_minutes}m
                </p>
              </div>
            </div>

            {asyncByokFeedback && (
              <div className="mb-4 rounded-lg border border-border/70 bg-background/40 px-3 py-2 text-sm text-muted-foreground">
                {asyncByokFeedback}
              </div>
            )}

            {asyncByokEscrowsLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading…
              </div>
            ) : !asyncByokEscrows?.length ? (
              <p className="text-sm text-muted-foreground">No active escrows.</p>
            ) : (
              <div className="space-y-3">
                {asyncByokEscrows.map((escrow) => (
                  <div key={escrow.id} className="rounded-lg border border-border/70 bg-background/40 px-4 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          {escrow.provider_name || 'BYOK'} · {escrow.purpose_type}
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                          Expires {new Date(escrow.expires_at).toLocaleString()} · Access count {escrow.access_count}
                        </p>
                      </div>
                      <button onClick={() => handleRevokeAsyncByokEscrow(escrow.id)} disabled={revokeAsyncByokEscrow.isPending}
                        className="inline-flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-200 disabled:opacity-60">
                        {revokeAsyncByokEscrow.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                        Revoke
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
