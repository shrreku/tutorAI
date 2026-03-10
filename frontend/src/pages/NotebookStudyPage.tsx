import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Loader2, Send, Sparkles, BookOpen, MessageSquare,
  Target, ChevronDown, Layers3,
} from 'lucide-react';
import { getApiErrorMessage } from '../api/client';
import {
  useCreateNotebookSession,
  useNotebook,
  useNotebookResources,
  useNotebookSessions,
  useResources,
  useSendNotebookMessage,
  useTurns,
} from '../api/hooks';
import SessionLaunchPanel from '../components/notebooks/SessionLaunchPanel';
import type { NotebookSessionCreateRequest } from '../types/api';

const MODES = ['learn', 'doubt', 'practice', 'revision'] as const;
const MODE_META: Record<string, { icon: typeof BookOpen; label: string; color: string }> = {
  learn:    { icon: BookOpen,       label: 'Learn',    color: 'text-blue-400' },
  doubt:    { icon: MessageSquare,  label: 'Doubt',    color: 'text-emerald-400' },
  practice: { icon: Target,         label: 'Practice', color: 'text-orange-400' },
  revision: { icon: Sparkles,       label: 'Revision', color: 'text-purple-400' },
};

/* Simple markdown-ish rendering: bold, italic, code, bullet lists */
function renderFormattedText(text: string) {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="list-disc list-inside space-y-0.5 my-1">
          {listItems.map((li, i) => <li key={i}>{formatInline(li)}</li>)}
        </ul>,
      );
      listItems = [];
    }
  };

  const formatInline = (s: string): React.ReactNode => {
    // Simple inline formatting: **bold**, *italic*, `code`
    const parts: React.ReactNode[] = [];
    let remaining = s;
    let key = 0;
    const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(remaining)) !== null) {
      if (match.index > lastIndex) parts.push(remaining.slice(lastIndex, match.index));
      if (match[2]) parts.push(<strong key={key++} className="font-semibold text-foreground">{match[2]}</strong>);
      else if (match[3]) parts.push(<em key={key++} className="italic">{match[3]}</em>);
      else if (match[4]) parts.push(<code key={key++} className="px-1 py-0.5 rounded bg-border/50 font-mono text-[0.85em]">{match[4]}</code>);
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < remaining.length) parts.push(remaining.slice(lastIndex));
    return parts.length === 0 ? s : <>{parts}</>;
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (/^[-*•]\s+/.test(trimmed)) {
      listItems.push(trimmed.replace(/^[-*•]\s+/, ''));
      continue;
    }
    flushList();

    if (/^#{1,3}\s+/.test(trimmed)) {
      const hMatch = trimmed.match(/^(#{1,3})\s+(.*)$/);
      if (hMatch) {
        const level = hMatch[1].length;
        const cls = level === 1 ? 'text-base font-semibold text-foreground mt-2 mb-1' : level === 2 ? 'text-sm font-semibold text-foreground mt-1.5 mb-0.5' : 'text-sm font-medium text-foreground mt-1 mb-0.5';
        elements.push(<p key={elements.length} className={cls}>{formatInline(hMatch[2])}</p>);
        continue;
      }
    }
    if (trimmed === '') { elements.push(<div key={elements.length} className="h-2" />); continue; }
    elements.push(<p key={elements.length} className="leading-relaxed">{formatInline(trimmed)}</p>);
  }
  flushList();
  return <div className="space-y-0.5">{elements}</div>;
}

export default function NotebookStudyPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { notebookId = '' } = useParams<{ notebookId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const sessionId = searchParams.get('sessionId') || '';

  const { data: notebook } = useNotebook(notebookId);
  const { data: notebookResources } = useNotebookResources(notebookId);
  const { data: notebookSessions, isLoading: notebookSessionsLoading } = useNotebookSessions(notebookId);
  const { data: allResources } = useResources();
  const createNotebookSession = useCreateNotebookSession(notebookId);
  const { data: turnsData, isLoading: turnsLoading } = useTurns(sessionId);
  const sendNotebookMessage = useSendNotebookMessage(notebookId);

  const [input, setInput] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showSessionPicker, setShowSessionPicker] = useState(false);
  const [launchSummary, setLaunchSummary] = useState<Record<string, unknown> | null>(
    ((location.state as { launchSummary?: Record<string, unknown> } | null)?.launchSummary) ?? null,
  );
  const scrollRef = useRef<HTMLDivElement>(null);

  const activeSessionId = useMemo(() => {
    if (sessionId) return sessionId;
    return notebookSessions?.items?.[0]?.session_id ?? '';
  }, [notebookSessions?.items, sessionId]);

  const activeNotebookSession = useMemo(() => {
    if (!activeSessionId || !notebookSessions?.items) return null;
    return notebookSessions.items.find((s) => s.session_id === activeSessionId) ?? null;
  }, [activeSessionId, notebookSessions?.items]);

  useEffect(() => {
    if (!sessionId && activeSessionId) setSearchParams({ sessionId: activeSessionId });
  }, [activeSessionId, sessionId, setSearchParams]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turnsData?.turns]);

  const startSessionFromLaunchPanel = async (request: NotebookSessionCreateRequest) => {
    setErrorMessage(null);
    try {
      const detail = await createNotebookSession.mutateAsync(request);
      setSearchParams({ sessionId: detail.session.id });
      setLaunchSummary(detail.preparation_summary ?? null);
    } catch (error) {
      setErrorMessage(getApiErrorMessage(error, 'Failed to start notebook session.'));
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || !activeSessionId || sendNotebookMessage.isPending) return;
    const message = input.trim();
    setErrorMessage(null);
    try {
      setInput('');
      await sendNotebookMessage.mutateAsync({ session_id: activeSessionId, message });
    } catch (error) {
      setInput(message);
      setErrorMessage(getApiErrorMessage(error, 'Failed to send notebook message.'));
    }
  };

  const hasResources = (notebookResources?.items?.length ?? 0) > 0;
  const sessions = notebookSessions?.items ?? [];
  const turns = turnsData?.turns ?? [];
  const resourceMap = new Map((allResources?.items ?? []).map((resource) => [resource.id, resource]));

  const recommendedMode = sessions.length === 0 ? 'learn' : turns.length > 0 ? (activeNotebookSession?.mode as (typeof MODES)[number] | undefined) ?? 'practice' : 'practice';
  const recommendedReason = sessions.length === 0
    ? 'Start with a learn session to establish the objective sequence and baseline understanding.'
    : 'Use the launcher to open a fresh branch when you want a different scope or topic than your current thread.';

  const launchResources = (notebookResources?.items ?? []).map((resource) => ({
    id: resource.resource_id,
    label: resourceMap.get(resource.resource_id)?.filename ?? resource.resource_id,
    subtitle: resourceMap.get(resource.resource_id)?.topic || 'Attached notebook resource',
  }));

  const quickActions = activeNotebookSession?.mode === 'practice'
    ? ['Give me one harder question.', 'Check my reasoning step by step.', 'Turn this into a mini quiz.']
    : activeNotebookSession?.mode === 'revision'
      ? ['Summarize the weak points first.', 'Test me on the weakest concept.', 'Make me recall before explaining.']
      : ['Explain this more simply.', 'Show one worked example.', 'Give me a question on this.', 'Point me to the source.'];

  const activeMeta = activeNotebookSession ? MODE_META[activeNotebookSession.mode] : null;
  const ActiveIcon = activeMeta?.icon ?? BookOpen;

  const scopeType = String(launchSummary?.scope_type ?? '');
  const scopeResourceIds = Array.isArray(launchSummary?.scope_resource_ids) ? launchSummary?.scope_resource_ids : [];
  const artifactsPrepared = Number(launchSummary?.artifacts_created ?? 0) + Number(launchSummary?.topic_artifacts_created ?? 0);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header bar */}
      <div className="px-6 py-3 border-b border-border/50 flex items-center gap-3 shrink-0">
        <button onClick={() => navigate(`/notebooks/${notebookId}`)} className="text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="h-4 w-px bg-border" />
        <h1 className="font-display text-base font-semibold text-foreground truncate">{notebook?.title || 'Study'}</h1>

        {/* Session indicator */}
        {activeNotebookSession && (
          <div className="relative ml-auto">
            <button onClick={() => setShowSessionPicker(!showSessionPicker)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border/50 hover:border-gold/20 transition-colors text-xs">
              <ActiveIcon className={`w-3.5 h-3.5 ${activeMeta?.color ?? ''}`} />
              <span className="capitalize text-foreground font-medium">{activeNotebookSession.mode}</span>
              <span className="text-muted-foreground">·</span>
              <span className="text-muted-foreground">{new Date(activeNotebookSession.started_at).toLocaleDateString()}</span>
              <ChevronDown className="w-3 h-3 text-muted-foreground" />
            </button>

            {showSessionPicker && (
              <div className="absolute right-0 top-full mt-1 z-20 w-64 rounded-lg border border-border bg-card shadow-lg overflow-hidden">
                <div className="p-2 max-h-60 overflow-auto space-y-1">
                  {sessions.map((s) => {
                    const meta = MODE_META[s.mode] ?? MODE_META.learn;
                    const Icon = meta.icon;
                    const isActive = s.session_id === activeSessionId;
                    return (
                      <button key={s.id} onClick={() => { setSearchParams({ sessionId: s.session_id }); setShowSessionPicker(false); }}
                        className={`w-full flex items-center gap-2 p-2 rounded-md text-left text-xs transition-colors ${isActive ? 'bg-gold/10 border border-gold/20' : 'hover:bg-muted/50 border border-transparent'}`}>
                        <Icon className={`w-3.5 h-3.5 shrink-0 ${meta.color}`} />
                        <span className="capitalize font-medium text-foreground">{s.mode}</span>
                        <span className="text-muted-foreground ml-auto">{new Date(s.started_at).toLocaleDateString()}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
        {!activeNotebookSession && !notebookSessionsLoading && (
          <span className="text-xs text-muted-foreground ml-auto">No active session</span>
        )}
      </div>

      {/* Warnings */}
      <div className="px-6">
        {!hasResources && (
          <div className="mt-3 p-3 rounded-lg border border-gold/20 bg-gold/[0.06] text-sm text-gold">
            Attach at least one resource before starting sessions.
          </div>
        )}
        {launchSummary && (
          <div className="mt-3 rounded-2xl border border-gold/20 bg-[linear-gradient(135deg,rgba(245,158,11,0.14),rgba(255,255,255,0.8))] px-4 py-3 text-sm text-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-gold/20 bg-card/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-gold">
                <Layers3 className="h-3.5 w-3.5" /> Session context ready
              </span>
              {scopeType && <span className="text-xs text-muted-foreground">Scope: {scopeType.replace('_', ' ')}</span>}
              {scopeResourceIds.length > 0 && <span className="text-xs text-muted-foreground">Resources: {scopeResourceIds.length}</span>}
              {artifactsPrepared > 0 && <span className="text-xs text-muted-foreground">Prep artifacts: {artifactsPrepared}</span>}
            </div>
          </div>
        )}
        {errorMessage && (
          <div className="mt-3 p-3 rounded-lg border border-red-500/20 bg-red-500/[0.06] text-sm text-red-300 flex items-start gap-2">
            <span className="flex-1">{errorMessage}</span>
            <button onClick={() => setErrorMessage(null)} className="text-red-400 hover:text-red-200 text-xs shrink-0">dismiss</button>
          </div>
        )}
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {turnsLoading ? (
          <div className="flex items-center justify-center h-full"><Loader2 className="w-5 h-5 text-gold animate-spin" /></div>
        ) : !activeSessionId ? (
          <div className="h-full flex items-center justify-center">
            <div className="w-full max-w-5xl animate-fade-up">
              <SessionLaunchPanel
                resources={launchResources}
                recommendedMode={recommendedMode}
                recommendedReason={recommendedReason}
                pending={createNotebookSession.isPending}
                onLaunch={startSessionFromLaunchPanel}
                title="Open a new study thread"
                subtitle="Launch from here when you want a fresh session with a specific scope, resource mix, or topic focus."
              />
            </div>
          </div>
        ) : turns.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-lg animate-fade-up">
              <div className="w-14 h-14 rounded-2xl bg-gold/10 border border-gold/20 flex items-center justify-center mx-auto mb-4">
                <Sparkles className="w-6 h-6 text-gold" />
              </div>
              <h2 className="font-display text-xl font-semibold text-foreground mb-2">Session is ready</h2>
              <p className="text-sm text-muted-foreground mb-5">You have an active tutoring thread. Ask a first question or use one of the suggested prompts to set direction quickly.</p>
              <div className="flex flex-wrap items-center justify-center gap-2">
                {quickActions.map((action) => (
                  <button key={action} onClick={() => setInput(action)} className="rounded-full border border-border bg-card px-3 py-1.5 text-xs text-foreground transition-colors hover:border-gold/20 hover:text-gold">
                    {action}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-5">
            {turns.map((turn) => (
              <div key={turn.turn_id} className="space-y-3">
                {/* Student bubble */}
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-gold/10 border border-gold/20 px-4 py-3 text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                    {turn.student_message}
                  </div>
                </div>
                {/* Tutor bubble */}
                <div className="flex justify-start gap-3">
                  <div className="w-7 h-7 rounded-lg bg-card border border-border flex items-center justify-center shrink-0 mt-0.5">
                    <Sparkles className="w-3.5 h-3.5 text-gold" />
                  </div>
                  <div className="max-w-[85%] rounded-2xl rounded-tl-md bg-card border border-border px-4 py-3 text-sm text-foreground leading-relaxed">
                    {renderFormattedText(turn.tutor_response)}
                  </div>
                </div>
              </div>
            ))}
            <div ref={scrollRef} />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="px-6 py-3 border-t border-border/50 shrink-0">
        <div className="max-w-3xl mx-auto space-y-3">
          {activeSessionId && (
            <div className="flex flex-wrap gap-2">
              {quickActions.map((action) => (
                <button
                  key={action}
                  type="button"
                  onClick={() => setInput(action)}
                  className="rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-gold/20 hover:text-foreground"
                >
                  {action}
                </button>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={activeSessionId ? 'Ask your tutor…' : 'Start a session first…'}
              disabled={!activeSessionId}
              rows={1}
              className="w-full rounded-xl border border-border bg-background px-4 py-3 pr-12 text-sm resize-none focus:outline-none focus:border-gold/30 transition-colors disabled:opacity-50 placeholder:text-muted-foreground/50"
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendMessage(); } }}
              style={{ minHeight: '44px', maxHeight: '120px' }}
              onInput={(e) => { const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 120) + 'px'; }}
            />
          </div>
          <button onClick={() => void sendMessage()} disabled={!activeSessionId || !input.trim() || sendNotebookMessage.isPending}
            className="w-10 h-10 rounded-xl bg-gold text-primary-foreground flex items-center justify-center disabled:opacity-40 hover:bg-gold/90 transition-colors shrink-0">
            {sendNotebookMessage.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
        </div>
      </div>
    </div>
  );
}
