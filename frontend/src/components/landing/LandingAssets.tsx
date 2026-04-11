import { useRef, useEffect, useState, type ReactNode } from 'react';
import { motion, useInView, AnimatePresence } from 'framer-motion';
import {
  Brain, Target, Upload, BarChart3,
  PenTool, Zap, Map, User, TrendingUp,
  FileText, Network, GraduationCap,
} from 'lucide-react';

/* ═══ Shared utilities ════════════════════════════════════════════ */

export function Reveal({ children, delay = 0, className = '' }: { children: ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-60px' });
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 32 }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 32 }}
      transition={{ duration: 0.7, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function FloatingParticles({ count = 14 }: { count?: number }) {
  return (
    <div className="landing-particles">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="landing-particle"
          style={{
            left: `${Math.random() * 100}%`,
            top: `${Math.random() * 100}%`,
            animationDelay: `${Math.random() * 8}s`,
            animationDuration: `${12 + Math.random() * 10}s`,
            width: `${2 + Math.random() * 3}px`,
            height: `${2 + Math.random() * 3}px`,
          }}
        />
      ))}
    </div>
  );
}

export function AnimatedNumber({ value, suffix = '' }: { value: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true });
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    if (!isInView) return;
    let start = 0;
    const step = Math.max(1, Math.floor(value / 40));
    const timer = setInterval(() => {
      start += step;
      if (start >= value) { setDisplay(value); clearInterval(timer); }
      else setDisplay(start);
    }, 30);
    return () => clearInterval(timer);
  }, [isInView, value]);
  return <span ref={ref}>{display}{suffix}</span>;
}

/* ═══ Study Map — hub-spoke radial layout ═════════════════════════ */

export function StudyMapIllustration({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-40px' });

  /* Hand-placed positions for a balanced hexagonal layout in a 5:4 container */
  const centerX = 50;
  const centerY = 46;

  const outerNodes = [
    { icon: Upload, label: 'Upload', x: 15, y: 58 },
    { icon: FileText, label: 'Parse', x: 22, y: 22 },
    { icon: Network, label: 'Concepts', x: 50, y: 10 },
    { icon: Map, label: 'Study Map', x: 78, y: 22 },
    { icon: Target, label: 'Mastery', x: 85, y: 58 },
    { icon: TrendingUp, label: 'Adapt', x: 50, y: 78 },
  ];

  /* Ordered ring connections (outer-to-outer) */
  const ringEdges: [number, number][] = [[0,1],[1,2],[2,3],[3,4],[4,5],[5,0]];

  return (
    <div ref={ref} className={`relative w-full aspect-[5/4] rounded-2xl border border-border/40 bg-card/20 backdrop-blur-sm overflow-hidden ${className}`}>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,hsl(155_28%_38%_/_0.06)_0%,transparent_70%)]" />

      {/* SVG edges */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none">
        {/* Hub-to-spoke lines */}
        {outerNodes.map((node, i) => (
          <motion.line
            key={`hub-${i}`}
            x1={`${centerX}%`} y1={`${centerY}%`}
            x2={`${node.x}%`} y2={`${node.y}%`}
            stroke="hsl(155 28% 38% / 0.25)"
            strokeWidth="1.5"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={isInView ? { pathLength: 1, opacity: 1 } : {}}
            transition={{ duration: 0.6, delay: 0.2 + i * 0.08 }}
          />
        ))}
        {/* Ring connections */}
        {ringEdges.map(([a, b], i) => (
          <motion.line
            key={`ring-${i}`}
            x1={`${outerNodes[a].x}%`} y1={`${outerNodes[a].y}%`}
            x2={`${outerNodes[b].x}%`} y2={`${outerNodes[b].y}%`}
            stroke="hsl(155 28% 38% / 0.12)"
            strokeWidth="1"
            strokeDasharray="4 4"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={isInView ? { pathLength: 1, opacity: 1 } : {}}
            transition={{ duration: 0.5, delay: 0.6 + i * 0.06 }}
          />
        ))}
      </svg>

      {/* Center hub — AI Tutor */}
      <motion.div
        className="absolute flex flex-col items-center gap-1.5"
        style={{ left: `${centerX}%`, top: `${centerY}%`, transform: 'translate(-50%, -50%)' }}
        initial={{ opacity: 0, scale: 0 }}
        animate={isInView ? { opacity: 1, scale: 1 } : {}}
        transition={{ type: 'spring', stiffness: 260, damping: 20, delay: 0.1 }}
      >
        <motion.div
          animate={{ boxShadow: ['0 0 0px hsl(155 28% 38% / 0)', '0 0 28px hsl(155 28% 38% / 0.3)', '0 0 0px hsl(155 28% 38% / 0)'] }}
          transition={{ duration: 3, repeat: Infinity }}
          className="rounded-full flex items-center justify-center border-2 border-gold/40 bg-gold/15"
          style={{ width: 56, height: 56 }}
        >
          <Brain style={{ width: 26, height: 26 }} className="text-gold" />
        </motion.div>
        <span className="text-[11px] font-ui font-semibold text-foreground whitespace-nowrap">AI Tutor</span>
      </motion.div>

      {/* Outer nodes */}
      {outerNodes.map((node, i) => (
        <motion.div
          key={node.label}
          className="absolute flex flex-col items-center gap-1"
          style={{ left: `${node.x}%`, top: `${node.y}%`, transform: 'translate(-50%, -50%)' }}
          initial={{ opacity: 0, scale: 0 }}
          animate={isInView ? { opacity: 1, scale: 1 } : {}}
          transition={{ type: 'spring', stiffness: 260, damping: 20, delay: 0.15 + i * 0.1 }}
        >
          <div className="rounded-full flex items-center justify-center border border-gold/25 bg-gold/8" style={{ width: 44, height: 44 }}>
            <node.icon style={{ width: 20, height: 20 }} className="text-gold" />
          </div>
          <span className="text-[11px] font-ui font-medium text-muted-foreground whitespace-nowrap">{node.label}</span>
        </motion.div>
      ))}

      {/* Animated data particles along hub spokes */}
      {outerNodes.map((node, i) => (
        <motion.div
          key={`particle-${i}`}
          className="absolute w-1.5 h-1.5 rounded-full bg-gold/60"
          animate={{
            left: [`${centerX}%`, `${node.x}%`],
            top: [`${centerY}%`, `${node.y}%`],
            opacity: [0, 1, 0],
          }}
          transition={{ duration: 2, delay: i * 0.5, repeat: Infinity, ease: 'linear' }}
        />
      ))}
    </div>
  );
}


/* ═══ Adaptive Path — personalization journey ═════════════════════ */

export function AdaptivePathAnimation({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-40px' });
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!isInView) return;
    const timer = setInterval(() => setStep(s => (s + 1) % 4), 2200);
    return () => clearInterval(timer);
  }, [isInView]);

  const steps = [
    { icon: User, label: 'Assess your level', color: 'bg-blue-500/15 border-blue-500/25 text-blue-400' },
    { icon: Map, label: 'Build study map', color: 'bg-gold/15 border-gold/25 text-gold' },
    { icon: Brain, label: 'Adaptive tutoring', color: 'bg-purple-500/15 border-purple-500/25 text-purple-400' },
    { icon: Target, label: 'Track mastery', color: 'bg-emerald-500/15 border-emerald-500/25 text-emerald-400' },
  ];

  return (
    <div ref={ref} className={`relative w-full rounded-2xl border border-border/40 bg-card/20 backdrop-blur-sm p-6 overflow-hidden ${className}`}>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,hsl(155_28%_38%_/_0.05)_0%,transparent_60%)]" />

      {/* Progress bar */}
      <div className="relative h-1.5 rounded-full bg-border/20 mb-6 overflow-hidden">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-gold/60 to-gold"
          animate={{ width: `${((step + 1) / 4) * 100}%` }}
          transition={{ duration: 0.5 }}
        />
      </div>

      {/* Steps */}
      <div className="grid grid-cols-4 gap-2">
        {steps.map((s, i) => (
          <motion.div
            key={s.label}
            animate={{
              opacity: i <= step ? 1 : 0.3,
              scale: i === step ? 1.05 : 1,
            }}
            transition={{ duration: 0.4 }}
            className="flex flex-col items-center gap-2 text-center"
          >
            <div className={`w-10 h-10 rounded-xl border flex items-center justify-center transition-colors ${
              i <= step ? s.color : 'bg-card/40 border-border/30 text-muted-foreground/40'
            }`}>
              <s.icon className="w-4 h-4" />
            </div>
            <span className={`text-[10px] font-ui font-medium leading-tight ${i <= step ? 'text-foreground' : 'text-muted-foreground/40'}`}>
              {s.label}
            </span>
          </motion.div>
        ))}
      </div>

      {/* Active description */}
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.3 }}
          className="mt-5 rounded-xl bg-card/40 border border-border/30 p-3"
        >
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse" />
            <span className="text-xs font-ui font-semibold text-gold">{steps[step].label}</span>
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            {[
              'Analyzing your responses to understand current knowledge and learning style.',
              'Building a personalized concept map with prerequisites and optimal learning paths.',
              'Adapting questions and explanations in real-time based on your mastery signals.',
              'Tracking concept-level mastery and surfacing what to study next.',
            ][step]}
          </p>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/* ═══ Pipeline visualization — how ingestion works ════════════════ */

const pipelineSteps = [
  { icon: Upload, label: 'Upload', desc: 'PDFs, slides, notes' },
  { icon: FileText, label: 'Parse', desc: 'Structure extraction' },
  { icon: Network, label: 'Concepts', desc: 'Knowledge graph' },
  { icon: Map, label: 'Plan', desc: 'Study objectives' },
  { icon: Brain, label: 'Tutor', desc: 'Socratic dialogue' },
  { icon: PenTool, label: 'Artifacts', desc: 'Cards, quizzes, notes' },
];

export function PipelineAnimation({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-40px' });

  return (
    <div ref={ref} className={`relative ${className}`}>
      <div className="flex items-start justify-between gap-0">
        {pipelineSteps.map((step, i) => (
          <div key={step.label} className="flex items-start flex-1">
            <motion.div
              initial={{ opacity: 0, scale: 0 }}
              animate={isInView ? { opacity: 1, scale: 1 } : {}}
              transition={{ type: 'spring', delay: i * 0.12, stiffness: 260, damping: 20 }}
              className="flex flex-col items-center gap-1.5 flex-shrink-0"
            >
              <motion.div
                whileHover={{ scale: 1.1, y: -2 }}
                className="w-12 h-12 md:w-14 md:h-14 rounded-2xl bg-gold/8 border border-gold/20 flex items-center justify-center group cursor-default"
              >
                <step.icon className="w-5 h-5 md:w-6 md:h-6 text-gold" />
              </motion.div>
              <span className="text-[10px] md:text-xs font-ui font-semibold text-foreground">{step.label}</span>
              <span className="text-[9px] md:text-[10px] text-muted-foreground hidden sm:block">{step.desc}</span>
            </motion.div>

            {i < pipelineSteps.length - 1 && (
              <motion.div
                initial={{ scaleX: 0, opacity: 0 }}
                animate={isInView ? { scaleX: 1, opacity: 1 } : {}}
                transition={{ duration: 0.4, delay: 0.1 + i * 0.12 }}
                className="flex-1 mx-1 md:mx-2"
                style={{ marginTop: '22px' }}
              >
                <div className="h-px bg-gradient-to-r from-gold/30 via-gold/15 to-gold/30 relative">
                  <motion.div
                    className="absolute top-1/2 -translate-y-1/2 w-1 h-1 rounded-full bg-gold/60"
                    animate={{ left: ['0%', '100%'] }}
                    transition={{ duration: 1.5, delay: i * 0.3, repeat: Infinity, ease: 'linear' }}
                  />
                </div>
              </motion.div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ═══ Mastery radial chart ════════════════════════════════════════ */

export function MasteryRadial({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-40px' });

  const concepts = [
    { name: 'Linear Algebra', pct: 85, color: 'hsl(155 35% 45%)' },
    { name: 'Calculus III', pct: 62, color: 'hsl(155 28% 38%)' },
    { name: 'Probability', pct: 41, color: 'hsl(155 20% 50%)' },
    { name: 'Statistics', pct: 73, color: 'hsl(160 30% 42%)' },
  ];

  return (
    <div ref={ref} className={`relative rounded-2xl border border-border/40 bg-card/20 backdrop-blur-sm p-5 ${className}`}>
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 className="w-4 h-4 text-gold/60" />
        <span className="text-xs font-ui font-semibold text-foreground">Mastery Overview</span>
      </div>
      <div className="space-y-3">
        {concepts.map((c, i) => (
          <motion.div
            key={c.name}
            initial={{ opacity: 0, x: -20 }}
            animate={isInView ? { opacity: 1, x: 0 } : {}}
            transition={{ delay: 0.2 + i * 0.1 }}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-foreground">{c.name}</span>
              <span className="text-[10px] font-mono text-gold font-semibold">{c.pct}%</span>
            </div>
            <div className="h-2 rounded-full bg-border/20 overflow-hidden">
              <motion.div
                className="h-full rounded-full"
                style={{ background: c.color }}
                initial={{ width: 0 }}
                animate={isInView ? { width: `${c.pct}%` } : {}}
                transition={{ duration: 0.8, delay: 0.4 + i * 0.1, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ═══ Personalization showcase ════════════════════════════════════ */

export function PersonalizationShowcase({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-40px' });
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (!isInView) return;
    const t = setInterval(() => setActive(a => (a + 1) % 3), 3000);
    return () => clearInterval(t);
  }, [isInView]);

  const profiles = [
    {
      name: 'Visual learner',
      avatar: '🎨',
      detail: 'Prefers diagrams and step-by-step breakdowns. Tutor generates more visual artifacts.',
      mastery: 72,
      style: 'border-purple-400/30 bg-purple-500/5',
    },
    {
      name: 'Quick learner',
      avatar: '⚡',
      detail: 'High prior knowledge. Tutor skips basics, dives into advanced concepts faster.',
      mastery: 89,
      style: 'border-gold/30 bg-gold/5',
    },
    {
      name: 'Methodical learner',
      avatar: '📐',
      detail: 'Needs thorough grounding. Tutor provides more examples and checks understanding.',
      mastery: 55,
      style: 'border-emerald-400/30 bg-emerald-500/5',
    },
  ];

  return (
    <div ref={ref} className={`relative rounded-2xl border border-border/40 bg-card/20 backdrop-blur-sm overflow-hidden ${className}`}>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,hsl(155_28%_38%_/_0.04)_0%,transparent_50%)]" />
      <div className="relative p-5">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="w-4 h-4 text-gold/60" />
          <span className="text-xs font-ui font-semibold text-foreground">Adapts to every learner</span>
        </div>

        <div className="flex gap-2 mb-4">
          {profiles.map((p, i) => (
            <button
              key={p.name}
              onClick={() => setActive(i)}
              className={`flex-1 rounded-lg border p-2.5 text-center transition-all duration-300 cursor-pointer ${
                i === active ? p.style + ' scale-[1.02]' : 'border-border/30 bg-card/30 opacity-50'
              }`}
            >
              <div className="text-lg mb-1">{p.avatar}</div>
              <div className="text-[10px] font-ui font-medium text-foreground leading-tight">{p.name}</div>
            </button>
          ))}
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={active}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="rounded-xl bg-card/40 border border-border/30 p-3"
          >
            <p className="text-[11px] text-muted-foreground leading-relaxed mb-2">{profiles[active].detail}</p>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-full bg-border/20 overflow-hidden">
                <motion.div
                  className="h-full rounded-full bg-gold"
                  initial={{ width: 0 }}
                  animate={{ width: `${profiles[active].mastery}%` }}
                  transition={{ duration: 0.6 }}
                />
              </div>
              <span className="text-[10px] font-mono font-semibold text-gold">{profiles[active].mastery}%</span>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ═══ Vertical timeline for how-it-works ══════════════════════════ */

export function HowItWorksTimeline({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-60px' });

  const steps = [
    { icon: GraduationCap, title: 'Create a notebook', desc: 'Each notebook is a course. Set goals, pick a study mode, and build a workspace that persists across sessions.', accent: false },
    { icon: Upload, title: 'Upload your materials', desc: 'Drop PDFs, slides, or notes. The pipeline extracts structure, builds a concept graph, and indexes a searchable knowledge base.', accent: false },
    { icon: Map, title: 'Get a personalized study map', desc: 'Automatic learning objectives built from your material. The system creates an adaptive path based on concept prerequisites and your goals.', accent: true },
    { icon: Brain, title: 'Learn through Socratic dialogue', desc: 'The tutor adapts in real-time — asking questions, citing your sources, and adjusting difficulty based on your responses.', accent: true },
    { icon: Target, title: 'Track mastery & iterate', desc: 'See concept-level progress, review generated artifacts, identify weak spots, and pick up exactly where you left off.', accent: false },
  ];

  return (
    <div ref={ref} className={`relative ${className}`}>
      {/* Vertical line */}
      <motion.div
        className="absolute left-6 md:left-7 top-0 w-px bg-gradient-to-b from-gold/40 via-gold/20 to-transparent"
        initial={{ height: 0 }}
        animate={isInView ? { height: '100%' } : {}}
        transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
      />

      <div className="space-y-1">
        {steps.map((step, i) => (
          <motion.div
            key={step.title}
            initial={{ opacity: 0, x: -20 }}
            animate={isInView ? { opacity: 1, x: 0 } : {}}
            transition={{ delay: 0.2 + i * 0.15, duration: 0.6 }}
            className="relative flex items-start gap-4 md:gap-5 pl-0"
          >
            {/* Node on the line */}
            <div className={`relative z-10 flex-shrink-0 w-12 h-12 md:w-14 md:h-14 rounded-2xl border flex items-center justify-center ${
              step.accent
                ? 'bg-gold/15 border-gold/30 shadow-[0_0_16px_hsl(155_28%_38%_/_0.15)]'
                : 'bg-card/60 border-border/40'
            }`}>
              <step.icon className={`w-5 h-5 md:w-6 md:h-6 ${step.accent ? 'text-gold' : 'text-muted-foreground'}`} />
            </div>
            <div className="flex-1 pb-8">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-[10px] font-bold text-gold/50 tracking-wider">0{i + 1}</span>
                {step.accent && <span className="text-[9px] font-ui font-bold uppercase tracking-widest text-gold bg-gold/10 px-1.5 py-0.5 rounded">Key</span>}
              </div>
              <h4 className="font-display text-lg md:text-xl font-semibold text-foreground mb-1.5 tracking-tight">{step.title}</h4>
              <p className="text-sm text-muted-foreground leading-relaxed">{step.desc}</p>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ═══ Interactive concept node cluster ════════════════════════════ */

export function ConceptCluster({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-40px' });

  const nodes = [
    { label: 'Vectors', x: 30, y: 25, mastery: 85 },
    { label: 'Matrices', x: 55, y: 18, mastery: 72 },
    { label: 'Eigenvalues', x: 75, y: 35, mastery: 45 },
    { label: 'Linear Maps', x: 45, y: 50, mastery: 60 },
    { label: 'Determinants', x: 20, y: 55, mastery: 90 },
    { label: 'Basis', x: 65, y: 65, mastery: 38 },
    { label: 'Span', x: 35, y: 75, mastery: 78 },
  ];

  const edges = [[0,1],[0,4],[1,2],[1,3],[3,2],[3,5],[4,6],[6,5]];

  return (
    <div ref={ref} className={`relative w-full aspect-[5/4] rounded-2xl border border-border/40 bg-card/20 backdrop-blur-sm overflow-hidden ${className}`}>
      <svg className="absolute inset-0 w-full h-full">
        {edges.map(([a, b], i) => (
          <motion.line
            key={i}
            x1={`${nodes[a].x}%`} y1={`${nodes[a].y}%`}
            x2={`${nodes[b].x}%`} y2={`${nodes[b].y}%`}
            stroke="hsl(155 28% 38% / 0.15)"
            strokeWidth="1.5"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={isInView ? { pathLength: 1, opacity: 1 } : {}}
            transition={{ duration: 0.6, delay: 0.3 + i * 0.05 }}
          />
        ))}
      </svg>

      {nodes.map((node, i) => {
        const masteryColor = node.mastery > 70 ? 'border-emerald-400/40 bg-emerald-500/10' :
                            node.mastery > 50 ? 'border-gold/40 bg-gold/10' :
                            'border-orange-400/40 bg-orange-500/10';
        return (
          <motion.div
            key={node.label}
            className="absolute flex flex-col items-center"
            style={{ left: `${node.x}%`, top: `${node.y}%`, transform: 'translate(-50%, -50%)' }}
            initial={{ opacity: 0, scale: 0 }}
            animate={isInView ? { opacity: 1, scale: 1 } : {}}
            transition={{ type: 'spring', delay: 0.15 + i * 0.08 }}
          >
            <motion.div
              whileHover={{ scale: 1.15 }}
              className={`w-9 h-9 md:w-10 md:h-10 rounded-full border-2 flex items-center justify-center cursor-default ${masteryColor}`}
            >
              <span className="text-[9px] md:text-[10px] font-mono font-bold text-foreground">{node.mastery}</span>
            </motion.div>
            <span className="text-[9px] font-ui font-medium text-muted-foreground mt-1 whitespace-nowrap">{node.label}</span>
          </motion.div>
        );
      })}
    </div>
  );
}
