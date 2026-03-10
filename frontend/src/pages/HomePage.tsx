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
    <div className="h-full flex flex-col p-8 overflow-auto">
      {/* Hero */}
      <div className="max-w-3xl mb-12 animate-fade-up">
        <div className="flex items-center gap-2 mb-4">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">
            Unified Tutor
          </span>
        </div>
        <h1 className="font-display text-4xl md:text-5xl font-semibold tracking-tight text-foreground leading-[1.1] mb-4">
          Build course notebooks,<br />
          <span className="italic text-gold">then learn in context.</span>
        </h1>
        <p className="text-muted-foreground text-lg max-w-xl leading-relaxed">
          Notebooks are now your primary learning container. Attach resources,
          run notebook-scoped sessions, and track progress across the full course.
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid md:grid-cols-3 gap-5 max-w-4xl mb-10">
        {/* Upload Card */}
        <button
          onClick={() => navigate('/notebooks/new')}
          className="group relative overflow-hidden rounded-xl border border-border bg-card p-6 text-left transition-all duration-300 hover:border-gold/30 hover:shadow-lg hover:shadow-gold/5 animate-fade-up"
          style={{ animationDelay: '0.1s' }}
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-gold/5 to-transparent rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="relative">
            <div className="w-11 h-11 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center mb-5 group-hover:bg-gold/15 transition-colors">
              <Upload className="w-5 h-5 text-gold" />
            </div>
            <h3 className="font-display text-lg font-semibold mb-1.5 text-card-foreground">
              Create Notebook
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              Start a course container with goals and session modes.
            </p>
            <div className="flex items-center gap-1.5 text-xs font-medium text-gold opacity-0 group-hover:opacity-100 transition-opacity">
              New notebook <ArrowRight className="w-3 h-3" />
            </div>
          </div>
        </button>

        {/* Browse Card */}
        <button
          onClick={() => navigate('/notebooks')}
          className="group relative overflow-hidden rounded-xl border border-border bg-card p-6 text-left transition-all duration-300 hover:border-gold/30 hover:shadow-lg hover:shadow-gold/5 animate-fade-up"
          style={{ animationDelay: '0.2s' }}
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-gold/5 to-transparent rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="relative">
            <div className="w-11 h-11 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center mb-5 group-hover:bg-gold/15 transition-colors">
              <BookOpen className="w-5 h-5 text-gold" />
            </div>
            <h3 className="font-display text-lg font-semibold mb-1.5 text-card-foreground">
              Open Notebooks
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              Enter your notebook workspace and manage resources/sessions.
            </p>
            <div className="flex items-center gap-1.5 text-xs font-medium text-gold opacity-0 group-hover:opacity-100 transition-opacity">
              {notebookCount} notebook{notebookCount !== 1 ? 's' : ''} <ArrowRight className="w-3 h-3" />
            </div>
          </div>
        </button>

        {/* Start Session Card */}
        <button
          onClick={() => navigate('/notebooks')}
          className="group relative overflow-hidden rounded-xl border border-gold/20 bg-gradient-to-br from-gold/[0.08] to-card p-6 text-left transition-all duration-300 hover:border-gold/40 hover:shadow-lg hover:shadow-gold/10 animate-fade-up"
          style={{ animationDelay: '0.3s' }}
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-gold/10 to-transparent rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="relative">
            <div className="w-11 h-11 rounded-lg bg-gold/15 border border-gold/25 flex items-center justify-center mb-5 group-hover:bg-gold/25 transition-colors">
              <Sparkles className="w-5 h-5 text-gold" />
            </div>
            <h3 className="font-display text-lg font-semibold mb-1.5 text-card-foreground">
              Notebook Study
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              Launch notebook-scoped tutoring with mode-aware sessions.
            </p>
            <div className="flex items-center gap-1.5 text-xs font-medium text-gold">
              Open notebooks <ArrowRight className="w-3 h-3 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        </button>
      </div>

      {creditsEnabled && balance && (
        <div className="max-w-4xl mb-8 animate-fade-up" style={{ animationDelay: '0.32s' }}>
          <div className={`rounded-xl border p-5 ${isLowBalance ? 'border-amber-500/30 bg-amber-500/5' : 'border-border bg-card'}`}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  {isLowBalance ? <AlertTriangle className="w-4 h-4 text-amber-400" /> : <Wallet className="w-4 h-4 text-gold" />}
                  <p className="text-sm font-medium text-foreground">Platform credit status</p>
                </div>
                <p className="text-sm text-muted-foreground max-w-2xl">
                  Balance: {balance.balance.toLocaleString()} credits. Live tutoring with BYOK bypasses platform billing, but uploads and queued preparation always use platform credits.
                </p>
              </div>
              <button
                onClick={() => navigate('/billing')}
                className="inline-flex items-center gap-2 rounded-lg border border-gold/20 bg-gold/10 px-3 py-2 text-sm font-medium text-gold"
              >
                Open billing <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {showConsentPrompt && (
        <div className="max-w-4xl mb-8 animate-fade-up" style={{ animationDelay: '0.35s' }}>
          <div className="rounded-xl border border-gold/25 bg-gold/[0.05] p-5">
            <h2 className="font-display text-lg font-semibold text-foreground mb-1.5">
              Research participation preference
            </h2>
            <p className="text-sm text-muted-foreground mb-4 max-w-2xl leading-relaxed">
                StudyAgent is a research project. You can choose whether anonymized tutoring
                interactions may be used to improve model quality, and change this anytime.
            </p>
            <div className="flex flex-wrap gap-2.5">
              <button
                onClick={() => saveConsentPreference(true)}
                className="px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium hover:bg-gold/90 transition-colors"
              >
                Opt in
              </button>
              <button
                onClick={() => saveConsentPreference(false)}
                className="px-4 py-2 rounded-lg border border-border text-sm font-medium text-foreground hover:border-gold/20 transition-colors"
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
            <p className="text-2xl font-display font-semibold text-foreground">{notebookCount}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Notebooks</p>
          </div>
          <div>
            <p className="text-2xl font-display font-semibold text-foreground">{resourceCount}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Attached resources</p>
          </div>
          <div>
            <p className="text-2xl font-display font-semibold text-foreground">{resourceCount}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Library resources</p>
          </div>
        </div>
      </div>
    </div>
  )
}
