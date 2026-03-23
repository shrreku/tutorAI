import { Link } from 'react-router-dom';
import { Sparkles, BookOpen, MessageSquare, Brain, ArrowRight, Github } from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background relative overflow-hidden">

      {/* ── Navigation bar ─────────────────────────────────────── */}
      <header className="relative z-20 flex items-center justify-between px-8 py-6 max-w-7xl mx-auto">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-9 h-9 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center group-hover:bg-gold/20 transition-colors">
            <Sparkles className="w-4.5 h-4.5 text-gold" />
          </div>
          <div>
            <span className="font-display text-xl font-semibold text-foreground tracking-tight">
              StudyAgent
            </span>
          </div>
        </Link>

        <nav className="flex items-center gap-3">
          <Link
            to="/login"
            className="px-5 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="px-5 py-2.5 text-sm font-medium rounded-lg bg-gold/10 border border-gold/20 text-gold hover:bg-gold/20 hover:border-gold/30 transition-all"
          >
            Get started
          </Link>
        </nav>
      </header>

      {/* ── Hero section ───────────────────────────────────────── */}
      <section className="relative z-10 flex flex-col items-center text-center px-8 pt-20 pb-28 max-w-4xl mx-auto">
        <div className="flex items-center gap-2 mb-6 animate-fade-in">
          <div className="h-px w-10 bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.3em] text-gold font-medium">
            AI-Powered Tutoring
          </span>
          <div className="h-px w-10 bg-gold/40" />
        </div>

        <h1
          className="font-display text-5xl sm:text-6xl md:text-7xl font-semibold tracking-tight text-foreground leading-[1.08] mb-6 animate-fade-up"
        >
          Turn any textbook into{' '}
          <span className="italic text-gold">conversations</span>
        </h1>

        <p
          className="text-lg md:text-xl text-muted-foreground max-w-2xl leading-relaxed mb-10 animate-fade-up"
          style={{ animationDelay: '0.12s' }}
        >
          Upload your study materials, pick focus areas, and learn through guided
          Socratic dialogue. One workspace for your entire study loop — grounded
          in your own sources.
        </p>

        <div
          className="flex flex-col sm:flex-row items-center gap-4 animate-fade-up"
          style={{ animationDelay: '0.24s' }}
        >
          <Link
            to="/register"
            className="group flex items-center gap-2 px-7 py-3.5 rounded-xl bg-gold text-primary-foreground font-semibold text-sm hover:brightness-110 transition-all duration-300"
          >
            Start learning — free
            <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
          <Link
            to="/login"
            className="px-7 py-3.5 rounded-xl border border-border text-foreground font-medium text-sm hover:border-gold/30 hover:bg-gold/5 transition-all duration-300"
          >
            I already have an account
          </Link>
        </div>
      </section>

      {/* ── Feature cards ──────────────────────────────────────── */}
      <section className="relative z-10 max-w-5xl mx-auto px-8 pb-24">
        <div className="grid md:grid-cols-3 gap-6">
          {[
            {
              icon: BookOpen,
              title: 'Ingest anything',
              desc: 'Upload PDFs, slides, or markdown. We extract structure, concepts, and an ontology graph automatically.',
              delay: '0.05s',
            },
            {
              icon: Brain,
              title: 'Adaptive tutoring',
              desc: 'Socratic questioning that adapts to your mastery level. Every response is grounded in your uploaded sources.',
              delay: '0.15s',
            },
            {
              icon: MessageSquare,
              title: 'Multi-concept sessions',
              desc: 'Study across topics in a single session with intelligent objective planning and step transitions.',
              delay: '0.25s',
            },
          ].map(({ icon: Icon, title, desc, delay }) => (
            <div
              key={title}
              className="group relative overflow-hidden rounded-xl border border-border bg-card p-7 transition-all duration-300 hover:border-gold/25 animate-fade-up"
              style={{ animationDelay: delay }}
            >
              <div className="relative">
                <div className="w-11 h-11 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center mb-5 group-hover:bg-gold/15 transition-colors">
                  <Icon className="w-5 h-5 text-gold" />
                </div>
                <h3 className="font-display text-lg font-semibold mb-2 text-card-foreground">
                  {title}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it works ───────────────────────────────────────── */}
      <section className="relative z-10 max-w-4xl mx-auto px-8 pb-28">
        <div className="text-center mb-14">
          <h2 className="font-display text-3xl md:text-4xl font-semibold text-foreground tracking-tight mb-3">
            Three steps to mastery
          </h2>
          <p className="text-muted-foreground text-base">
            From raw material to deep understanding — in minutes.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-10">
          {[
            { num: '01', label: 'Upload', text: 'Drop your PDF or notes. Our pipeline extracts chunks, concepts, and relationships.' },
            { num: '02', label: 'Choose topics', text: 'Pick which concepts to study. We build an adaptive plan around your goals.' },
            { num: '03', label: 'Learn', text: 'Chat with an AI tutor that asks the right questions and cites your sources.' },
          ].map(({ num, label, text }) => (
            <div key={num} className="flex flex-col">
              <span className="font-mono text-xs text-gold/60 mb-2">{num}</span>
              <h3 className="font-display text-xl font-semibold text-foreground mb-2">{label}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Research notice ────────────────────────────────────── */}
      <section className="relative z-10 max-w-3xl mx-auto px-8 pb-16">
        <div className="rounded-xl border border-border bg-card p-6 text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-gold/70 font-medium mb-2">
            Student Research Project
          </p>
          <p className="text-sm text-muted-foreground leading-relaxed max-w-xl mx-auto">
            StudyAgent is an academic research project exploring AI-powered tutoring.
            Your data is never sold. You can opt in to anonymised research data
            collection during registration — and change your preference at any time.
          </p>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-border/40 py-8 px-8">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Sparkles className="w-3.5 h-3.5 text-gold/50" />
            <span>StudyAgent &copy; {new Date().getFullYear()}</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <Link to="/register" className="hover:text-foreground transition-colors">
              Create account
            </Link>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 hover:text-foreground transition-colors"
            >
              <Github className="w-3.5 h-3.5" /> Source
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
