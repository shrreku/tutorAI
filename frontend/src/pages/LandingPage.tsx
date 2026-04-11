import { Link } from 'react-router-dom';
import { useRef, useState } from 'react';
import { motion, useScroll, useTransform, AnimatePresence } from 'framer-motion';
import {
  Sparkles, MessageSquare, Brain, ArrowRight, Github,
  Upload, GraduationCap, Target, BarChart3,
  PenTool, ClipboardCheck, Shield, Star, Lightbulb,
  ChevronRight, Play, Users, CheckCircle2,
  LayoutDashboard, Boxes, Building2,
} from 'lucide-react';
import {
  Reveal, FloatingParticles,
  HowItWorksTimeline, PipelineAnimation,
  PersonalizationShowcase, AdaptivePathAnimation,
  MasteryRadial, StudyMapIllustration,
} from '../components/landing/LandingAssets';

/* ─── Feature card (inline) ────────────────────────────────────── */
function FeatureCard({ icon: Icon, title, desc }: { icon: typeof Sparkles; title: string; desc: string }) {
  return (
    <motion.div
      whileHover={{ y: -4, scale: 1.015 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      className="group relative overflow-hidden rounded-2xl border border-border/60 bg-card/60 backdrop-blur-sm hover:border-gold/25 p-6 transition-colors duration-300"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-gold/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      <div className="relative">
        <div className="w-11 h-11 rounded-xl bg-gold/8 border border-gold/15 group-hover:bg-gold/12 flex items-center justify-center mb-4 transition-colors duration-300">
          <Icon className="w-5 h-5 text-gold" />
        </div>
        <h3 className="font-display text-[1.1rem] font-semibold mb-2 text-foreground tracking-tight">{title}</h3>
        <p className="text-[0.82rem] text-muted-foreground leading-relaxed">{desc}</p>
      </div>
    </motion.div>
  );
}

/* ─── Workspace mockup ─────────────────────────────────────────── */
function WorkspaceMockup() {
  return (
    <div className="landing-workspace-mockup">
      <div className="landing-mockup-chrome">
        <div className="flex items-center gap-1.5 px-4 py-3">
          <div className="w-3 h-3 rounded-full bg-red-400/60" />
          <div className="w-3 h-3 rounded-full bg-yellow-400/60" />
          <div className="w-3 h-3 rounded-full bg-green-400/60" />
          <div className="flex-1 mx-8">
            <div className="h-5 rounded-md bg-border/30 max-w-[260px] mx-auto" />
          </div>
        </div>
      </div>
      <div className="landing-mockup-body">
        <div className="grid grid-cols-12 gap-0 h-full">
          <div className="col-span-3 border-r border-border/30 p-3 space-y-3">
            <div className="h-5 w-24 rounded bg-gold/10 mb-4" />
            <div className="space-y-2">
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-gold/30" /><div className="h-3 flex-1 rounded bg-border/30" /></div>
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-gold/20" /><div className="h-3 w-3/4 rounded bg-border/20" /></div>
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-gold/15" /><div className="h-3 w-2/3 rounded bg-border/20" /></div>
            </div>
            <div className="mt-4 pt-3 border-t border-border/20">
              <div className="h-4 w-20 rounded bg-border/20 mb-2" />
              <div className="h-2 rounded-full bg-gold/20 mb-1"><div className="h-2 rounded-full bg-gold/50 w-3/5" /></div>
              <div className="h-2 rounded-full bg-gold/20"><div className="h-2 rounded-full bg-gold/40 w-2/5" /></div>
            </div>
          </div>
          <div className="col-span-6 p-4 space-y-3">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-6 h-6 rounded-full bg-gold/20 flex items-center justify-center"><Sparkles className="w-3 h-3 text-gold/60" /></div>
              <div className="h-4 w-16 rounded bg-gold/10" />
            </div>
            <div className="rounded-xl bg-card/60 border border-border/20 p-3 space-y-2 max-w-[90%]">
              <div className="h-3 w-full rounded bg-border/25" /><div className="h-3 w-5/6 rounded bg-border/20" /><div className="h-3 w-4/6 rounded bg-border/15" />
            </div>
            <div className="rounded-xl bg-gold/8 border border-gold/15 p-3 space-y-2 max-w-[80%] ml-auto">
              <div className="h-3 w-full rounded bg-gold/15" /><div className="h-3 w-3/4 rounded bg-gold/10" />
            </div>
            <div className="rounded-xl bg-card/60 border border-border/20 p-3 space-y-2 max-w-[90%]">
              <div className="h-3 w-full rounded bg-border/25" /><div className="h-3 w-4/5 rounded bg-border/20" /><div className="h-3 w-3/5 rounded bg-border/15" />
            </div>
            <div className="mt-auto pt-2"><div className="h-10 rounded-xl border border-border/30 bg-card/40 flex items-center px-3"><div className="h-3 w-32 rounded bg-border/15" /></div></div>
          </div>
          <div className="col-span-3 border-l border-border/30 p-3 space-y-3">
            <div className="h-5 w-20 rounded bg-gold/10 mb-3" />
            <div className="rounded-lg border border-border/20 bg-card/40 p-2.5 space-y-2">
              <div className="flex items-center gap-2"><PenTool className="w-3 h-3 text-gold/40" /><div className="h-3 w-12 rounded bg-gold/15" /></div>
              <div className="h-2 w-full rounded bg-border/15" /><div className="h-2 w-4/5 rounded bg-border/10" />
            </div>
            <div className="rounded-lg border border-gold/15 bg-gold/5 p-2.5 space-y-2">
              <div className="flex items-center gap-2"><ClipboardCheck className="w-3 h-3 text-gold/50" /><div className="h-3 w-10 rounded bg-gold/15" /></div>
              <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-full border border-gold/30" /><div className="h-2.5 flex-1 rounded bg-border/15" /></div>
              <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-full border border-gold/30 bg-gold/20" /><div className="h-2.5 w-4/5 rounded bg-border/15" /></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   LANDING PAGE
   ═══════════════════════════════════════════════════════════════════ */
export default function LandingPage() {
  const heroRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ['start start', 'end start'] });
  const heroY = useTransform(scrollYProgress, [0, 1], [0, 120]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.7], [1, 0]);
  const [activeTab, setActiveTab] = useState(0);

  const audienceTabs = [
    {
      label: 'Students', icon: GraduationCap,
      title: 'Your AI-powered study partner',
      desc: 'Upload your course materials and learn through guided, Socratic dialogue. The tutor adapts to what you know, asks the right questions, and generates study artifacts from your actual sources — not generic content.',
      features: ['Adaptive sessions that match your pace', 'Flashcards, quizzes & notes from your material', 'Concept-level mastery and progress tracking', 'Pick up exactly where you left off'],
    },
    {
      label: 'Teachers', icon: Users,
      title: 'Understand how your students learn',
      desc: 'Organize course content into structured notebooks. See which concepts students struggle with, review their AI-generated artifacts, and guide what they should focus on next — all backed by real session data.',
      features: ['Structure courses as notebook containers', 'Concept-level student progress visibility', 'Identify stuck points and weak areas', 'Review AI-generated study artifacts'],
    },
    {
      label: 'Institutes', icon: Building2,
      title: 'AI tutoring infrastructure for your campus',
      desc: 'Deploy a source-grounded, privacy-first tutoring platform across departments. Every answer cites uploaded materials. Full consent management, BYOK support, and anonymized research data opt-in for academic studies.',
      features: ['Privacy-first with full data consent controls', 'Bring Your Own Key for complete data ownership', 'Research-grade session analytics and mastery data', 'Scales across courses and departments'],
    },
  ];

  return (
    <div className="landing-root">
      <FloatingParticles />

      {/* ═══ Navigation ════════════════════════════════════════════ */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="landing-nav"
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 lg:px-8 py-4">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-gold/20 to-gold/5 border border-gold/20 flex items-center justify-center group-hover:from-gold/30 group-hover:to-gold/10 transition-all duration-300">
              <Sparkles className="w-4 h-4 text-gold" />
            </div>
            <span className="font-display text-xl font-semibold text-foreground tracking-tight">StudyAgent</span>
          </Link>
          <nav className="hidden md:flex items-center gap-8 text-sm font-ui">
            <a href="#how-it-works" className="text-muted-foreground hover:text-foreground transition-colors">How it works</a>
            <a href="#personalization" className="text-muted-foreground hover:text-foreground transition-colors">Personalization</a>
            <a href="#audience" className="text-muted-foreground hover:text-foreground transition-colors">For you</a>
            <a href="#features" className="text-muted-foreground hover:text-foreground transition-colors">Features</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link to="/login" className="px-5 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors hidden sm:inline-flex">Sign in</Link>
            <Link to="/register" className="landing-cta-btn group">
              Get started free <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </div>
        </div>
      </motion.header>

      {/* ═══ Hero ══════════════════════════════════════════════════ */}
      <section ref={heroRef} className="relative z-10 pt-12 pb-6 md:pt-20 md:pb-10">
        <div className="landing-hero-glow" />
        <motion.div style={{ y: heroY, opacity: heroOpacity }} className="max-w-6xl mx-auto px-6 lg:px-8">
          <div className="flex flex-col items-center text-center">

            <motion.h1 initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }} className="landing-hero-title text-foreground mb-5 max-w-[900px]">
              Turn your textbooks into{' '}<span className="landing-gradient-text italic font-reading">guided learning</span>
            </motion.h1>
            <motion.p initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.35 }} className="reading-copy text-lg md:text-xl text-muted-foreground max-w-2xl leading-relaxed mb-8">
              Upload any course material. StudyAgent builds a personalized study map, adapts to your learning style, and tutors you through Socratic dialogue — every answer grounded in your own sources.
            </motion.p>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.5 }} className="flex flex-col sm:flex-row items-center gap-4 mb-10">
              <Link to="/register" className="landing-hero-cta group">
                <span>Start learning — it's free</span><ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" />
              </Link>
              <Link to="/login" className="landing-hero-secondary group">
                <Play className="w-3.5 h-3.5 text-gold" /><span>I have an account</span>
              </Link>
            </motion.div>
          </div>
        </motion.div>
      </section>

      {/* ═══ Pipeline strip ════════════════════════════════════════ */}
      <section className="relative z-10 py-6 md:py-8">
        <Reveal className="max-w-4xl mx-auto px-6 lg:px-8">
          <PipelineAnimation />
        </Reveal>
      </section>

      {/* ═══ Workspace showcase ════════════════════════════════════ */}
      <section id="workspace" className="relative z-10 py-10 md:py-14 landing-workspace-section">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-10 lg:gap-14 items-center">
            <Reveal>
              <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">The study workspace</span>
              <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-4">
                Not a chatbot. <span className="italic font-reading text-gold">A study desk.</span>
              </h2>
              <p className="reading-copy text-muted-foreground text-base mb-6 leading-relaxed">
                Three panels working together — your course context, the AI tutor, and your study artifacts — all visible at once.
              </p>
              <div className="space-y-4">
                {[
                  { icon: LayoutDashboard, title: 'Context Panel', desc: 'Resources, objectives, progress, and concept mastery — always visible.' },
                  { icon: MessageSquare, title: 'Tutor Panel', desc: 'Socratic questioning with citations and adaptive pacing.' },
                  { icon: Boxes, title: 'Artifact Panel', desc: 'Notes, flashcards, quizzes — generated in real time.' },
                ].map(({ icon: Icon, title, desc }) => (
                  <div key={title} className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded-xl bg-gold/10 border border-gold/15 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <Icon className="w-4 h-4 text-gold" />
                    </div>
                    <div>
                      <h4 className="font-display text-sm font-semibold text-foreground mb-0.5">{title}</h4>
                      <p className="text-sm text-muted-foreground leading-relaxed">{desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Reveal>
            <Reveal delay={0.2}>
              <WorkspaceMockup />
            </Reveal>
          </div>
        </div>
      </section>

      {/* ═══ How It Works — animated timeline ═════════════════════ */}
      <section id="how-it-works" className="relative z-10 py-12 md:py-16">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">How it works</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              From upload to <span className="italic font-reading text-gold">mastery</span>
            </h2>
            <p className="reading-copy text-muted-foreground text-base max-w-xl mx-auto">
              Five steps to turn raw study material into adaptive, personalized learning.
            </p>
          </Reveal>
          <div className="grid lg:grid-cols-2 gap-10 lg:gap-14 items-start">
            <Reveal>
              <HowItWorksTimeline />
            </Reveal>
            <Reveal delay={0.15}>
              <div className="space-y-5 lg:sticky lg:top-28">
                <StudyMapIllustration />
                <MasteryRadial />
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ═══ Personalization + Adaptive ═══════════════════════════ */}
      <section id="personalization" className="relative z-10 py-12 md:py-16 landing-workspace-section">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Personalized learning</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Every learner gets a <span className="italic font-reading text-gold">unique path</span>
            </h2>
            <p className="reading-copy text-muted-foreground text-base max-w-xl mx-auto">
              StudyAgent builds a personalized study map from your materials and adapts in real-time based on how you learn.
            </p>
          </Reveal>
          <div className="grid md:grid-cols-2 gap-5">
            <Reveal>
              <PersonalizationShowcase className="h-full" />
            </Reveal>
            <Reveal delay={0.1}>
              <AdaptivePathAnimation className="h-full" />
            </Reveal>
          </div>
        </div>
      </section>

      {/* ═══ Audience Tabs ═════════════════════════════════════════ */}
      <section id="audience" className="relative z-10 py-12 md:py-16 landing-audience-section">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-8">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Built for you</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Whether you're <span className="italic font-reading text-gold">learning or teaching</span>
            </h2>
          </Reveal>
          <Reveal delay={0.1}>
            <div className="flex justify-center gap-2 mb-8">
              {audienceTabs.map((tab, i) => (
                <button key={tab.label} onClick={() => setActiveTab(i)} className={`landing-audience-tab ${activeTab === i ? 'active' : ''}`}>
                  <tab.icon className="w-4 h-4" /><span>{tab.label}</span>
                </button>
              ))}
            </div>
          </Reveal>
          <Reveal delay={0.2}>
            <AnimatePresence mode="wait">
              <motion.div key={activeTab} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }} transition={{ duration: 0.35 }} className="landing-audience-card">
                <div className="grid md:grid-cols-2 gap-8 items-center">
                  <div>
                    <h3 className="font-display text-2xl md:text-3xl font-semibold text-foreground mb-3 tracking-tight">{audienceTabs[activeTab].title}</h3>
                    <p className="reading-copy text-muted-foreground text-sm leading-relaxed mb-5">{audienceTabs[activeTab].desc}</p>
                    <Link to="/register" className="landing-cta-btn inline-flex group">
                      Get started <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                    </Link>
                  </div>
                  <div className="space-y-2.5">
                    {audienceTabs[activeTab].features.map((feat, i) => (
                      <motion.div key={feat} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.08 }} className="flex items-center gap-3 rounded-xl border border-border/40 bg-card/50 backdrop-blur-sm px-4 py-3">
                        <CheckCircle2 className="w-4 h-4 text-gold flex-shrink-0" />
                        <span className="text-sm font-medium text-foreground">{feat}</span>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>
          </Reveal>
        </div>
      </section>

      {/* ═══ Features ══════════════════════════════════════════════ */}
      <section id="features" className="relative z-10 py-12 md:py-16">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Under the hood</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Powered by <span className="italic font-reading text-gold">real intelligence</span>
            </h2>
            <p className="reading-copy text-muted-foreground text-base max-w-xl mx-auto">
              Not a wrapper around a chatbot. A full learning pipeline from document parsing to mastery tracking.
            </p>
          </Reveal>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              { icon: Upload, title: 'Smart ingestion', desc: 'PDFs, slides, DOCX parsed into structured chunks with concept extraction and knowledge-base indexing.' },
              { icon: Brain, title: 'Socratic tutoring', desc: 'The AI asks questions instead of lecturing. Responses adapt to your mastery and cite your sources.' },
              { icon: Target, title: 'Adaptive study maps', desc: 'Concept graphs and learning objectives built automatically. The system knows what to teach next.' },
              { icon: PenTool, title: 'Artifact generation', desc: 'Flashcards, quizzes, revision plans generated from your sessions — not generic templates.' },
              { icon: BarChart3, title: 'Mastery tracking', desc: 'Concept-level progress, weak areas, and next-step recommendations — visible during study.' },
              { icon: Shield, title: 'Privacy-first', desc: 'Your data is never sold. BYOK support. Optional anonymized research data with consent management.' },
            ].map((f, i) => (
              <Reveal key={f.title} delay={i * 0.05}>
                <FeatureCard {...f} />
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ Differentiators ═══════════════════════════════════════ */}
      <section className="relative z-10 py-10 md:py-14">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              What makes it <span className="italic font-reading text-gold">different</span>
            </h2>
          </Reveal>
          <div className="grid md:grid-cols-3 gap-5">
            {[
              { icon: Star, quote: 'Every answer cites your actual uploaded materials. No hallucinated explanations.', label: 'Source-grounded AI' },
              { icon: Lightbulb, quote: 'Active recall and Socratic method by default. The tutor asks you questions.', label: 'Socratic method' },
              { icon: Sparkles, quote: 'Artifacts generated from your sessions — not boilerplate templates.', label: 'Your artifacts' },
            ].map((item, i) => (
              <Reveal key={item.label} delay={i * 0.08}>
                <div className="landing-diff-card">
                  <div className="w-10 h-10 rounded-xl bg-gold/10 border border-gold/15 flex items-center justify-center mb-4">
                    <item.icon className="w-5 h-5 text-gold" />
                  </div>
                  <p className="reading-copy text-foreground text-[0.88rem] leading-relaxed mb-3 italic">"{item.quote}"</p>
                  <span className="font-ui text-xs font-semibold uppercase tracking-wider text-gold/70">{item.label}</span>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ Final CTA ═════════════════════════════════════════════ */}
      <section className="relative z-10 py-12 md:py-16">
        <Reveal>
          <div className="max-w-4xl mx-auto px-6 lg:px-8">
            <div className="landing-final-cta">
              <div className="landing-final-cta-glow" />
              <div className="relative text-center">
                <span className="section-kicker text-[11px] text-gold/80 font-medium mb-4 block">Ready to study smarter?</span>
                <h2 className="editorial-title text-3xl md:text-4xl lg:text-5xl text-foreground mb-4">
                  Start your first <span className="italic font-reading text-gold">notebook</span>
                </h2>
                <p className="reading-copy text-muted-foreground text-base max-w-xl mx-auto mb-8 leading-relaxed">
                  Upload your materials, create a notebook, and experience AI tutoring grounded in your own sources. Free to start.
                </p>
                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                  <Link to="/register" className="landing-hero-cta group">
                    <span>Create free account</span><ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" />
                  </Link>
                  <Link to="/login" className="landing-hero-secondary group">
                    <span>Sign in</span><ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-gold transition-colors" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ═══ Research Notice ════════════════════════════════════════ */}
      <section className="relative z-10 pb-8">
        <Reveal>
          <div className="max-w-3xl mx-auto px-6 lg:px-8">
            <div className="landing-research-notice">
              <div className="flex items-center gap-2 justify-center mb-2">
                <GraduationCap className="w-4 h-4 text-gold/60" />
                <span className="font-ui text-xs uppercase tracking-[0.2em] text-gold/70 font-medium">Academic Research Project</span>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed max-w-xl mx-auto text-center">
                StudyAgent is an academic research project exploring AI-powered tutoring. Your data is never sold. Opt in to anonymized research data collection during registration.
              </p>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ═══ Footer ════════════════════════════════════════════════ */}
      <footer className="relative z-10 border-t border-border/30 py-8 px-6 lg:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col md:flex-row items-center justify-between gap-5">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gold/10 border border-gold/15 flex items-center justify-center"><Sparkles className="w-3.5 h-3.5 text-gold" /></div>
              <div>
                <span className="font-display text-base font-semibold text-foreground">StudyAgent</span>
                <p className="text-xs text-muted-foreground">AI-powered notebook tutoring</p>
              </div>
            </div>
            <div className="flex items-center gap-8 text-sm text-muted-foreground">
              <Link to="/register" className="hover:text-foreground transition-colors">Create account</Link>
              <Link to="/login" className="hover:text-foreground transition-colors">Sign in</Link>
              <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 hover:text-foreground transition-colors">
                <Github className="w-3.5 h-3.5" /> Source
              </a>
            </div>
            <p className="text-xs text-muted-foreground/60">&copy; {new Date().getFullYear()} StudyAgent. MIT License.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
