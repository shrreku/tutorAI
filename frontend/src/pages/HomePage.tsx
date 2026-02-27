import { useNavigate } from 'react-router-dom'
import { BookOpen, Upload, MessageSquare, ArrowRight, Sparkles, Clock } from 'lucide-react'
import { useResources, useSessions } from '../api/hooks'

export default function HomePage() {
  const navigate = useNavigate()
  const { data: resourcesData } = useResources()
  const { data: sessionsData } = useSessions()

  const resourceCount = resourcesData?.items?.length ?? 0
  const sessionCount = sessionsData?.items?.length ?? 0
  const activeSessions = sessionsData?.items?.filter(s => s.status === 'active') ?? []

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      {/* Hero */}
      <div className="max-w-3xl mb-12 animate-fade-up">
        <div className="flex items-center gap-2 mb-4">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">
            Welcome back
          </span>
        </div>
        <h1 className="font-display text-4xl md:text-5xl font-semibold tracking-tight text-foreground leading-[1.15] mb-4">
          What would you like to<br />
          <span className="italic text-gold">study today?</span>
        </h1>
        <p className="text-muted-foreground text-lg max-w-xl leading-relaxed">
          Upload your materials, and let your AI tutor guide you through them
          with adaptive, grounded instruction.
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid md:grid-cols-3 gap-5 max-w-4xl mb-10">
        {/* Upload Card */}
        <button
          onClick={() => navigate('/resources')}
          className="group relative overflow-hidden rounded-xl border border-border bg-card p-6 text-left transition-all duration-300 hover:border-gold/30 hover:shadow-lg hover:shadow-gold/5 animate-fade-up"
          style={{ animationDelay: '0.1s' }}
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-gold/5 to-transparent rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="relative">
            <div className="w-11 h-11 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center mb-5 group-hover:bg-gold/15 transition-colors">
              <Upload className="w-5 h-5 text-gold" />
            </div>
            <h3 className="font-display text-lg font-semibold mb-1.5 text-card-foreground">
              Upload Resources
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              Upload educational PDFs to build your knowledge base
            </p>
            <div className="flex items-center gap-1.5 text-xs font-medium text-gold opacity-0 group-hover:opacity-100 transition-opacity">
              Go to Resources <ArrowRight className="w-3 h-3" />
            </div>
          </div>
        </button>

        {/* Browse Card */}
        <button
          onClick={() => navigate('/resources')}
          className="group relative overflow-hidden rounded-xl border border-border bg-card p-6 text-left transition-all duration-300 hover:border-gold/30 hover:shadow-lg hover:shadow-gold/5 animate-fade-up"
          style={{ animationDelay: '0.2s' }}
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-gold/5 to-transparent rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="relative">
            <div className="w-11 h-11 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center mb-5 group-hover:bg-gold/15 transition-colors">
              <BookOpen className="w-5 h-5 text-gold" />
            </div>
            <h3 className="font-display text-lg font-semibold mb-1.5 text-card-foreground">
              Browse Resources
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              View and manage your uploaded learning materials
            </p>
            <div className="flex items-center gap-1.5 text-xs font-medium text-gold opacity-0 group-hover:opacity-100 transition-opacity">
              {resourceCount} resource{resourceCount !== 1 ? 's' : ''} <ArrowRight className="w-3 h-3" />
            </div>
          </div>
        </button>

        {/* Start Session Card */}
        <button
          onClick={() => navigate('/sessions/new')}
          className="group relative overflow-hidden rounded-xl border border-gold/20 bg-gradient-to-br from-gold/[0.08] to-card p-6 text-left transition-all duration-300 hover:border-gold/40 hover:shadow-lg hover:shadow-gold/10 animate-fade-up"
          style={{ animationDelay: '0.3s' }}
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-gold/10 to-transparent rounded-bl-full opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="relative">
            <div className="w-11 h-11 rounded-lg bg-gold/15 border border-gold/25 flex items-center justify-center mb-5 group-hover:bg-gold/25 transition-colors">
              <Sparkles className="w-5 h-5 text-gold" />
            </div>
            <h3 className="font-display text-lg font-semibold mb-1.5 text-card-foreground">
              Start Learning
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-4">
              Begin a new tutoring session with your AI tutor
            </p>
            <div className="flex items-center gap-1.5 text-xs font-medium text-gold">
              New Session <ArrowRight className="w-3 h-3 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        </button>
      </div>

      {/* Active Sessions */}
      {activeSessions.length > 0 && (
        <div className="max-w-4xl animate-fade-up" style={{ animationDelay: '0.4s' }}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-xl font-semibold text-foreground">
              Active Sessions
            </h2>
            <button
              onClick={() => navigate('/sessions')}
              className="text-xs font-medium text-gold hover:text-gold/80 flex items-center gap-1 transition-colors"
            >
              View all <ArrowRight className="w-3 h-3" />
            </button>
          </div>
          <div className="space-y-2">
            {activeSessions.slice(0, 3).map((session) => (
              <button
                key={session.id}
                onClick={() => navigate(`/sessions/${session.id}`)}
                className="w-full flex items-center gap-4 p-4 rounded-lg border border-border bg-card hover:border-gold/20 hover:bg-card/80 transition-all group text-left"
              >
                <div className="w-9 h-9 rounded-lg bg-gold/10 border border-gold/15 flex items-center justify-center flex-shrink-0">
                  <MessageSquare className="w-4 h-4 text-gold" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-card-foreground truncate">
                    Session
                  </p>
                  <p className="text-xs text-muted-foreground">
                    <Clock className="w-3 h-3 inline mr-1" />
                    {new Date(session.created_at).toLocaleDateString()}
                  </p>
                </div>
                <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Stats Footer */}
      <div className="mt-auto pt-8 max-w-4xl animate-fade-up" style={{ animationDelay: '0.5s' }}>
        <div className="flex gap-8 border-t border-border/50 pt-6">
          <div>
            <p className="text-2xl font-display font-semibold text-foreground">{resourceCount}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Resources</p>
          </div>
          <div>
            <p className="text-2xl font-display font-semibold text-foreground">{sessionCount}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Sessions</p>
          </div>
          <div>
            <p className="text-2xl font-display font-semibold text-foreground">{activeSessions.length}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Active</p>
          </div>
        </div>
      </div>
    </div>
  )
}
