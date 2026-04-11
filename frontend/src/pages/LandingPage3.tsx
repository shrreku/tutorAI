import { Link } from 'react-router-dom';
import { useRef, useState } from 'react';
import { motion, useScroll, useTransform, AnimatePresence } from 'framer-motion';
import {
  Sparkles, Brain, ArrowRight, Github,
  Upload, GraduationCap, Target, BarChart3,
  PenTool, Zap, Shield, Star, Lightbulb,
  ChevronRight, Users, CheckCircle2,
  Building2,
} from 'lucide-react';
import {
  Reveal, FloatingParticles,
  HowItWorksTimeline, PersonalizationShowcase,
  AdaptivePathAnimation, MasteryRadial,
  StudyMapIllustration, ConceptCluster,
} from '../components/landing/LandingAssets';

/* ═══════════════════════════════════════════════════════════════════
   LANDING PAGE v3 — "Editorial" variant
   Magazine-style layout, large typography, alternating full-width
   sections, concept cluster hero, editorial how-it-works
   ═══════════════════════════════════════════════════════════════════ */
export default function LandingPage3() {
  const heroRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ['start start', 'end start'] });
  const heroY = useTransform(scrollYProgress, [0, 1], [0, 80]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.6], [1, 0]);
  const [activeTab, setActiveTab] = useState(0);

  const tabs = [
    { label: 'Students', icon: GraduationCap, title: 'Your AI study partner', desc: 'Upload course materials and learn through Socratic dialogue. The tutor adapts to what you know and generates artifacts from your sources.', features: ['Adaptive sessions', 'Flashcards & quizzes from your material', 'Concept-level mastery tracking', 'Resume where you left off'] },
    { label: 'Teachers', icon: Users, title: 'See how students learn', desc: 'Organize content into notebooks. See concept-level struggles, review AI artifacts, and guide focus areas with real session data.', features: ['Notebook-based course structure', 'Concept-level visibility', 'Identify weak areas', 'Review AI artifacts'] },
    { label: 'Institutes', icon: Building2, title: 'Campus-wide AI tutoring', desc: 'Privacy-first, source-grounded tutoring at scale. BYOK support, consent management, and research-grade analytics.', features: ['Full consent controls', 'BYOK data ownership', 'Research-grade analytics', 'Department-wide scaling'] },
  ];

  return (
    <div className="landing-root">
      <FloatingParticles count={10} />

      {/* ═══ Nav ═══════════════════════════════════════════════════ */}
      <motion.header initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} className="landing-nav">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 lg:px-8 py-4">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-gold/20 to-gold/5 border border-gold/20 flex items-center justify-center group-hover:from-gold/30 group-hover:to-gold/10 transition-all duration-300">
              <Sparkles className="w-4 h-4 text-gold" />
            </div>
            <span className="font-display text-xl font-semibold text-foreground tracking-tight">StudyAgent</span>
          </Link>
          <nav className="hidden md:flex items-center gap-8 text-sm font-ui">
            <a href="#how-it-works" className="text-muted-foreground hover:text-foreground transition-colors">How it works</a>
            <a href="#study-map" className="text-muted-foreground hover:text-foreground transition-colors">Study maps</a>
            <a href="#audience" className="text-muted-foreground hover:text-foreground transition-colors">For you</a>
            <a href="#features" className="text-muted-foreground hover:text-foreground transition-colors">Features</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link to="/login" className="px-5 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors hidden sm:inline-flex">Sign in</Link>
            <Link to="/register" className="landing-cta-btn group">Get started free <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" /></Link>
          </div>
        </div>
      </motion.header>

      {/* ═══ Editorial Hero ════════════════════════════════════════ */}
      <section ref={heroRef} className="relative z-10 pt-20 pb-6 md:pt-28 md:pb-10">
        <div className="landing-hero-glow" />
        <motion.div style={{ y: heroY, opacity: heroOpacity }} className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="grid lg:grid-cols-5 gap-8 lg:gap-12 items-center">
            <div className="lg:col-span-3">
              <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }} className="mb-5">
                <span className="inline-flex items-center gap-2 rounded-full bg-gold/8 border border-gold/15 px-4 py-1.5 text-xs font-ui font-medium text-gold">
                  <Zap className="w-3 h-3" /> Academic Research Project
                </span>
              </motion.div>
              <motion.h1 initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, delay: 0.2, ease: [0.22, 1, 0.36, 1] }} className="text-foreground mb-5" style={{ fontFamily: "'Instrument Serif', Georgia, serif", fontSize: 'clamp(2.4rem, 5.5vw, 4.5rem)', lineHeight: 1.1, letterSpacing: '-0.03em', fontWeight: 400 }}>
                The AI tutor that learns{' '}
                <span className="italic text-gold">your material</span>{' '}
                before teaching{' '}
                <span className="italic text-gold">you</span>
              </motion.h1>
              <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.4 }} className="reading-copy text-lg text-muted-foreground leading-relaxed mb-8 max-w-xl">
                Upload your textbooks and notes. StudyAgent extracts concepts, builds a personalized study map, and guides you with adaptive Socratic tutoring — every answer citing your own sources.
              </motion.p>
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.55 }} className="flex items-center gap-4">
                <Link to="/register" className="landing-hero-cta group"><span>Start studying free</span><ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" /></Link>
                <Link to="/login" className="landing-hero-secondary group"><span>Sign in</span><ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-gold transition-colors" /></Link>
              </motion.div>
            </div>
            <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 1, delay: 0.3, ease: [0.22, 1, 0.36, 1] }} className="lg:col-span-2">
              <ConceptCluster />
            </motion.div>
          </div>
        </motion.div>
      </section>

      {/* ═══ Editorial quote strip ═════════════════════════════════ */}
      <section className="relative z-10 py-10 border-y border-border/30">
        <Reveal className="max-w-4xl mx-auto px-6 lg:px-8 text-center">
          <p className="reading-copy text-xl md:text-2xl text-foreground/80 italic leading-relaxed" style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}>
            "Every answer grounded in your sources. No hallucinations. No generic content. Just your material, understood deeply."
          </p>
          <p className="mt-4 text-xs font-ui uppercase tracking-[0.2em] text-gold/70">Source-grounded AI tutoring</p>
        </Reveal>
      </section>

      {/* ═══ How It Works — editorial timeline ════════════════════ */}
      <section id="how-it-works" className="relative z-10 py-14 md:py-20">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">How it works</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Five steps to <span className="italic font-reading text-gold">mastery</span>
            </h2>
          </Reveal>
          <div className="grid lg:grid-cols-2 gap-10 items-start">
            <Reveal>
              <HowItWorksTimeline />
            </Reveal>
            <Reveal delay={0.15}>
              <div className="lg:sticky lg:top-28">
                <StudyMapIllustration />
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ═══ Study Map + Personalization ═══════════════════════════ */}
      <section id="study-map" className="relative z-10 py-14 md:py-20 landing-workspace-section">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Personalized learning</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Adaptive paths built from <span className="italic font-reading text-gold">your content</span>
            </h2>
            <p className="reading-copy text-muted-foreground text-base max-w-xl mx-auto">
              Your materials become a personalized study map. The tutor adapts in real-time based on mastery, gaps, and learning patterns.
            </p>
          </Reveal>

          {/* Staggered editorial cards */}
          <div className="space-y-5">
            <div className="grid md:grid-cols-2 gap-5">
              <Reveal>
                <PersonalizationShowcase className="h-full" />
              </Reveal>
              <Reveal delay={0.1}>
                <AdaptivePathAnimation className="h-full" />
              </Reveal>
            </div>
            <Reveal delay={0.15}>
              <MasteryRadial />
            </Reveal>
          </div>
        </div>
      </section>

      {/* ═══ Audience tabs ═════════════════════════════════════════ */}
      <section id="audience" className="relative z-10 py-14 md:py-20 landing-audience-section">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-8">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Built for you</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Whether you're <span className="italic font-reading text-gold">learning or teaching</span>
            </h2>
          </Reveal>
          <Reveal delay={0.1}>
            <div className="flex justify-center gap-2 mb-8">
              {tabs.map((tab, i) => (
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
                    <h3 className="font-display text-2xl font-semibold text-foreground mb-3 tracking-tight">{tabs[activeTab].title}</h3>
                    <p className="reading-copy text-muted-foreground text-sm leading-relaxed mb-5">{tabs[activeTab].desc}</p>
                    <Link to="/register" className="landing-cta-btn inline-flex group">Get started <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" /></Link>
                  </div>
                  <div className="space-y-2.5">
                    {tabs[activeTab].features.map((feat, i) => (
                      <motion.div key={feat} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.08 }} className="flex items-center gap-3 rounded-xl border border-border/40 bg-card/50 backdrop-blur-sm px-4 py-3">
                        <CheckCircle2 className="w-4 h-4 text-gold flex-shrink-0" /><span className="text-sm font-medium text-foreground">{feat}</span>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>
          </Reveal>
        </div>
      </section>

      {/* ═══ Features — editorial list ═════════════════════════════ */}
      <section id="features" className="relative z-10 py-14 md:py-20">
        <div className="max-w-4xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Under the hood</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Powered by <span className="italic font-reading text-gold">real intelligence</span>
            </h2>
          </Reveal>
          <div className="space-y-4">
            {[
              { icon: Upload, title: 'Smart ingestion', desc: 'PDFs, slides, DOCX parsed into structured chunks with concept extraction and knowledge-base indexing.' },
              { icon: Brain, title: 'Socratic tutoring', desc: 'The AI asks questions instead of lecturing. Responses adapt to your mastery and always cite your sources.' },
              { icon: Target, title: 'Adaptive study maps', desc: 'Concept graphs and learning objectives built automatically. The system knows what to teach next.' },
              { icon: PenTool, title: 'Artifact generation', desc: 'Flashcards, quizzes, revision plans generated from your sessions — not generic templates.' },
              { icon: BarChart3, title: 'Mastery tracking', desc: 'Concept-level progress, weak areas, and recommendations — visible during study.' },
              { icon: Shield, title: 'Privacy-first', desc: 'Your data is never sold. BYOK support. Consent management built in.' },
            ].map((f, i) => (
              <Reveal key={f.title} delay={i * 0.04}>
                <div className="group flex items-start gap-5 rounded-2xl border border-border/40 hover:border-gold/20 bg-card/40 hover:bg-card/60 backdrop-blur-sm p-5 transition-all duration-300">
                  <div className="w-10 h-10 rounded-xl bg-gold/8 border border-gold/15 flex items-center justify-center flex-shrink-0 group-hover:bg-gold/12 transition-colors">
                    <f.icon className="w-5 h-5 text-gold" />
                  </div>
                  <div>
                    <h3 className="font-display text-base font-semibold text-foreground mb-1 tracking-tight">{f.title}</h3>
                    <p className="text-[0.82rem] text-muted-foreground leading-relaxed">{f.desc}</p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ Editorial differentiators ═════════════════════════════ */}
      <section className="relative z-10 py-12 md:py-16 border-y border-border/30">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <div className="grid md:grid-cols-3 gap-8 text-center">
            {[
              { icon: Star, stat: '100%', label: 'Source-grounded', desc: 'Every answer cites your uploaded materials' },
              { icon: Lightbulb, stat: 'Socratic', label: 'Active recall', desc: 'The tutor asks you questions first' },
              { icon: Sparkles, stat: '6+', label: 'Artifact types', desc: 'Generated from your sessions' },
            ].map((item, i) => (
              <Reveal key={item.label} delay={i * 0.08}>
                <div className="space-y-3">
                  <div className="w-11 h-11 rounded-xl bg-gold/10 border border-gold/15 flex items-center justify-center mx-auto"><item.icon className="w-5 h-5 text-gold" /></div>
                  <p className="font-display text-3xl font-semibold text-foreground">{item.stat}</p>
                  <p className="font-ui text-xs font-semibold uppercase tracking-wider text-gold/70">{item.label}</p>
                  <p className="text-sm text-muted-foreground">{item.desc}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ═══ Final CTA ═════════════════════════════════════════════ */}
      <section className="relative z-10 py-14 md:py-20">
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
                  Upload your materials and experience AI tutoring grounded in your own sources.
                </p>
                <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                  <Link to="/register" className="landing-hero-cta group"><span>Create free account</span><ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" /></Link>
                  <Link to="/login" className="landing-hero-secondary group"><span>Sign in</span><ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-gold transition-colors" /></Link>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ═══ Research + Footer ═════════════════════════════════════ */}
      <section className="relative z-10 pb-8">
        <Reveal>
          <div className="max-w-3xl mx-auto px-6 lg:px-8">
            <div className="landing-research-notice">
              <div className="flex items-center gap-2 justify-center mb-2">
                <GraduationCap className="w-4 h-4 text-gold/60" />
                <span className="font-ui text-xs uppercase tracking-[0.2em] text-gold/70 font-medium">Academic Research Project</span>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed max-w-xl mx-auto text-center">
                StudyAgent is an academic research project. Your data is never sold. Opt in to anonymized research during registration.
              </p>
            </div>
          </div>
        </Reveal>
      </section>
      <footer className="relative z-10 border-t border-border/30 py-8 px-6 lg:px-8">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gold/10 border border-gold/15 flex items-center justify-center"><Sparkles className="w-3.5 h-3.5 text-gold" /></div>
            <div><span className="font-display text-base font-semibold text-foreground">StudyAgent</span><p className="text-xs text-muted-foreground">AI-powered notebook tutoring</p></div>
          </div>
          <div className="flex items-center gap-8 text-sm text-muted-foreground">
            <Link to="/register" className="hover:text-foreground transition-colors">Create account</Link>
            <Link to="/login" className="hover:text-foreground transition-colors">Sign in</Link>
            <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 hover:text-foreground transition-colors"><Github className="w-3.5 h-3.5" /> Source</a>
          </div>
          <p className="text-xs text-muted-foreground/60">&copy; {new Date().getFullYear()} StudyAgent. MIT License.</p>
        </div>
      </footer>
    </div>
  );
}
