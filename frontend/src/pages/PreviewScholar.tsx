/**
 * Design Preview V1 — "Scholar"
 *
 * Warm, paper-like, light-mode aesthetic.
 * Newsreader (display) + Source Sans 3 (body).
 * Sage green accent. Walnut sidebar. Cream backgrounds.
 */

import { useState } from 'react';
import {
  Home, NotebookPen, FolderOpen, SlidersHorizontal, Plus,
  BookOpen, ArrowRight, Send, Target, Brain, FileText,
  ExternalLink, StickyNote, PanelLeft, LogOut, CheckCircle2,
  Circle, Loader2, Sparkles, Layers,
} from 'lucide-react';

const themeVars: Record<string, string> = {
  '--background': '42 30% 95%',
  '--foreground': '20 30% 12%',
  '--card': '40 28% 98%',
  '--card-foreground': '20 30% 12%',
  '--popover': '40 28% 98%',
  '--popover-foreground': '20 30% 12%',
  '--primary': '155 28% 38%',
  '--primary-foreground': '0 0% 100%',
  '--secondary': '38 15% 90%',
  '--secondary-foreground': '20 20% 20%',
  '--muted': '38 14% 90%',
  '--muted-foreground': '20 10% 45%',
  '--accent': '155 20% 92%',
  '--accent-foreground': '155 35% 25%',
  '--destructive': '0 60% 48%',
  '--destructive-foreground': '0 0% 100%',
  '--border': '35 12% 82%',
  '--input': '35 12% 82%',
  '--ring': '155 28% 38%',
  '--radius': '0.5rem',
  '--sidebar': '20 30% 8%',
  '--sidebar-foreground': '35 12% 70%',
  '--sidebar-accent': '155 28% 42%',
  '--gold': '155 28% 38%',
  '--gold-muted': '155 15% 55%',
  '--surface': '42 25% 93%',
};

const FONT_DISPLAY = '"Newsreader", Georgia, serif';
const FONT_BODY = '"Source Sans 3", system-ui, sans-serif';

const navItems = [
  { label: 'Studio', icon: Home, active: false },
  { label: 'Notebooks', icon: NotebookPen, active: true },
  { label: 'Resources', icon: FolderOpen, active: false },
  { label: 'Settings', icon: SlidersHorizontal, active: false },
];

const mockNotebooks = [
  { title: 'Linear Algebra', goal: 'Master matrix operations, vector spaces, and eigenvalue decomposition', date: 'Mar 8, 2026', sessions: 12, progress: 68 },
  { title: 'Organic Chemistry', goal: 'Understand reaction mechanisms and functional group transformations', date: 'Mar 5, 2026', sessions: 8, progress: 45 },
  { title: 'Modern History', goal: 'Analyze major geopolitical shifts from 1900–2000', date: 'Feb 28, 2026', sessions: 5, progress: 30 },
];

const mockObjectives = [
  { title: 'Matrix multiplication & properties', status: 'completed' as const, pct: 100 },
  { title: 'Row reduction & echelon forms', status: 'completed' as const, pct: 100 },
  { title: 'Vector spaces & subspaces', status: 'active' as const, pct: 55 },
  { title: 'Eigenvalues & eigenvectors', status: 'pending' as const, pct: 0 },
];

const mockMessages = [
  { role: 'student' as const, text: 'Can you explain how eigenvalues relate to matrix transformations?' },
  { role: 'tutor' as const, text: 'Think of it this way — when you multiply a matrix by a vector, most vectors change both direction and magnitude. But eigenvectors are special: they only get scaled. The eigenvalue tells you that scaling factor.\n\nFor example, if Av = 3v, then v is an eigenvector with eigenvalue 3. The matrix A stretches v by a factor of 3 without rotating it.' },
  { role: 'student' as const, text: 'So an eigenvector with eigenvalue 2 just doubles in length?' },
  { role: 'tutor' as const, text: 'Exactly right. And an eigenvalue of −1 would flip the vector\'s direction while keeping the same length. This geometric interpretation is powerful — it tells you the "natural axes" of a transformation.' },
];

function SidebarMock() {
  return (
    <aside
      className="w-60 flex flex-col shrink-0 border-r"
      style={{
        background: 'hsl(20 30% 8%)',
        borderColor: 'hsl(20 20% 14%)',
        fontFamily: FONT_BODY,
      }}
    >
      <div className="p-5 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'hsl(155 28% 38% / 0.15)', border: '1px solid hsl(155 28% 38% / 0.25)' }}>
            <BookOpen className="w-4 h-4" style={{ color: 'hsl(155 38% 52%)' }} />
          </div>
          <div>
            <h1 style={{ fontFamily: FONT_DISPLAY, color: 'hsl(35 20% 90%)', fontSize: '1.1rem', fontWeight: 600, letterSpacing: '-0.01em' }}>
              StudyAgent
            </h1>
            <p style={{ fontSize: '0.6rem', color: 'hsl(35 10% 50%)', letterSpacing: '0.18em', textTransform: 'uppercase' as const, marginTop: 1 }}>
              Learning companion
            </p>
          </div>
        </div>
      </div>

      <div className="px-3 mb-4">
        <button
          className="flex items-center justify-center gap-2 w-full rounded-lg text-sm font-medium py-2.5"
          style={{ background: 'hsl(155 28% 38% / 0.12)', border: '1px solid hsl(155 28% 38% / 0.2)', color: 'hsl(155 38% 55%)' }}
        >
          <Plus className="w-4 h-4" />
          New Notebook
        </button>
      </div>

      <nav className="flex-1 px-3 space-y-0.5">
        {navItems.map(({ label, icon: Icon, active }) => (
          <div
            key={label}
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium"
            style={{
              background: active ? 'hsl(155 28% 38% / 0.1)' : 'transparent',
              color: active ? 'hsl(155 38% 55%)' : 'hsl(35 10% 55%)',
              border: active ? '1px solid hsl(155 28% 38% / 0.12)' : '1px solid transparent',
            }}
          >
            <Icon className="w-[18px] h-[18px]" />
            {label}
          </div>
        ))}
      </nav>

      <div className="p-4 border-t" style={{ borderColor: 'hsl(20 15% 14%)' }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium" style={{ background: 'hsl(155 28% 38% / 0.12)', color: 'hsl(155 38% 55%)' }}>
            SK
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium truncate" style={{ color: 'hsl(35 15% 85%)' }}>Student</p>
            <p className="text-[11px] truncate" style={{ color: 'hsl(35 8% 45%)' }}>student@university.edu</p>
          </div>
          <LogOut className="w-4 h-4 shrink-0" style={{ color: 'hsl(35 8% 40%)' }} />
        </div>
      </div>
    </aside>
  );
}

function DashboardView() {
  return (
    <div className="p-8 max-w-5xl" style={{ fontFamily: FONT_BODY }}>
      <div className="mb-10">
        <p className="text-xs font-medium mb-3" style={{ color: 'hsl(155 28% 38%)', letterSpacing: '0.2em', textTransform: 'uppercase' as const }}>
          Your workspace
        </p>
        <h1 style={{ fontFamily: FONT_DISPLAY, fontSize: '2.2rem', fontWeight: 600, color: 'hsl(20 30% 12%)', lineHeight: 1.15, letterSpacing: '-0.02em' }}>
          Good evening, <span style={{ fontStyle: 'italic', color: 'hsl(155 30% 32%)' }}>student</span>
        </h1>
        <p className="mt-2" style={{ fontSize: '1rem', color: 'hsl(20 10% 45%)', lineHeight: 1.6, maxWidth: '36rem' }}>
          Continue where you left off, or start a new notebook.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-10">
        {[
          { icon: Plus, title: 'Create Notebook', desc: 'Start a new course container', action: 'New notebook' },
          { icon: BookOpen, title: 'Continue Studying', desc: 'Resume your last session', action: 'Open workspace' },
          { icon: FolderOpen, title: 'Browse Resources', desc: 'Manage uploaded materials', action: 'View library' },
        ].map(({ icon: Icon, title, desc, action }) => (
          <button
            key={title}
            className="group rounded-xl p-5 text-left transition-all duration-200"
            style={{
              background: 'hsl(40 28% 98%)',
              border: '1px solid hsl(35 12% 82%)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'hsl(155 28% 38% / 0.35)';
              e.currentTarget.style.boxShadow = '0 4px 20px hsl(155 28% 38% / 0.06)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'hsl(35 12% 82%)';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            <div className="w-10 h-10 rounded-lg flex items-center justify-center mb-4" style={{ background: 'hsl(155 28% 38% / 0.08)', border: '1px solid hsl(155 28% 38% / 0.15)' }}>
              <Icon className="w-5 h-5" style={{ color: 'hsl(155 28% 38%)' }} />
            </div>
            <p className="text-sm font-semibold mb-1" style={{ color: 'hsl(20 30% 12%)' }}>{title}</p>
            <p className="text-sm mb-3" style={{ color: 'hsl(20 10% 50%)', lineHeight: 1.5 }}>{desc}</p>
            <span className="text-xs font-medium flex items-center gap-1" style={{ color: 'hsl(155 28% 38%)' }}>
              {action} <ArrowRight className="w-3 h-3" />
            </span>
          </button>
        ))}
      </div>

      <div className="mb-3">
        <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: '1.35rem', fontWeight: 500, color: 'hsl(20 30% 12%)' }}>
          Recent notebooks
        </h2>
      </div>
      <div className="grid grid-cols-3 gap-4">
        {mockNotebooks.map((nb) => (
          <div
            key={nb.title}
            className="rounded-xl p-5 transition-all duration-200 cursor-pointer"
            style={{
              background: 'hsl(40 28% 98%)',
              border: '1px solid hsl(35 12% 82%)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'hsl(155 28% 38% / 0.3)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'hsl(35 12% 82%)';
            }}
          >
            <p className="text-sm font-semibold mb-1" style={{ color: 'hsl(20 30% 12%)' }}>{nb.title}</p>
            <p className="text-xs mb-3 line-clamp-2" style={{ color: 'hsl(20 10% 50%)', lineHeight: 1.5 }}>{nb.goal}</p>
            <div className="h-1.5 rounded-full overflow-hidden mb-3" style={{ background: 'hsl(35 12% 88%)' }}>
              <div className="h-full rounded-full" style={{ width: `${nb.progress}%`, background: 'hsl(155 28% 42%)' }} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[11px]" style={{ color: 'hsl(20 8% 55%)' }}>{nb.sessions} sessions</span>
              <span className="text-[11px]" style={{ color: 'hsl(20 8% 55%)' }}>{nb.date}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-10 pt-6 flex gap-8" style={{ borderTop: '1px solid hsl(35 12% 85%)' }}>
        {[
          { label: 'Notebooks', value: '3' },
          { label: 'Resources', value: '14' },
          { label: 'Study hours', value: '28' },
        ].map(({ label, value }) => (
          <div key={label}>
            <p style={{ fontFamily: FONT_DISPLAY, fontSize: '1.5rem', fontWeight: 600, color: 'hsl(20 30% 12%)' }}>{value}</p>
            <p className="text-xs mt-0.5" style={{ color: 'hsl(20 8% 50%)' }}>{label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function WorkspaceView() {
  return (
    <div className="flex h-full" style={{ fontFamily: FONT_BODY }}>
      {/* Left — Study Map */}
      <div className="w-64 shrink-0 overflow-y-auto p-3 space-y-4" style={{ borderRight: '1px solid hsl(35 12% 82%)' }}>
        <div className="flex items-center gap-2 mb-1">
          <FileText className="w-3.5 h-3.5" style={{ color: 'hsl(20 10% 50%)' }} />
          <h3 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'hsl(20 10% 50%)' }}>Resources</h3>
        </div>
        <div className="px-1 py-2.5" style={{ borderBottom: '1px solid hsl(35 12% 86%)' }}>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full shrink-0" style={{ background: 'hsl(155 40% 42%)' }} />
            <span className="text-xs" style={{ color: 'hsl(20 25% 18%)' }}>Linear Algebra — Strang Ch.6</span>
          </div>
        </div>

        <div>
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-3.5 h-3.5" style={{ color: 'hsl(20 10% 50%)' }} />
            <h3 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'hsl(20 10% 50%)' }}>Study Map</h3>
            <span className="text-[10px] ml-auto" style={{ color: 'hsl(20 8% 55%)' }}>2/4</span>
          </div>
          <div className="space-y-0">
            {mockObjectives.map((obj, i) => {
              const Icon = obj.status === 'completed' ? CheckCircle2 : obj.status === 'active' ? Loader2 : Circle;
              const iconColor = obj.status === 'completed' ? 'hsl(155 40% 42%)' : obj.status === 'active' ? 'hsl(155 30% 38%)' : 'hsl(20 6% 70%)';
              const numBg = obj.status === 'completed' ? 'hsl(155 30% 42% / 0.1)' : obj.status === 'active' ? 'hsl(155 28% 38% / 0.1)' : 'hsl(35 10% 92%)';
              const numColor = obj.status === 'completed' ? 'hsl(155 35% 38%)' : obj.status === 'active' ? 'hsl(155 28% 35%)' : 'hsl(20 8% 55%)';
              return (
                <div key={i} className="relative pl-9 pb-3" style={{ borderBottom: '1px solid hsl(35 12% 88%)' }}>
                  <div className="absolute left-0 top-0 flex w-6 flex-col items-center">
                    <div className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-semibold" style={{ background: numBg, color: numColor, border: `1px solid ${numColor}22` }}>
                      {i + 1}
                    </div>
                    {i < mockObjectives.length - 1 && <div className="mt-1 h-full min-h-6 w-px" style={{ background: 'hsl(35 10% 85%)' }} />}
                  </div>
                  <div className="flex items-start gap-1.5 pt-0.5">
                    <Icon className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: iconColor }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs leading-snug" style={{ color: 'hsl(20 25% 15%)' }}>{obj.title}</p>
                      <div className="mt-1.5 h-1 rounded-full overflow-hidden" style={{ background: 'hsl(35 10% 88%)' }}>
                        <div className="h-full rounded-full" style={{ width: `${obj.pct}%`, background: obj.status === 'completed' ? 'hsl(155 35% 42%)' : obj.status === 'active' ? 'hsl(155 28% 38%)' : 'hsl(20 6% 75%)' }} />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div>
          <div className="flex items-center gap-2 mb-2">
            <Brain className="w-3.5 h-3.5" style={{ color: 'hsl(20 10% 50%)' }} />
            <h3 className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'hsl(20 10% 50%)' }}>Mastery</h3>
          </div>
          {['Matrix multiplication', 'Row reduction', 'Span & basis'].map((concept, i) => {
            const score = [92, 85, 55][i];
            return (
              <div key={concept} className="py-1.5">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs" style={{ color: 'hsl(20 15% 25%)' }}>{concept}</span>
                  <span className="text-[10px]" style={{ color: 'hsl(20 8% 55%)' }}>{score}%</span>
                </div>
                <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'hsl(35 10% 88%)' }}>
                  <div className="h-full rounded-full" style={{ width: `${score}%`, background: score >= 70 ? 'hsl(155 35% 42%)' : 'hsl(38 70% 50%)' }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Center — Chat */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="shrink-0 px-5 py-3 flex items-center gap-3" style={{ borderBottom: '1px solid hsl(35 12% 82%)' }}>
          <div className="w-2 h-2 rounded-full" style={{ background: 'hsl(155 35% 42%)' }} />
          <p className="text-xs font-medium" style={{ color: 'hsl(20 25% 15%)' }}>Vector spaces & subspaces</p>
          <span className="text-[10px] rounded-full px-2 py-0.5" style={{ background: 'hsl(155 28% 38% / 0.08)', color: 'hsl(155 30% 32%)' }}>active</span>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5">
          {mockMessages.map((msg, i) => (
            <div key={i} className={msg.role === 'student' ? 'flex justify-end' : ''}>
              <div
                className="max-w-[80%] rounded-xl px-4 py-3"
                style={msg.role === 'student'
                  ? { background: 'hsl(155 28% 38% / 0.08)', border: '1px solid hsl(155 28% 38% / 0.12)' }
                  : { background: 'hsl(40 28% 98%)', border: '1px solid hsl(35 12% 85%)' }
                }
              >
                <p className="text-[10px] font-medium uppercase tracking-wider mb-1.5" style={{ color: 'hsl(20 8% 55%)' }}>
                  {msg.role === 'student' ? 'You' : 'Tutor'}
                </p>
                <p className="text-sm leading-relaxed whitespace-pre-line" style={{ color: 'hsl(20 25% 15%)' }}>
                  {msg.text}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div className="shrink-0 px-5 py-4" style={{ borderTop: '1px solid hsl(35 12% 82%)' }}>
          <div className="flex items-center gap-2 rounded-xl px-4 py-3" style={{ background: 'hsl(40 28% 98%)', border: '1px solid hsl(35 12% 82%)' }}>
            <input
              className="flex-1 bg-transparent text-sm outline-none"
              style={{ color: 'hsl(20 25% 15%)', fontFamily: FONT_BODY }}
              placeholder="Ask a question about the material..."
              readOnly
            />
            <button className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'hsl(155 28% 38%)', color: 'white' }}>
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Right — Notes & Artifacts */}
      <div className="w-72 shrink-0 overflow-y-auto flex flex-col" style={{ borderLeft: '1px solid hsl(35 12% 82%)' }}>
        <div className="px-3 py-3" style={{ borderBottom: '1px solid hsl(35 12% 86%)' }}>
          <div className="flex gap-1">
            {['Artifacts', 'Notes', 'Sources'].map((tab, i) => (
              <button
                key={tab}
                className="px-3 py-2 text-[11px] font-medium rounded-md"
                style={i === 1
                  ? { background: 'hsl(155 28% 38% / 0.08)', color: 'hsl(155 30% 32%)' }
                  : { color: 'hsl(20 8% 50%)' }
                }
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
        <div className="p-3 flex-1">
          <div className="flex items-center gap-2 mb-3">
            <StickyNote className="w-3.5 h-3.5" style={{ color: 'hsl(155 28% 38%)' }} />
            <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'hsl(20 10% 50%)' }}>Personal notes</p>
          </div>
          <textarea
            className="w-full min-h-[200px] resize-none rounded-lg p-3 text-xs leading-relaxed outline-none"
            style={{
              background: 'hsl(40 28% 98%)',
              border: '1px solid hsl(35 12% 85%)',
              color: 'hsl(20 25% 15%)',
              fontFamily: FONT_BODY,
            }}
            placeholder="Write your notes here..."
            defaultValue={"Eigenvalues = scaling factors for eigenvectors\n\nKey insight: eigenvectors define the 'natural axes' of a transformation. They don't rotate, only scale.\n\nλ = eigenvalue, v = eigenvector\nAv = λv"}
            readOnly
          />
          <p className="text-[10px] text-center mt-2" style={{ color: 'hsl(20 6% 62%)' }}>Auto-saved locally</p>

          <div className="mt-5 pt-4" style={{ borderTop: '1px solid hsl(35 12% 88%)' }}>
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-3.5 h-3.5" style={{ color: 'hsl(155 28% 38%)' }} />
              <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'hsl(20 10% 50%)' }}>Generate</p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {['flashcards', 'quiz', 'summary'].map((type) => (
                <button
                  key={type}
                  className="flex items-center gap-1 rounded-full px-2.5 py-1.5 text-[11px] font-medium capitalize"
                  style={{ border: '1px solid hsl(155 28% 38% / 0.2)', background: 'hsl(155 28% 38% / 0.05)', color: 'hsl(155 30% 32%)' }}
                >
                  <Layers className="w-3 h-3" />
                  {type}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5 pt-4" style={{ borderTop: '1px solid hsl(35 12% 88%)' }}>
            <div className="flex items-center gap-2 mb-2">
              <ExternalLink className="w-3.5 h-3.5" style={{ color: 'hsl(20 10% 50%)' }} />
              <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'hsl(20 10% 50%)' }}>Sources</p>
            </div>
            <div className="space-y-2">
              <div className="flex items-start gap-2 py-2" style={{ borderBottom: '1px solid hsl(35 12% 90%)' }}>
                <ExternalLink className="w-3 h-3 mt-0.5 shrink-0" style={{ color: 'hsl(200 50% 45%)' }} />
                <div>
                  <p className="text-xs" style={{ color: 'hsl(20 25% 15%)' }}>Strang — Ch.6 Eigenvalues</p>
                  <p className="text-[10px] italic mt-0.5 line-clamp-2" style={{ color: 'hsl(20 8% 55%)' }}>
                    "The eigenvalue equation Ax = λx shows that..."
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PreviewScholar() {
  const [view, setView] = useState<'dashboard' | 'workspace'>('dashboard');

  return (
    <div
      style={{
        ...Object.fromEntries(Object.entries(themeVars).map(([k, v]) => [k, v])),
        fontFamily: FONT_BODY,
        background: 'hsl(42 30% 95%)',
        color: 'hsl(20 30% 12%)',
      } as React.CSSProperties}
    >
      <div className="flex h-screen overflow-hidden">
        <SidebarMock />
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Top bar */}
          <div className="shrink-0 flex items-center justify-between px-6 py-3" style={{ borderBottom: '1px solid hsl(35 12% 82%)' }}>
            <div className="flex items-center gap-1 p-0.5 rounded-lg" style={{ background: 'hsl(38 14% 90%)' }}>
              {(['dashboard', 'workspace'] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className="px-4 py-1.5 rounded-md text-xs font-medium capitalize transition-all"
                  style={view === v
                    ? { background: 'hsl(40 28% 98%)', color: 'hsl(20 30% 12%)', boxShadow: '0 1px 3px hsl(20 10% 50% / 0.08)' }
                    : { color: 'hsl(20 10% 50%)' }
                  }
                >
                  {v}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] font-medium px-2.5 py-1 rounded-full" style={{ background: 'hsl(155 28% 38% / 0.08)', color: 'hsl(155 30% 32%)', letterSpacing: '0.12em', textTransform: 'uppercase' as const }}>
                V1 — Scholar
              </span>
              <PanelLeft className="w-4 h-4" style={{ color: 'hsl(20 8% 55%)' }} />
            </div>
          </div>

          <div className="flex-1 overflow-auto" style={{ background: 'hsl(42 30% 95%)' }}>
            {view === 'dashboard' ? <DashboardView /> : <WorkspaceView />}
          </div>
        </main>
      </div>
    </div>
  );
}
