import { useNavigate } from 'react-router-dom'
import { BookOpen, Upload, ArrowRight, Sparkles, Wallet, AlertTriangle } from 'lucide-react'
import { useBillingBalance, useNotebooks, useResources, useUserSettings, useUpdateUserSettings } from '../api/hooks'

export default function HomePage() {
  const navigate = useNavigate()
  const { data: notebooksData } = useNotebooks()
  const { data: resourcesData } = useResources()
  const { data: userSettings } = useUserSettings()
  const { data: balance } = useBillingBalance()
  const updateUserSettings = useUpdateUserSettings()

  const notebookCount = notebooksData?.items?.length ?? 0
  const resourceCount = resourcesData?.items?.length ?? 0
  const showConsentPrompt = userSettings ? !userSettings.consent_preference_set : false
  const creditsEnabled = balance?.credits_enabled ?? false
  const isLowBalance = creditsEnabled && (balance?.balance ?? 0) < Math.round((balance?.default_monthly_grant ?? 0) * 0.2)

  const saveConsentPreference = async (enabled: boolean) => {
    try {
      await updateUserSettings.mutateAsync({ consent_training_global: enabled })
    } catch (err) {
      console.error('Failed to save consent preference', err)
    }
  }

  return (
    <div className="h-full flex flex-col overflow-auto px-6 py-8 lg:px-10">
      {/* Hero */}
      <div className="surface-scholarly max-w-5xl rounded-[32px] border border-border/70 px-7 py-8 md:px-10 md:py-10 mb-12 animate-fade-up">
        <div className="flex items-center gap-2 mb-4">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="section-kicker text-[11px] text-gold font-medium">
            Unified Tutor
          </span>
        </div>
        <h1 className="editorial-title text-5xl md:text-7xl text-foreground mb-4">
          Build course notebooks,<br />
          <span className="font-reading italic text-gold">then learn in context.</span>
        </h1>
        <p className="reading-copy text-muted-foreground text-xl max-w-2xl leading-relaxed">
          Notebooks are now your primary learning container. Attach resources,
          run notebook-scoped sessions, and track progress across the full course.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <span className="data-chip rounded-full border border-gold/20 bg-gold/10 px-3 py-1 text-[11px] font-semibold uppercase text-gold">Notebook-scoped sessions</span>
          <span className="data-chip rounded-full border border-border bg-card/70 px-3 py-1 text-[11px] font-semibold uppercase text-muted-foreground">Artifacts + notes</span>
          <span className="data-chip rounded-full border border-border bg-card/70 px-3 py-1 text-[11px] font-semibold uppercase text-muted-foreground">Progress-aware study</span>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid md:grid-cols-3 gap-5 max-w-4xl mb-10">
        {/* Upload Card */}
        <button
          onClick={() => navigate('/notebooks/new')}
          className="surface-scholarly group rounded-[28px] border border-border/70 p-6 text-left transition-all duration-300 hover:border-gold/30 animate-fade-up"
          style={{ animationDelay: '0.1s' }}
        >
          <div>
            <div className="w-11 h-11 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center mb-5 group-hover:bg-gold/15 transition-colors">
              <Upload className="w-5 h-5 text-gold" />
            </div>
            <h3 className="font-reading text-2xl font-semibold mb-1.5 text-card-foreground">
              Create Notebook
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              Start a course container with goals and session modes.
            </p>
            <div className="font-ui flex items-center gap-1.5 text-xs font-medium text-gold opacity-0 group-hover:opacity-100 transition-opacity">
              New notebook <ArrowRight className="w-3 h-3" />
            </div>
          </div>
        </button>

        {/* Browse Card */}
        <button
          onClick={() => navigate('/notebooks')}
          className="surface-scholarly group rounded-[28px] border border-border/70 p-6 text-left transition-all duration-300 hover:border-gold/30 animate-fade-up"
          style={{ animationDelay: '0.2s' }}
        >
          <div>
            <div className="w-11 h-11 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center mb-5 group-hover:bg-gold/15 transition-colors">
              <BookOpen className="w-5 h-5 text-gold" />
            </div>
            <h3 className="font-reading text-2xl font-semibold mb-1.5 text-card-foreground">
              Open Notebooks
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              Enter your notebook workspace and manage resources/sessions.
            </p>
            <div className="font-ui flex items-center gap-1.5 text-xs font-medium text-gold opacity-0 group-hover:opacity-100 transition-opacity">
              {notebookCount} notebook{notebookCount !== 1 ? 's' : ''} <ArrowRight className="w-3 h-3" />
            </div>
          </div>
        </button>

        {/* Start Session Card */}
        <button
          onClick={() => navigate('/notebooks')}
          className="surface-scholarly group rounded-[28px] border border-gold/20 p-6 text-left transition-all duration-300 hover:border-gold/30 animate-fade-up"
          style={{ animationDelay: '0.3s' }}
        >
          <div>
            <div className="w-11 h-11 rounded-lg bg-gold/15 border border-gold/25 flex items-center justify-center mb-5 group-hover:bg-gold/25 transition-colors">
              <Sparkles className="w-5 h-5 text-gold" />
            </div>
            <h3 className="font-reading text-2xl font-semibold mb-1.5 text-card-foreground">
              Notebook Study
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              Launch notebook-scoped tutoring with mode-aware sessions.
            </p>
            <div className="font-ui flex items-center gap-1.5 text-xs font-medium text-gold">
              Open notebooks <ArrowRight className="w-3 h-3 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        </button>
      </div>

      {creditsEnabled && balance && (
        <div className="max-w-4xl mb-8 animate-fade-up" style={{ animationDelay: '0.32s' }}>
          <div className={`surface-scholarly rounded-[28px] border p-5 ${isLowBalance ? 'border-amber-500/30 bg-amber-500/5' : 'border-border'}`}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  {isLowBalance ? <AlertTriangle className="w-4 h-4 text-amber-400" /> : <Wallet className="w-4 h-4 text-gold" />}
                  <p className="font-ui text-sm font-medium text-foreground">Platform credit status</p>
                </div>
                <p className="text-sm text-muted-foreground max-w-2xl">
                  Balance: {balance.balance.toLocaleString()} credits. Live tutoring with BYOK bypasses platform billing, but uploads and queued preparation always use platform credits.
                </p>
              </div>
              <button
                onClick={() => navigate('/billing')}
                className="font-ui inline-flex items-center gap-2 rounded-xl border border-gold/20 bg-gold/10 px-3 py-2 text-sm font-medium text-gold"
              >
                Open billing <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {showConsentPrompt && (
        <div className="max-w-4xl mb-8 animate-fade-up" style={{ animationDelay: '0.35s' }}>
          <div className="surface-scholarly rounded-[28px] border border-gold/25 bg-gold/[0.05] p-5">
            <h2 className="font-reading text-3xl font-semibold text-foreground mb-1.5">
              Research participation preference
            </h2>
            <p className="reading-copy text-base text-muted-foreground mb-4 max-w-2xl leading-relaxed">
                StudyAgent is a research project. You can choose whether anonymized tutoring
                interactions may be used to improve model quality, and change this anytime.
            </p>
            <div className="flex flex-wrap gap-2.5">
              <button
                onClick={() => saveConsentPreference(true)}
                className="font-ui px-4 py-2 rounded-xl bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors"
              >
                Opt in
              </button>
              <button
                onClick={() => saveConsentPreference(false)}
                className="font-ui px-4 py-2 rounded-xl border border-border text-sm font-medium text-foreground hover:border-gold/20 transition-colors"
              >
                Keep opted out
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Stats Footer */}
      <div className="mt-auto pt-8 max-w-4xl animate-fade-up" style={{ animationDelay: '0.5s' }}>
        <div className="flex gap-8 border-t border-border/50 pt-6">
          <div>
            <p className="text-3xl font-display font-semibold text-foreground">{notebookCount}</p>
            <p className="data-chip text-xs text-muted-foreground mt-0.5 uppercase">Notebooks</p>
          </div>
          <div>
            <p className="text-3xl font-display font-semibold text-foreground">{resourceCount}</p>
            <p className="data-chip text-xs text-muted-foreground mt-0.5 uppercase">Attached resources</p>
          </div>
          <div>
            <p className="text-3xl font-display font-semibold text-foreground">{resourceCount}</p>
            <p className="data-chip text-xs text-muted-foreground mt-0.5 uppercase">Library resources</p>
          </div>
        </div>
      </div>
    </div>
  )
}
