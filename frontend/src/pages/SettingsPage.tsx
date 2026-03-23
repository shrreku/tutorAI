import { useEffect, useState } from 'react';
import { CheckCircle2, Key, Loader2, Save, Settings2, ShieldAlert, Trash2, Cpu, FileText } from 'lucide-react';
import { getApiErrorMessage } from '../api/client';
import { useAsyncByokEscrows, useRevokeAsyncByokEscrow, useUserSettings, useUpdateUserSettings, useModelCatalog, useModelPreferences, useUpdateModelPreferences } from '../api/hooks';

export default function SettingsPage() {
  const { data, isLoading } = useUserSettings();
  const { data: asyncByokEscrows, isLoading: asyncByokEscrowsLoading } = useAsyncByokEscrows();
  const revokeAsyncByokEscrow = useRevokeAsyncByokEscrow();
  const updateSettings = useUpdateUserSettings();
  const [consentTrainingGlobal, setConsentTrainingGlobal] = useState(false);

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

  useEffect(() => {
    if (data) {
      setConsentTrainingGlobal(Boolean(data.consent_training_global));
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

  const isSaving = updateSettings.isPending;

  const handleSave = async () => {
    try {
      await updateSettings.mutateAsync({
        consent_training_global: consentTrainingGlobal,
      });
    } catch (err) {
      console.error('Failed to update settings', err);
    }
  };

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
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">
            Settings
          </span>
        </div>
        <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight text-foreground leading-tight mb-2">
          Account <span className="italic text-gold">preferences</span>
        </h1>
        <p className="text-muted-foreground max-w-2xl">
          Manage your global research participation preference. This is a student research project,
          and you can opt in or out at any time.
        </p>
      </div>

      <div className="max-w-3xl mt-8">
        <div className="rounded-xl border border-border bg-card p-6 animate-fade-up" style={{ animationDelay: '0.03s' }}>
          <div className="flex items-start gap-3 mb-5">
            <div className="w-10 h-10 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center flex-shrink-0">
              <FileText className="w-5 h-5 text-gold" />
            </div>
            <div>
              <h2 className="font-display text-lg font-semibold text-card-foreground">
                Parse page allowance
              </h2>
              <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                Upload parsing is limited by total pages processed across your account. Admins can extend this allowance when needed.
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading page allowance...
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-4">
              <div className="rounded-lg border border-border/70 bg-background/40 p-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Remaining</p>
                <p className="mt-2 text-2xl font-semibold text-foreground">{data?.parse_page_remaining ?? 0}</p>
              </div>
              <div className="rounded-lg border border-border/70 bg-background/40 p-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Limit</p>
                <p className="mt-2 text-2xl font-semibold text-foreground">{data?.parse_page_limit ?? 0}</p>
              </div>
              <div className="rounded-lg border border-border/70 bg-background/40 p-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Used</p>
                <p className="mt-2 text-2xl font-semibold text-foreground">{data?.parse_page_used ?? 0}</p>
              </div>
              <div className="rounded-lg border border-border/70 bg-background/40 p-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Reserved</p>
                <p className="mt-2 text-2xl font-semibold text-foreground">{data?.parse_page_reserved ?? 0}</p>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-xl border border-border bg-card p-6 animate-fade-up" style={{ animationDelay: '0.05s' }}>
          <div className="flex items-start gap-3 mb-5">
            <div className="w-10 h-10 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center flex-shrink-0">
              <Settings2 className="w-5 h-5 text-gold" />
            </div>
            <div>
              <h2 className="font-display text-lg font-semibold text-card-foreground">
                Research consent
              </h2>
              <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                Allow anonymized tutoring interactions to be used for model quality improvement and
                evaluation in this student research project.
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading your settings...
            </div>
          ) : (
            <>
              <label className="flex items-start gap-3 p-4 rounded-lg border border-border/80 bg-background/30 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 rounded border-border accent-[hsl(var(--gold))]"
                  checked={consentTrainingGlobal}
                  onChange={(e) => setConsentTrainingGlobal(e.target.checked)}
                />
                <div>
                  <p className="text-sm font-medium text-foreground">Opt in to research data usage</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    This sets your global default for new tutoring sessions.
                  </p>
                </div>
              </label>

              <div className="mt-4 flex items-center gap-3">
                <button
                  onClick={handleSave}
                  disabled={isSaving}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors disabled:opacity-60"
                >
                  {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save preference
                </button>

                {updateSettings.isSuccess && !isSaving && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600">
                    <CheckCircle2 className="w-4 h-4" />
                    Saved
                  </span>
                )}
              </div>
            </>
          )}
        </div>

        {/* BYOK Section */}
        <div className="rounded-xl border border-border bg-card p-6 mt-6 animate-fade-up" style={{ animationDelay: '0.1s' }}>
          <div className="flex items-start gap-3 mb-5">
            <div className="w-10 h-10 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center flex-shrink-0">
              <Key className="w-5 h-5 text-gold" />
            </div>
            <div>
              <h2 className="font-display text-lg font-semibold text-card-foreground">
                Bring Your Own Key (BYOK)
              </h2>
              <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                BYOK is used for live tutoring, notebook session planning, and notebook artifact generation. Uploads only
                use it when you opt into async BYOK escrow, and your key stays <strong>only in your browser</strong>
                unless you explicitly choose that escrow flow.
              </p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">API Key</label>
              <input
                type="password"
                placeholder="sk-..."
                value={byokApiKey}
                onChange={(e) => setByokApiKey(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background/30 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-gold/40"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">
                API Base URL <span className="text-muted-foreground font-normal">(optional)</span>
              </label>
              <input
                type="text"
                placeholder="https://api.openai.com/v1"
                value={byokBaseUrl}
                onChange={(e) => setByokBaseUrl(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-border bg-background/30 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-gold/40"
              />
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={handleSaveByok}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors"
              >
                <Save className="w-4 h-4" />
                Save BYOK settings
              </button>

              {byokSaved && (
                <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600">
                  <CheckCircle2 className="w-4 h-4" />
                  Saved locally
                </span>
              )}
            </div>

            {byokApiKey && (
              <p className="text-xs text-muted-foreground">
                Your key is attached only to live request-scoped tutoring calls. Clear the field and save to stop using BYOK.
              </p>
            )}

            <div className="rounded-lg border border-border/70 bg-background/40 px-3 py-2 text-xs text-muted-foreground">
              Hosted policy: live tutoring can use BYOK. Uploads, ingestion, and other queued preparation flows always use
              platform infrastructure and may consume platform credits.
            </div>

            {byokError && (
              <p className="text-xs text-red-300">{byokError}</p>
            )}
          </div>
        </div>

        {data?.async_byok_escrow_enabled && (
          <div className="rounded-xl border border-border bg-card p-6 mt-6 animate-fade-up" style={{ animationDelay: '0.15s' }}>
            <div className="flex items-start gap-3 mb-5">
              <div className="w-10 h-10 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center flex-shrink-0">
                <ShieldAlert className="w-5 h-5 text-gold" />
              </div>
              <div>
                <h2 className="font-display text-lg font-semibold text-card-foreground">
                  Async BYOK escrow
                </h2>
                <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                  Background uploads can temporarily escrow your BYOK in encrypted form so queued ingestion workers can use it.
                  Backend: {data.async_byok_escrow_backend || 'unknown'}. TTL: {data.async_byok_escrow_ttl_minutes} minutes.
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
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading active escrow objects...
              </div>
            ) : !asyncByokEscrows?.length ? (
              <div className="rounded-lg border border-border/70 bg-background/40 px-3 py-3 text-sm text-muted-foreground">
                No active async BYOK escrows.
              </div>
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
                      <button
                        onClick={() => handleRevokeAsyncByokEscrow(escrow.id)}
                        disabled={revokeAsyncByokEscrow.isPending}
                        className="inline-flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-200 disabled:opacity-60"
                      >
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

        {/* Model Selection Section (CM-013) */}
        {modelCatalog && modelCatalog.length > 0 && (
          <div className="rounded-xl border border-border bg-card p-6 mt-6 animate-fade-up" style={{ animationDelay: '0.2s' }}>
            <div className="flex items-start gap-3 mb-5">
              <div className="w-10 h-10 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center flex-shrink-0">
                <Cpu className="w-5 h-5 text-gold" />
              </div>
              <div>
                <h2 className="font-display text-lg font-semibold text-card-foreground">
                  Model preferences
                </h2>
                <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                  Choose which AI model to use for each task. Economy models use fewer credits; premium models offer higher quality.
                </p>
              </div>
            </div>

            <div className="space-y-4">
              {[
                { label: 'Tutoring model', value: selectedTutoringModel, setter: setSelectedTutoringModel },
                { label: 'Artifact generation model', value: selectedArtifactModel, setter: setSelectedArtifactModel },
                { label: 'Upload processing model', value: selectedUploadModel, setter: setSelectedUploadModel },
              ].map(({ label, value, setter }) => (
                <div key={label}>
                  <label className="block text-sm font-medium text-foreground mb-1.5">{label}</label>
                  <select
                    value={value}
                    onChange={(e) => setter(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-border bg-background/30 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-gold/40"
                  >
                    <option value="">System default</option>
                    {['economy', 'standard', 'premium_small'].map((cls) => {
                      const models = modelCatalog.filter((m) => m.model_class === cls && m.is_active);
                      if (!models.length) return null;
                      return (
                        <optgroup key={cls} label={cls.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}>
                          {models.map((m) => (
                            <option key={m.model_id} value={m.model_id}>
                              {m.display_name} — {cls.replace('_', ' ')}
                            </option>
                          ))}
                        </optgroup>
                      );
                    })}
                  </select>
                </div>
              ))}

              <div className="flex items-center gap-3">
                <button
                  onClick={handleSaveModelPrefs}
                  disabled={updateModelPrefs.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors disabled:opacity-60"
                >
                  {updateModelPrefs.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save model preferences
                </button>

                {modelSaved && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600">
                    <CheckCircle2 className="w-4 h-4" />
                    Saved
                  </span>
                )}
              </div>

              <div className="rounded-lg border border-border/70 bg-background/40 px-3 py-2 text-xs text-muted-foreground">
                Model selection affects credit consumption. Economy models use fewer credits per request.
                The system may automatically route to a fallback model if your selected model is temporarily unavailable.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
