/**
 * Design Preview V2 — "Focus"
 *
 * Cool, minimal, dark-mode aesthetic.
 * Sora throughout. Indigo accent. Hairline borders. Dense layout.
 * Inspired by Linear, Arc, and modern productivity tools.
 */

import { useState } from 'react';
import {
  Home, NotebookPen, FolderOpen, SlidersHorizontal, Plus,
  BookOpen, ArrowRight, Send, Target, Brain, FileText,
  ExternalLink, StickyNote, PanelLeft, LogOut, CheckCircle2,
  Circle, Loader2, Sparkles, ChevronRight,
} from 'lucide-react';

const FONT = '"Sora", system-ui, sans-serif';
const FONT_MONO = '"JetBrains Mono", monospace';

/* ── Color tokens ─────────────────────────────────────────── */
const C = {
  bg:        'hsl(228 18% 5%)',
  bg2:       'hsl(228 14% 7.5%)',
  surface:   'hsl(228 14% 9%)',
  card:      'hsl(228 14% 8.5%)',
  fg:        'hsl(215 15% 88%)',
  fgMuted:   'hsl(215 8% 48%)',
  fgDim:     'hsl(215 6% 35%)',
  border:    'hsl(228 8% 13%)',
  borderSub: 'hsl(228 6% 10%)',
  accent:    'hsl(238 55% 62%)',
  accentSub: 'hsl(238 40% 52%)',
  accentBg:  'hsl(238 40% 62% / 0.08)',
  accentBg2: 'hsl(238 40% 62% / 0.12)',
  sidebar:   'hsl(230 20% 3.5%)',
  sidebarFg: 'hsl(215 8% 48%)',
  green:     'hsl(155 50% 42%)',
  greenBg:   'hsl(155 40% 42% / 0.1)',
  amber:     'hsl(38 75% 52%)',
  amberBg:   'hsl(38 60% 52% / 0.08)',
};

const navItems = [
  { label: 'Studio', icon: Home, active: false },
  { label: 'Notebooks', icon: NotebookPen, active: true },
  { label: 'Resources', icon: FolderOpen, active: false },
  { label: 'Settings', icon: SlidersHorizontal, active: false },
];

const mockNotebooks = [
  { title: 'Linear Algebra', goal: 'Master matrix operations, vector spaces, and eigenvalue decomposition', date: '2026-03-08', sessions: 12, progress: 68 },
  { title: 'Organic Chemistry', goal: 'Understand reaction mechanisms and functional group transformations', date: '2026-03-05', sessions: 8, progress: 45 },
  { title: 'Modern History', goal: 'Analyze major geopolitical shifts from 1900–2000', date: '2026-02-28', sessions: 5, progress: 30 },
];

const mockObjectives = [
  { title: 'Matrix multiplication & properties', status: 'completed' as const, pct: 100 },
  { title: 'Row reduction & echelon forms', status: 'completed' as const, pct: 100 },
  { title: 'Vector spaces & subspaces', status: 'active' as const, pct: 55 },
  { title: 'Eigenvalues & eigenvectors', status: 'pending' as const, pct: 0 },
];

const mockMessages = [
  { role: 'student' as const, text: 'Can you explain how eigenvalues relate to matrix transformations?' },
  { role: 'tutor' as const, text: 'When you multiply a matrix by a vector, most vectors change both direction and magnitude. But eigenvectors are special: they only get scaled. The eigenvalue is that scaling factor.\n\nIf Av = 3v, then v is an eigenvector with eigenvalue 3. The matrix stretches v by 3× without rotation.' },
  { role: 'student' as const, text: 'So eigenvalue 2 means the vector just doubles in length?' },
  { role: 'tutor' as const, text: 'Correct. And eigenvalue −1 flips direction while preserving magnitude. This geometric interpretation reveals the "natural axes" of a transformation — the directions that are invariant under it.' },
];

function SidebarMock() {
  return (
    <aside
      className="w-56 flex flex-col shrink-0"
      style={{ background: C.sidebar, borderRight: `1px solid ${C.borderSub}`, fontFamily: FONT }}
    >
      <div className="p-4 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md flex items-center justify-center" style={{ background: C.accentBg, border: `1px solid ${C.accent}33` }}>
            <BookOpen className="w-3.5 h-3.5" style={{ color: C.accent }} />
          </div>
          <span style={{ fontFamily: FONT, color: C.fg, fontSize: '0.9rem', fontWeight: 600, letterSpacing: '-0.02em' }}>
            StudyAgent
          </span>
        </div>
      </div>

      <div className="px-2.5 mb-3">
        <button
          className="flex items-center justify-center gap-1.5 w-full rounded-md text-xs font-medium py-2"
          style={{ background: C.accentBg, border: `1px solid ${C.accent}22`, color: C.accent }}
        >
          <Plus className="w-3.5 h-3.5" />
          New Notebook
        </button>
      </div>

      <nav className="flex-1 px-2.5 space-y-px">
        {navItems.map(({ label, icon: Icon, active }) => (
          <div
            key={label}
            className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium"
            style={{
              background: active ? C.accentBg : 'transparent',
              color: active ? C.accent : C.sidebarFg,
              borderLeft: active ? `2px solid ${C.accent}` : '2px solid transparent',
            }}
          >
            <Icon className="w-4 h-4" />
            {label}
          </div>
        ))}
      </nav>

      <div className="p-3 border-t" style={{ borderColor: C.borderSub }}>
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md flex items-center justify-center text-[10px] font-semibold" style={{ background: C.accentBg, color: C.accent }}>
            SK
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-medium truncate" style={{ color: C.fg }}>Student</p>
            <p className="text-[10px] truncate" style={{ color: C.fgDim }}>student@uni.edu</p>
          </div>
          <LogOut className="w-3.5 h-3.5 shrink-0" style={{ color: C.fgDim }} />
        </div>
      </div>
    </aside>
  );
}

function DashboardView() {
  return (
    <div className="p-6 max-w-5xl" style={{ fontFamily: FONT }}>
      <div className="mb-8">
        <h1 style={{ fontSize: '1.5rem', fontWeight: 600, color: C.fg, letterSpacing: '-0.03em' }}>
          Dashboard
        </h1>
        <p className="mt-1" style={{ fontSize: '0.8rem', color: C.fgMuted }}>
          3 notebooks · 14 resources · 28 study hours
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-8">
        {[
          { icon: Plus, title: 'Create Notebook', desc: 'New course container' },
          { icon: BookOpen, title: 'Resume Study', desc: 'Continue last session' },
          { icon: FolderOpen, title: 'Resources', desc: 'Manage materials' },
        ].map(({ icon: Icon, title, desc }) => (
          <button
            key={title}
            className="group rounded-lg p-4 text-left transition-colors duration-150"
            style={{ background: C.card, border: `1px solid ${C.border}` }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = `${C.accent}44`; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border; }}
          >
            <div className="flex items-center gap-3 mb-2">
              <Icon className="w-4 h-4" style={{ color: C.accent }} />
              <p className="text-xs font-semibold" style={{ color: C.fg }}>{title}</p>
              <ArrowRight className="w-3 h-3 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: C.fgMuted }} />
            </div>
            <p className="text-[11px]" style={{ color: C.fgMuted }}>{desc}</p>
          </button>
        ))}
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 style={{ fontSize: '0.85rem', fontWeight: 600, color: C.fg, letterSpacing: '-0.01em' }}>Notebooks</h2>
        <span className="text-[10px] font-medium" style={{ color: C.fgDim }}>3 total</span>
      </div>

      {/* Table-like list */}
      <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${C.border}` }}>
        {mockNotebooks.map((nb, i) => (
          <div
            key={nb.title}
            className="flex items-center gap-4 px-4 py-3 transition-colors cursor-pointer"
            style={{
              background: C.card,
              borderBottom: i < mockNotebooks.length - 1 ? `1px solid ${C.border}` : 'none',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = C.surface; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = C.card; }}
          >
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium" style={{ color: C.fg }}>{nb.title}</p>
              <p className="text-[11px] truncate mt-0.5" style={{ color: C.fgDim }}>{nb.goal}</p>
            </div>
            <div className="w-24 shrink-0">
              <div className="h-1 rounded-full overflow-hidden" style={{ background: C.border }}>
                <div className="h-full rounded-full" style={{ width: `${nb.progress}%`, background: C.accent }} />
              </div>
              <p className="text-[10px] mt-1 text-right" style={{ color: C.fgDim, fontFamily: FONT_MONO }}>{nb.progress}%</p>
            </div>
            <div className="w-16 text-right shrink-0">
              <p className="text-[10px]" style={{ color: C.fgDim, fontFamily: FONT_MONO }}>{nb.sessions} sess</p>
            </div>
            <div className="w-20 text-right shrink-0">
              <p className="text-[10px]" style={{ color: C.fgDim, fontFamily: FONT_MONO }}>{nb.date}</p>
            </div>
            <ChevronRight className="w-3.5 h-3.5 shrink-0" style={{ color: C.fgDim }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function WorkspaceView() {
  return (
    <div className="flex h-full" style={{ fontFamily: FONT }}>
      {/* Left — Study Map */}
      <div className="w-56 shrink-0 overflow-y-auto p-2.5 space-y-3" style={{ borderRight: `1px solid ${C.border}` }}>
        <div className="flex items-center gap-1.5 px-1">
          <FileText className="w-3 h-3" style={{ color: C.fgDim }} />
          <h3 className="text-[10px] font-semibold uppercase" style={{ color: C.fgDim, letterSpacing: '0.1em' }}>Resources</h3>
        </div>
        <div className="flex items-center gap-2 px-1 py-2" style={{ borderBottom: `1px solid ${C.border}` }}>
          <div className="w-1.5 h-1.5 rounded-full" style={{ background: C.green }} />
          <span className="text-[11px]" style={{ color: C.fg }}>Strang — Ch.6</span>
        </div>

        <div>
          <div className="flex items-center gap-1.5 px-1 mb-2">
            <Target className="w-3 h-3" style={{ color: C.fgDim }} />
            <h3 className="text-[10px] font-semibold uppercase" style={{ color: C.fgDim, letterSpacing: '0.1em' }}>Objectives</h3>
            <span className="text-[9px] ml-auto" style={{ color: C.fgDim, fontFamily: FONT_MONO }}>2/4</span>
          </div>
          {mockObjectives.map((obj, i) => {
            const Icon = obj.status === 'completed' ? CheckCircle2 : obj.status === 'active' ? Loader2 : Circle;
            const color = obj.status === 'completed' ? C.green : obj.status === 'active' ? C.accent : C.fgDim;
            return (
              <div key={i} className="flex items-start gap-2 px-1 py-2" style={{ borderBottom: `1px solid ${C.border}` }}>
                <span className="text-[9px] font-semibold w-4 text-right shrink-0 pt-px" style={{ color: C.fgDim, fontFamily: FONT_MONO }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <Icon className="w-3 h-3 mt-0.5 shrink-0" style={{ color }} />
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] leading-snug" style={{ color: C.fg }}>{obj.title}</p>
                  <div className="mt-1 h-0.5 rounded-full overflow-hidden" style={{ background: C.border }}>
                    <div className="h-full rounded-full" style={{ width: `${obj.pct}%`, background: color }} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div>
          <div className="flex items-center gap-1.5 px-1 mb-2">
            <Brain className="w-3 h-3" style={{ color: C.fgDim }} />
            <h3 className="text-[10px] font-semibold uppercase" style={{ color: C.fgDim, letterSpacing: '0.1em' }}>Mastery</h3>
          </div>
          {['Matrix mult.', 'Row reduction', 'Span & basis'].map((c, i) => {
            const score = [92, 85, 55][i];
            const bar = score >= 70 ? C.green : C.amber;
            return (
              <div key={c} className="flex items-center gap-2 px-1 py-1.5">
                <span className="text-[11px] flex-1 truncate" style={{ color: C.fg }}>{c}</span>
                <div className="w-14 h-0.5 rounded-full overflow-hidden shrink-0" style={{ background: C.border }}>
                  <div className="h-full rounded-full" style={{ width: `${score}%`, background: bar }} />
                </div>
                <span className="text-[9px] w-7 text-right shrink-0" style={{ color: C.fgDim, fontFamily: FONT_MONO }}>{score}%</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Center — Chat */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="shrink-0 px-4 py-2.5 flex items-center gap-2" style={{ borderBottom: `1px solid ${C.border}` }}>
          <div className="w-1.5 h-1.5 rounded-full" style={{ background: C.accent }} />
          <p className="text-[11px] font-medium" style={{ color: C.fg }}>Vector spaces & subspaces</p>
          <span className="text-[9px] font-medium px-1.5 py-0.5 rounded" style={{ background: C.accentBg, color: C.accent }}>active</span>
          <span className="ml-auto text-[9px]" style={{ color: C.fgDim, fontFamily: FONT_MONO }}>step 3 of 4</span>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {mockMessages.map((msg, i) => (
            <div key={i}>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[9px] font-semibold uppercase" style={{ color: C.fgDim, letterSpacing: '0.08em' }}>
                  {msg.role === 'student' ? 'You' : 'Tutor'}
                </span>
                <div className="h-px flex-1" style={{ background: C.border }} />
              </div>
              <p className="text-[13px] leading-relaxed whitespace-pre-line pl-0" style={{ color: C.fg }}>
                {msg.text}
              </p>
            </div>
          ))}
        </div>

        <div className="shrink-0 px-4 py-3" style={{ borderTop: `1px solid ${C.border}` }}>
          <div className="flex items-center gap-2 rounded-md px-3 py-2.5" style={{ background: C.surface, border: `1px solid ${C.border}` }}>
            <input
              className="flex-1 bg-transparent text-xs outline-none"
              style={{ color: C.fg, fontFamily: FONT }}
              placeholder="Ask about the material..."
              readOnly
            />
            <button className="w-7 h-7 rounded-md flex items-center justify-center" style={{ background: C.accent, color: 'white' }}>
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Right — Notes & Artifacts */}
      <div className="w-64 shrink-0 overflow-y-auto flex flex-col" style={{ borderLeft: `1px solid ${C.border}` }}>
        <div className="px-2.5 py-2.5 flex gap-px" style={{ borderBottom: `1px solid ${C.border}` }}>
          {['Artifacts', 'Notes', 'Sources'].map((tab, i) => (
            <button
              key={tab}
              className="flex-1 py-1.5 text-[10px] font-medium rounded"
              style={i === 1
                ? { background: C.accentBg, color: C.accent }
                : { color: C.fgDim }
              }
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="p-2.5 flex-1">
          <div className="flex items-center gap-1.5 mb-2">
            <StickyNote className="w-3 h-3" style={{ color: C.accent }} />
            <p className="text-[10px] font-semibold uppercase" style={{ color: C.fgDim, letterSpacing: '0.1em' }}>Notes</p>
          </div>
          <textarea
            className="w-full min-h-[180px] resize-none rounded-md p-2.5 text-[11px] leading-relaxed outline-none"
            style={{
              background: C.surface,
              border: `1px solid ${C.border}`,
              color: C.fg,
              fontFamily: FONT,
            }}
            defaultValue={"Eigenvalues = scaling factors\nEigenvectors = invariant directions\n\nAv = λv\n\nGeometric meaning: eigenvectors define natural axes of transformation"}
            readOnly
          />
          <p className="text-[9px] text-center mt-1.5" style={{ color: C.fgDim }}>auto-saved</p>

          <div className="mt-4 pt-3" style={{ borderTop: `1px solid ${C.border}` }}>
            <div className="flex items-center gap-1.5 mb-2">
              <Sparkles className="w-3 h-3" style={{ color: C.accent }} />
              <p className="text-[10px] font-semibold uppercase" style={{ color: C.fgDim, letterSpacing: '0.1em' }}>Generate</p>
            </div>
            <div className="flex flex-wrap gap-1">
              {['flashcards', 'quiz', 'summary'].map((type) => (
                <button
                  key={type}
                  className="rounded px-2 py-1 text-[10px] font-medium capitalize"
                  style={{ border: `1px solid ${C.border}`, color: C.fgMuted }}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 pt-3" style={{ borderTop: `1px solid ${C.border}` }}>
            <div className="flex items-center gap-1.5 mb-2">
              <ExternalLink className="w-3 h-3" style={{ color: C.fgDim }} />
              <p className="text-[10px] font-semibold uppercase" style={{ color: C.fgDim, letterSpacing: '0.1em' }}>Sources</p>
            </div>
            <div className="flex items-start gap-2 py-1.5" style={{ borderBottom: `1px solid ${C.border}` }}>
              <ExternalLink className="w-3 h-3 mt-0.5 shrink-0" style={{ color: 'hsl(210 60% 55%)' }} />
              <div>
                <p className="text-[11px]" style={{ color: C.fg }}>Strang — Ch.6</p>
                <p className="text-[10px] italic mt-0.5 line-clamp-2" style={{ color: C.fgDim }}>
                  "The eigenvalue equation Ax = λx..."
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PreviewFocus() {
  const [view, setView] = useState<'dashboard' | 'workspace'>('dashboard');

  return (
    <div
      style={{
        fontFamily: FONT,
        background: C.bg,
        color: C.fg,
        minHeight: '100vh',
      }}
    >
      <div className="flex h-screen overflow-hidden">
        <SidebarMock />
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Top bar */}
          <div className="shrink-0 flex items-center justify-between px-4 py-2" style={{ borderBottom: `1px solid ${C.border}` }}>
            <div className="flex items-center gap-px p-px rounded-md" style={{ background: C.border }}>
              {(['dashboard', 'workspace'] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className="px-3 py-1.5 rounded text-[11px] font-medium capitalize transition-colors"
                  style={view === v
                    ? { background: C.surface, color: C.fg }
                    : { background: 'transparent', color: C.fgDim }
                  }
                >
                  {v}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[9px] font-semibold px-2 py-1 rounded" style={{ background: C.accentBg, color: C.accent, letterSpacing: '0.1em', textTransform: 'uppercase' as const }}>
                V2 — Focus
              </span>
              <PanelLeft className="w-3.5 h-3.5" style={{ color: C.fgDim }} />
            </div>
          </div>

          <div className="flex-1 overflow-auto" style={{ background: C.bg }}>
            {view === 'dashboard' ? <DashboardView /> : <WorkspaceView />}
          </div>
        </main>
      </div>
    </div>
  );
}
