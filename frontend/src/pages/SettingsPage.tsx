import { useEffect, useState } from 'react';
import { CheckCircle2, Key, Loader2, Save, Settings2 } from 'lucide-react';
import { useUserSettings, useUpdateUserSettings } from '../api/hooks';

export default function SettingsPage() {
  const { data, isLoading } = useUserSettings();
  const updateSettings = useUpdateUserSettings();
  const [consentTrainingGlobal, setConsentTrainingGlobal] = useState(false);

  // BYOK state — stored only in localStorage, never sent to server
  const [byokApiKey, setByokApiKey] = useState('');
  const [byokBaseUrl, setByokBaseUrl] = useState('');
  const [byokSaved, setByokSaved] = useState(false);

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
                Optionally provide your own LLM API key. Your key is stored <strong>only in your browser</strong> and
                is never persisted on the server.
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
                Your key will be sent as a header with each request to the tutoring API.
                Clear the field and save to stop using BYOK.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
