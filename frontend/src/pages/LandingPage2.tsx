import { Link } from 'react-router-dom';
import { useRef, useState } from 'react';
import { motion, useScroll, useTransform, AnimatePresence } from 'framer-motion';
import {
  Sparkles, Brain, ArrowRight, Github,
  Upload, GraduationCap, Target, BarChart3,
  PenTool, Zap, Shield, Star, Lightbulb,
  ChevronRight, Play, Users, CheckCircle2,
  Building2, Map,
} from 'lucide-react';
import {
  Reveal, FloatingParticles, AnimatedNumber,
  PipelineAnimation, PersonalizationShowcase,
  AdaptivePathAnimation, MasteryRadial,
  StudyMapIllustration, ConceptCluster,
} from '../components/landing/LandingAssets';

/* ─── Bento card ──────────────────────────────────────────────── */
function BentoCard({ icon: Icon, title, desc, span = false }: { icon: typeof Sparkles; title: string; desc: string; span?: boolean }) {
  return (
    <motion.div whileHover={{ y: -3 }} className={`group relative overflow-hidden rounded-2xl border border-border/60 bg-card/60 backdrop-blur-sm hover:border-gold/25 p-5 transition-colors duration-300 ${span ? 'md:col-span-2' : ''}`}>
      <div className="absolute inset-0 bg-gradient-to-br from-gold/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      <div className="relative">
        <div className="w-10 h-10 rounded-xl bg-gold/8 border border-gold/15 flex items-center justify-center mb-3">
          <Icon className="w-5 h-5 text-gold" />
        </div>
        <h3 className="font-display text-base font-semibold mb-1.5 text-foreground tracking-tight">{title}</h3>
        <p className="text-[0.82rem] text-muted-foreground leading-relaxed">{desc}</p>
      </div>
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   LANDING PAGE v2 — "Journey" variant
   Split-screen hero, pipeline strip, study-map focus, bento features
   ═══════════════════════════════════════════════════════════════════ */
export default function LandingPage2() {
  const heroRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ['start start', 'end start'] });
  const heroY = useTransform(scrollYProgress, [0, 1], [0, 100]);
  const heroOpacity = useTransform(scrollYProgress, [0, 0.7], [1, 0]);
  const [activeTab, setActiveTab] = useState(0);

  const tabs = [
    { label: 'Students', icon: GraduationCap, title: 'Your AI-powered study partner', desc: 'Upload course materials and learn through Socratic dialogue. The tutor adapts to what you know and generates artifacts from your actual sources.', features: ['Adaptive sessions that match your pace', 'Flashcards & quizzes from your material', 'Concept-level mastery tracking', 'Pick up where you left off'] },
    { label: 'Teachers', icon: Users, title: 'Understand how your students learn', desc: 'Organize content into notebooks. See which concepts students struggle with, review AI-generated artifacts, and guide focus areas.', features: ['Structure courses as notebooks', 'Concept-level progress visibility', 'Identify stuck points', 'Review AI-generated artifacts'] },
    { label: 'Institutes', icon: Building2, title: 'AI tutoring for your campus', desc: 'Deploy source-grounded, privacy-first tutoring across departments. Full consent management, BYOK support, and research data opt-in.', features: ['Privacy-first with consent controls', 'BYOK for data ownership', 'Research-grade analytics', 'Scales across departments'] },
  ];

  return (
    <div className="landing-root">
      <FloatingParticles />

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
            <a href="#journey" className="text-muted-foreground hover:text-foreground transition-colors">Your journey</a>
            <a href="#personalize" className="text-muted-foreground hover:text-foreground transition-colors">Personalization</a>
            <a href="#audience" className="text-muted-foreground hover:text-foreground transition-colors">For you</a>
            <a href="#features" className="text-muted-foreground hover:text-foreground transition-colors">Features</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link to="/login" className="px-5 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors hidden sm:inline-flex">Sign in</Link>
            <Link to="/register" className="landing-cta-btn group">Get started free <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" /></Link>
          </div>
        </div>
      </motion.header>

      {/* ═══ Split-screen Hero ═════════════════════════════════════ */}
      <section ref={heroRef} className="relative z-10 pt-16 pb-8 md:pt-24 md:pb-12">
        <div className="landing-hero-glow" />
        <motion.div style={{ y: heroY, opacity: heroOpacity }} className="max-w-6xl mx-auto px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-10 lg:gap-14 items-center">
            <div className="flex flex-col">
              <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5, delay: 0.1 }} className="landing-badge mb-5 self-start">
                <Zap className="w-3.5 h-3.5 text-gold" /><span>AI-Powered Notebook Tutoring</span>
              </motion.div>
              <motion.h1 initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }} className="landing-hero-title text-foreground mb-5">
                Your learning,{' '}<span className="landing-gradient-text italic font-reading">your path</span>
              </motion.h1>
              <motion.p initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.35 }} className="reading-copy text-lg text-muted-foreground leading-relaxed mb-8 max-w-lg">
                Upload your materials. StudyAgent maps your concepts, builds a personalized study plan, and guides you with adaptive Socratic tutoring — grounded entirely in your sources.
              </motion.p>
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.5 }} className="flex flex-col sm:flex-row items-start gap-3 mb-8">
                <Link to="/register" className="landing-hero-cta group"><span>Start learning free</span><ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-300" /></Link>
                <Link to="/login" className="landing-hero-secondary group"><Play className="w-3.5 h-3.5 text-gold" /><span>Sign in</span></Link>
              </motion.div>
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.7 }} className="flex gap-8">
                {[{ val: 100, suffix: '%', label: 'Source-grounded' }, { val: 6, suffix: '+', label: 'Artifact types' }, { val: 5, suffix: '', label: 'Study stages' }].map(({ val, suffix, label }) => (
                  <div key={label} className="text-center">
                    <p className="font-display text-2xl font-semibold text-foreground"><AnimatedNumber value={val} suffix={suffix} /></p>
                    <p className="text-[10px] text-muted-foreground font-ui uppercase tracking-wider mt-0.5">{label}</p>
                  </div>
                ))}
              </motion.div>
            </div>
            <motion.div initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 1, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}>
              <StudyMapIllustration className="w-full" />
            </motion.div>
          </div>
        </motion.div>
      </section>

      {/* ═══ Pipeline strip ════════════════════════════════════════ */}
      <section className="relative z-10 py-8 border-y border-border/30">
        <Reveal className="max-w-4xl mx-auto px-6 lg:px-8">
          <PipelineAnimation />
        </Reveal>
      </section>

      {/* ═══ Learning Journey — Study Map + Adaptive ═══════════════ */}
      <section id="journey" className="relative z-10 py-14 md:py-20">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Your learning journey</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              A study path that <span className="italic font-reading text-gold">adapts to you</span>
            </h2>
            <p className="reading-copy text-muted-foreground text-base max-w-xl mx-auto">
              We don't just chat about your documents. We build a study map and guide you concept by concept.
            </p>
          </Reveal>

          <div className="grid md:grid-cols-2 gap-10 items-center mb-14">
            <Reveal>
              <div className="space-y-4">
                <div className="w-11 h-11 rounded-xl bg-gold/10 border border-gold/20 flex items-center justify-center"><Map className="w-5 h-5 text-gold" /></div>
                <h3 className="font-display text-xl font-semibold text-foreground tracking-tight">Dynamic Study Maps</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Your materials are analyzed to create a concept graph. We identify prerequisites, map relationships, and build a visual journey tailored to your content.
                </p>
                <ul className="space-y-2 pt-2">
                  {['Automated concept extraction', 'Prerequisite mapping', 'Visual progress tracking'].map((item) => (
                    <li key={item} className="flex items-center gap-2.5 text-sm text-foreground/80"><CheckCircle2 className="w-3.5 h-3.5 text-gold" />{item}</li>
                  ))}
                </ul>
              </div>
            </Reveal>
            <Reveal delay={0.15}>
              <ConceptCluster />
            </Reveal>
          </div>

          <div className="grid md:grid-cols-2 gap-10 items-center">
            <Reveal className="order-2 md:order-1">
              <AdaptivePathAnimation />
            </Reveal>
            <Reveal delay={0.15} className="order-1 md:order-2">
              <div className="space-y-4">
                <div className="w-11 h-11 rounded-xl bg-gold/10 border border-gold/20 flex items-center justify-center"><Target className="w-5 h-5 text-gold" /></div>
                <h3 className="font-display text-xl font-semibold text-foreground tracking-tight">Adaptive Tutoring</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  The AI guides your learning — assessing mastery, identifying gaps, and dynamically adjusting difficulty and focus for each session.
                </p>
                <ul className="space-y-2 pt-2">
                  {['Real-time mastery assessment', 'Targeted remediation', 'Personalized pacing'].map((item) => (
                    <li key={item} className="flex items-center gap-2.5 text-sm text-foreground/80"><CheckCircle2 className="w-3.5 h-3.5 text-gold" />{item}</li>
                  ))}
                </ul>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ═══ Personalization showcase ══════════════════════════════ */}
      <section id="personalize" className="relative z-10 py-14 md:py-20 landing-workspace-section">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Personalized learning</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Every learner gets a <span className="italic font-reading text-gold">unique experience</span>
            </h2>
          </Reveal>
          <div className="grid md:grid-cols-2 gap-5">
            <Reveal><PersonalizationShowcase className="h-full" /></Reveal>
            <Reveal delay={0.1}><MasteryRadial className="h-full" /></Reveal>
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

      {/* ═══ Bento features ════════════════════════════════════════ */}
      <section id="features" className="relative z-10 py-14 md:py-20">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <Reveal className="text-center mb-10">
            <span className="section-kicker text-[11px] text-gold font-medium mb-3 block">Under the hood</span>
            <h2 className="editorial-title text-3xl md:text-4xl text-foreground mb-3">
              Powered by <span className="italic font-reading text-gold">real intelligence</span>
            </h2>
          </Reveal>
          <div className="grid md:grid-cols-2 gap-4">
            <Reveal><BentoCard icon={Upload} title="Smart ingestion" desc="PDFs, slides, DOCX parsed into structured chunks with concept extraction and knowledge-base indexing." span /></Reveal>
            <Reveal delay={0.05}><BentoCard icon={Brain} title="Socratic tutoring" desc="The AI asks questions instead of lecturing. Responses adapt to your mastery and cite sources." span /></Reveal>
            <Reveal delay={0.1}><BentoCard icon={Target} title="Adaptive study maps" desc="Concept graphs and objectives built automatically. The system knows what to teach next." /></Reveal>
            <Reveal delay={0.15}><BentoCard icon={PenTool} title="Artifact generation" desc="Flashcards, quizzes, revision plans from your sessions." /></Reveal>
            <Reveal delay={0.2}><BentoCard icon={BarChart3} title="Mastery tracking" desc="Concept-level progress and next-step recommendations." /></Reveal>
            <Reveal delay={0.25}><BentoCard icon={Shield} title="Privacy-first" desc="BYOK support. Data never sold. Consent management built in." /></Reveal>
          </div>
        </div>
      </section>

      {/* ═══ Differentiators ═══════════════════════════════════════ */}
      <section className="relative z-10 py-12 md:py-16">
        <div className="max-w-5xl mx-auto px-6 lg:px-8">
          <div className="grid md:grid-cols-3 gap-5">
            {[
              { icon: Star, quote: 'Every answer cites your uploaded materials. No hallucinations.', label: 'Source-grounded AI' },
              { icon: Lightbulb, quote: 'Active recall and Socratic method by default.', label: 'Socratic method' },
              { icon: Sparkles, quote: 'Artifacts generated from sessions — not templates.', label: 'Your artifacts' },
            ].map((item, i) => (
              <Reveal key={item.label} delay={i * 0.08}>
                <div className="landing-diff-card">
                  <div className="w-10 h-10 rounded-xl bg-gold/10 border border-gold/15 flex items-center justify-center mb-4"><item.icon className="w-5 h-5 text-gold" /></div>
                  <p className="reading-copy text-foreground text-[0.88rem] leading-relaxed mb-3 italic">"{item.quote}"</p>
                  <span className="font-ui text-xs font-semibold uppercase tracking-wider text-gold/70">{item.label}</span>
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
                  Upload your materials and experience AI tutoring grounded in your own sources. Free to start.
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
