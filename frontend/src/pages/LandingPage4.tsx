import { Link } from 'react-router-dom';
import { useRef, useState } from 'react';
import { motion, useScroll, useTransform, AnimatePresence } from 'framer-motion';
import {
  Sparkles, Brain, ArrowRight, Github,
  Upload, GraduationCap, Target,
  PenTool, Zap, Shield,
  ChevronRight, Users, CheckCircle2,
  Building2, Network, FileText, Map,
} from 'lucide-react';
import {
  Reveal, FloatingParticles, AnimatedNumber,
  HowItWorksTimeline, PipelineAnimation,
  PersonalizationShowcase, AdaptivePathAnimation,
  MasteryRadial, StudyMapIllustration, ConceptCluster,
} from '../components/landing/LandingAssets';

/* ═══════════════════════════════════════════════════════════════════
   LANDING PAGE v4 — "Technical" variant
   Data-heavy hero with animated stats, pipeline-centric storytelling,
   dashboard-style sections, concept graph focus, technical features
   ═══════════════════════════════════════════════════════════════════ */
export default function LandingPage4() {
  const heroRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ['start start', 'end start'] });
  const heroY = useTransform(scrollYProgress, [0, 1], [0, 90]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.65], [1, 0]);
  const [activeTab, setActiveTab] = useState(0);

  const tabs = [
    { label: 'Students', icon: GraduationCap, title: 'Your AI-powered study partner', desc: 'Upload course materials and learn through Socratic dialogue. The tutor adapts to what you know and generates artifacts from your sources.', features: ['Adaptive sessions matching your pace', 'Flashcards & quizzes from your material', 'Concept-level mastery tracking', 'Resume where you left off'] },
    { label: 'Teachers', icon: Users, title: 'Understand how students learn', desc: 'Organize content into notebooks. See concept-level struggles, review AI artifacts, and guide focus areas with real session data.', features: ['Notebook-based course structure', 'Concept-level progress visibility', 'Identify weak areas', 'Review AI-generated artifacts'] },
    { label: 'Institutes', icon: Building2, title: 'Campus-wide AI tutoring', desc: 'Privacy-first, source-grounded tutoring at scale. BYOK support, consent management, and research-grade analytics.', features: ['Full consent controls', 'BYOK data ownership', 'Research-grade analytics', 'Department-wide scaling'] },
  ];

  return (
    <div className="landing-root">
      <FloatingParticles count={12} />

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
            <a href="#pipeline" className="text-muted-foreground hover:text-foreground transition-colors">Pipeline</a>
            <a href="#knowledge" className="text-muted-foreground hover:text-foreground transition-colors">Knowledge graph</a>
            <a href="#audience" className="text-muted-foreground hover:text-foreground transition-colors">For you</a>
            <a href="#architecture" className="text-muted-foreground hover:text-foreground transition-colors">Architecture</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link to="/login" className="px-5 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors hidden sm:inline-flex">Sign in</Link>
            <Link to="/register" className="landing-cta-btn group">Get started free <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" /></Link>
          </div>
        </div>
      </motion.header>

      {/* ═══ Hero — data-centric with stats ════════════════════════ */}
      <section ref={heroRef} className="relative z-10 pt-16 pb-6 md:pt-24 md:pb-10">
        <div className="landing-hero-glow" />
        <motion.div style={{ y: heroY, opacity: heroOpacity }} className="max-w-6xl mx-auto px-6 lg:px-8">
          <div className="flex flex-col items-center text-center">
            <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5, delay: 0.1 }} className="landing-badge mb-5">
              <Zap className="w-3.5 h-3.5 text-gold" /><span>Full-stack AI Learning Pipeline</span>
            </motion.div>
            <motion.h1 initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }} className="landing-hero-title text-foreground mb-5 max-w-[850px]">
              From raw PDF to{' '}<span className="landing-gradient-text italic font-reading">concept mastery</span>
            </motion.h1>
            <motion.p initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.35 }} className="reading-copy text-lg text-muted-foreground max-w-2xl leading-relaxed mb-8">
              A six-stage pipeline: parse documents, extract concepts, build knowledge graphs, plan curricula, tutor adaptively, and generate study artifacts — all grounded in your sources.
            </motion.p>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.5 }} className="flex flex-col sm:flex-row items-center gap-4 mb-10">
              <Link to="/register" className="landing-hero-cta group"><span>Start learning free</span><ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" /></Link>
              <Link to="/login" className="landing-hero-secondary group"><span>Sign in</span><ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-gold transition-colors" /></Link>
            </motion.div>

            {/* Dashboard stats row */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.65 }} className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full max-w-3xl">
              {[
                { val: 6, suffix: '', label: 'Pipeline stages', icon: Network },
                { val: 100, suffix: '%', label: 'Source-grounded', icon: FileText },
                { val: 6, suffix: '+', label: 'Artifact types', icon: PenTool },
                { val: 5, suffix: '', label: 'Mastery levels', icon: Target },
              ].map(({ val, suffix, label, icon: Icon }) => (
                <div key={label} className="rounded-xl border border-border/50 bg-card/40 backdrop-blur-sm p-4 text-center">
                  <Icon className="w-4 h-4 text-gold/60 mx-auto mb-2" />
                  <p className="font-display text-2xl font-semibold text-foreground"><AnimatedNumber value={val} suffix={suffix} /></p>
                  <p className="text-[10px] text-muted-foreground font-ui uppercase tracking-wider mt-1">{label}</p>
                </div>
              ))}
            </motion.div>
          </div>
        </motion.div>
      </section>

      {/* ═══ Pipeline — central focus ══════════════════════════════ */}
      <section id="pipeline" className="relative z-10 py-12 md:py-16">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-8">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">The pipeline</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Six stages from <span className="italic font-reading text-gold">upload to mastery</span>
            </h2>
          </Reveal>
          <Reveal>
            <PipelineAnimation />
          </Reveal>
        </div>
      </section>

      {/* ═══ How It Works — timeline + study map ═══════════════════ */}
      <section className="relative z-10 py-14 md:py-20 landing-workspace-section">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Under the hood</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              How the <span className="italic font-reading text-gold">learning engine</span> works
            </h2>
          </Reveal>
          <div className="grid lg:grid-cols-2 gap-10 items-start">
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

      {/* ═══ Knowledge Graph + Concept Cluster ════════════════════ */}
      <section id="knowledge" className="relative z-10 py-14 md:py-20">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Knowledge graph</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Your content becomes a <span className="italic font-reading text-gold">concept graph</span>
            </h2>
            <p className="reading-copy text-muted-foreground text-base max-w-xl mx-auto">
              Concepts are extracted, prerequisites mapped, and relationships built into a navigable knowledge graph that powers adaptive tutoring.
            </p>
          </Reveal>
          <div className="grid md:grid-cols-2 gap-5">
            <Reveal>
              <ConceptCluster className="h-full" />
            </Reveal>
            <Reveal delay={0.1}>
              <div className="space-y-5 h-full flex flex-col">
                <PersonalizationShowcase className="flex-1" />
                <AdaptivePathAnimation className="flex-1" />
              </div>
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

      {/* ═══ Architecture features — technical grid ════════════════ */}
      <section id="architecture" className="relative z-10 py-14 md:py-20">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Architecture</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Built with <span className="italic font-reading text-gold">precision</span>
            </h2>
          </Reveal>
          <div className="grid md:grid-cols-2 gap-4">
            {[
              { icon: Upload, title: 'Document parsing', desc: 'Docling-powered extraction of structure, headings, tables, and figures from PDFs, slides, and DOCX files.', tag: 'Stage 1-2' },
              { icon: Network, title: 'Concept extraction', desc: 'LLM-powered ontology builds concept graphs with prerequisites, relationships, and learning objectives.', tag: 'Stage 3' },
              { icon: Map, title: 'Curriculum planning', desc: 'Automated study plans with sequenced learning objectives, scope management, and adaptive pacing.', tag: 'Stage 4' },
              { icon: Brain, title: 'Socratic runtime', desc: 'Multi-agent tutor with policy-led progression, mastery evaluation, and source-grounded retrieval.', tag: 'Stage 5' },
              { icon: PenTool, title: 'Artifact engine', desc: 'Flashcards, quizzes, summaries, and revision plans generated contextually from session dialogue.', tag: 'Stage 6' },
              { icon: Shield, title: 'Privacy & consent', desc: 'BYOK model support, data consent management, anonymized research opt-in, and zero data selling.', tag: 'Platform' },
            ].map((f, i) => (
              <Reveal key={f.title} delay={i * 0.05}>
                <div className="group rounded-2xl border border-border/50 hover:border-gold/20 bg-card/40 hover:bg-card/60 backdrop-blur-sm p-5 transition-all duration-300">
                  <div className="flex items-center justify-between mb-3">
                    <div className="w-9 h-9 rounded-lg bg-gold/8 border border-gold/15 flex items-center justify-center group-hover:bg-gold/12 transition-colors">
                      <f.icon className="w-4 h-4 text-gold" />
                    </div>
                    <span className="text-[10px] font-mono font-medium text-gold/50 uppercase tracking-wider">{f.tag}</span>
                  </div>
                  <h3 className="font-display text-base font-semibold text-foreground mb-1.5 tracking-tight">{f.title}</h3>
                  <p className="text-[0.82rem] text-muted-foreground leading-relaxed">{f.desc}</p>
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
                  Upload your materials and experience the full AI learning pipeline. Free to start.
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
