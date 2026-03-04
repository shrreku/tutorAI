import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Loader2, Send, Sparkles } from 'lucide-react';
import {
  useCreateNotebookSession,
  useNotebook,
  useNotebookResources,
  useNotebookSessions,
  useSendNotebookMessage,
  useTurns,
} from '../api/hooks';

const MODES = ['learn', 'doubt', 'practice', 'revision'] as const;

export default function NotebookStudyPage() {
  const navigate = useNavigate();
  const { notebookId = '' } = useParams<{ notebookId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const sessionId = searchParams.get('sessionId') || '';

  const { data: notebook } = useNotebook(notebookId);
  const { data: notebookResources } = useNotebookResources(notebookId);
  const { data: notebookSessions, isLoading: notebookSessionsLoading } = useNotebookSessions(notebookId);
  const createNotebookSession = useCreateNotebookSession(notebookId);
  const { data: turnsData, isLoading: turnsLoading } = useTurns(sessionId);
  const sendNotebookMessage = useSendNotebookMessage(notebookId);

  const [input, setInput] = useState('');
  const [mode, setMode] = useState<(typeof MODES)[number]>('learn');
  const scrollRef = useRef<HTMLDivElement>(null);

  const activeSessionId = useMemo(() => {
    if (sessionId) return sessionId;
    return notebookSessions?.items?.[0]?.session_id ?? '';
  }, [notebookSessions?.items, sessionId]);

  useEffect(() => {
    if (!sessionId && activeSessionId) {
      setSearchParams({ sessionId: activeSessionId });
    }
  }, [activeSessionId, sessionId, setSearchParams]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turnsData?.turns]);

  const startSession = async () => {
    const firstResourceId = notebookResources?.items?.[0]?.resource_id;
    if (!firstResourceId) return;

    const detail = await createNotebookSession.mutateAsync({
      resource_id: firstResourceId,
      mode,
    });
    setSearchParams({ sessionId: detail.session.id });
  };

  const sendMessage = async () => {
    if (!input.trim() || !activeSessionId || sendNotebookMessage.isPending) return;
    const message = input.trim();
    setInput('');
    await sendNotebookMessage.mutateAsync({
      session_id: activeSessionId,
      message,
    });
  };

  const hasResources = (notebookResources?.items?.length ?? 0) > 0;

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <button
        onClick={() => navigate(`/notebooks/${notebookId}`)}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to notebook
      </button>

      <div className="flex flex-wrap gap-3 items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-foreground">{notebook?.title || 'Notebook Study'}</h1>
          <p className="text-sm text-muted-foreground">Notebook-scoped tutor workspace</p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as (typeof MODES)[number])}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
          >
            {MODES.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <button
            onClick={startSession}
            disabled={!hasResources || createNotebookSession.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gold text-primary-foreground text-sm font-medium disabled:opacity-50"
          >
            {createNotebookSession.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            New Notebook Session
          </button>
        </div>
      </div>

      {!hasResources && (
        <div className="mb-4 p-3 rounded-lg border border-gold/20 bg-gold/10 text-sm text-gold">
          Attach at least one resource to this notebook before starting sessions.
        </div>
      )}

      <div className="rounded-xl border border-border bg-card flex-1 min-h-[480px] flex flex-col">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="text-xs text-muted-foreground font-mono">session: {activeSessionId || 'none'}</div>
          {notebookSessionsLoading && <Loader2 className="w-4 h-4 text-gold animate-spin" />}
        </div>

        <div className="flex-1 overflow-auto p-4 space-y-4">
          {turnsLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-5 h-5 text-gold animate-spin" />
            </div>
          ) : (turnsData?.turns?.length ?? 0) === 0 ? (
            <div className="h-full flex items-center justify-center text-center text-sm text-muted-foreground">
              <div>
                Start a notebook session and send your first message.
              </div>
            </div>
          ) : (
            turnsData?.turns.map((turn) => (
              <div key={turn.turn_id} className="space-y-2">
                <div className="flex justify-end">
                  <div className="max-w-[80%] rounded-xl rounded-tr-md bg-gold/10 border border-gold/20 px-3 py-2 text-sm text-foreground whitespace-pre-wrap">
                    {turn.student_message}
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="max-w-[80%] rounded-xl rounded-tl-md bg-background border border-border px-3 py-2 text-sm text-foreground whitespace-pre-wrap">
                    {turn.tutor_response}
                  </div>
                </div>
              </div>
            ))
          )}
          <div ref={scrollRef} />
        </div>

        <div className="p-3 border-t border-border flex items-center gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask inside notebook context..."
            rows={1}
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm resize-none"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void sendMessage();
              }
            }}
          />
          <button
            onClick={() => void sendMessage()}
            disabled={!activeSessionId || !input.trim() || sendNotebookMessage.isPending}
            className="w-9 h-9 rounded-lg bg-gold text-primary-foreground flex items-center justify-center disabled:opacity-50"
          >
            {sendNotebookMessage.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}
